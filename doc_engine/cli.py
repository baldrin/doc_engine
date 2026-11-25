"""Command line.

  python -m doc_engine db init | check | reset --yes
  python -m doc_engine samples
  python -m doc_engine preflight
  python -m doc_engine serve
  python -m doc_engine worker
  python -m doc_engine load --flow <id> --document <id> [--value "Name=value"] --jobs N [--bulk K] [--confirm-saturation]
  python -m doc_engine probe bucket --model sonnet [--dry-run] [--confirm-saturation]
  python -m doc_engine jobs
  python -m doc_engine export --job <id> --out <dir>
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import signal
import sys
import time
from pathlib import Path

from . import flows, planner, samples
from .config import Section, load_config, placeholders
from .db import Db, apply_schema, missing_tables, reset_schema, sync_models


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("doc_engine").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def cmd_db(cfg: Section, args: argparse.Namespace) -> int:
    db = Db(cfg)
    try:
        if args.action == "init":
            await apply_schema(db)
            await sync_models(db, cfg)
            print("schema applied; model limits copied from the config:")
            for r in await db.fetch("SELECT model, gateway_name, itpm, otpm, out_capacity FROM quota ORDER BY model"):
                print(f"  {r['model']:8} {r['gateway_name']:34} ITPM {r['itpm']:>11,.0f}  OTPM {r['otpm']:>9,.0f}  "
                      f"output cap {r['out_capacity']:>8,.0f}")
        elif args.action == "check":
            miss = await missing_tables(db)
            print("all tables present" if not miss else "missing tables: " + ", ".join(miss))
            return 1 if miss else 0
        elif args.action == "reset":
            if not args.yes:
                print("This deletes every flow, document, job and all history. Re-run with --yes to do it.")
                return 2
            await reset_schema(db)
            print("all Document Engine tables removed. Run `python -m doc_engine db init` next.")
    finally:
        await db.close()
    return 0


async def _tables_missing(db: Db) -> bool:
    """True, with a message, when `db init` has not been run."""
    if await missing_tables(db):
        print("the database is not set up. Run `python -m doc_engine db init` first.")
        return True
    return False


def _pairs(items: list[str], flag: str, bare_ok: bool = False) -> dict[str, str]:
    """Parse repeated "Name=value" arguments. A malformed one is refused, not dropped."""
    out: dict[str, str] = {}
    for it in items:
        if "=" not in it:
            if bare_ok:
                continue
            raise ValueError(f"{flag} \"{it}\" is not in the form \"Name=value\"")
        k, v = it.split("=", 1)
        if not k.strip():
            raise ValueError(f"{flag} \"{it}\" has no name before the = sign")
        out[k.strip()] = v
    return out


async def cmd_samples(cfg: Section, args: argparse.Namespace) -> int:
    db = Db(cfg)
    try:
        if await _tables_missing(db):
            return 1
        print("building sample flows and documents (the 150-page document takes a few seconds)...")
        made = await samples.install_samples(db, cfg, force=args.force)
        print(f"created {made['flows']} flow(s) and {made['documents']} document(s)")
        for r in await db.fetch("SELECT flow_id, name FROM flows ORDER BY name"):
            print(f"  flow      {r['flow_id']:26} {r['name']}")
        for r in await db.fetch("SELECT document_id, name, pages, size_bytes FROM documents ORDER BY name"):
            print(f"  document  {r['document_id']:26} {r['name']}  ({r['pages']} pages, {r['size_bytes'] / 1e6:.1f} MB)")
    finally:
        await db.close()
    return 0


async def cmd_jobs(cfg: Section, args: argparse.Namespace) -> int:
    db = Db(cfg)
    try:
        if await _tables_missing(db):
            return 1
        rows = await db.fetch(
            """SELECT j.job_id, j.flow_name, j.document_name, j.priority, j.state, j.submitted_at,
                      extract(epoch FROM coalesce(j.finished_at, clock_timestamp()) - j.submitted_at) AS wall_s,
                      (SELECT count(*) FROM calls c WHERE c.job_id = j.job_id) AS calls,
                      (SELECT count(*) FROM calls c WHERE c.job_id = j.job_id AND c.outcome = '429') AS rejections
               FROM jobs j ORDER BY j.submitted_at DESC LIMIT %s""", (args.limit,))
        for r in rows:
            print(f"{r['job_id']}  {r['state']:9} {r['priority']:11} {r['wall_s']:7.1f}s  calls {r['calls']:4}  "
                  f"429s {r['rejections']:3}  {r['flow_name']} / {r['document_name']}")
    finally:
        await db.close()
    return 0


async def run_summary(db: Db, cfg: Section, job_ids: list[str]) -> dict:
    jobs = await db.fetch(
        """SELECT job_id, priority, state, label, error, extract(epoch FROM finished_at - submitted_at) AS wall_s,
                  extract(epoch FROM started_at - submitted_at) AS queued_s
           FROM jobs WHERE job_id = ANY(%s) ORDER BY submitted_at, job_id""", (job_ids,))
    calls = await db.fetchone(
        """SELECT count(*) AS calls, count(*) FILTER (WHERE outcome = 'ok') AS ok,
                  count(*) FILTER (WHERE outcome = '429') AS rejections,
                  count(*) FILTER (WHERE outcome = '429' AND limit_type = 'output') AS rej_output,
                  count(*) FILTER (WHERE outcome = '429' AND limit_type = 'input') AS rej_input,
                  count(*) FILTER (WHERE truncated) AS truncated,
                  coalesce(sum(output_tokens), 0) AS output_tokens, coalesce(sum(input_tokens), 0) AS input_tokens,
                  coalesce(sum(cache_read), 0) AS cache_read, coalesce(sum(cache_write), 0) AS cache_write,
                  count(*) FILTER (WHERE cache_write > 0) AS cache_writes,
                  extract(epoch FROM max(done_at) - min(sent_at)) AS span_s
           FROM calls WHERE job_id = ANY(%s)""", (job_ids,))
    per_model = await db.fetch(
        """SELECT model, count(*) AS calls, coalesce(sum(output_tokens), 0) AS output_tokens,
                  coalesce(sum(input_tokens), 0) AS input_tokens, coalesce(sum(cache_read), 0) AS cache_read,
                  coalesce(sum(cache_write), 0) AS cache_write
           FROM calls WHERE job_id = ANY(%s) GROUP BY model ORDER BY model""", (job_ids,))
    peak = await db.fetchone(
        """SELECT coalesce(max(n), 0) AS peak FROM (
               SELECT sum(d) OVER (ORDER BY ts, d) AS n FROM (
                   SELECT sent_at AS ts, 1 AS d FROM calls WHERE job_id = ANY(%s)
                   UNION ALL SELECT done_at, -1 FROM calls WHERE job_id = ANY(%s)) x) y""", (job_ids, job_ids))
    cost = 0.0
    for m in per_model:
        p = cfg.models[m["model"]].pricing if m["model"] in cfg.models else None
        if p:
            cost += (m["input_tokens"] * p.input + m["output_tokens"] * p.output + m["cache_read"] * p.cache_read
                     + m["cache_write"] * p.cache_write) / 1e6
    return {"jobs": [dict(j) for j in jobs], "calls": dict(calls), "per_model": [dict(m) for m in per_model],
            "peak_in_flight": int(peak["peak"]), "cost": cost}


def print_summary(s: dict, worker_summary: dict | None = None) -> None:
    c = s["calls"]
    print("\n== summary ==")
    for j in s["jobs"]:
        wall = f"{j['wall_s']:.1f}s" if j["wall_s"] is not None else "-"
        q = f"{j['queued_s']:.1f}s" if j["queued_s"] is not None else "-"
        print(f"  {j['job_id']}  {j['priority']:11} {j['state']:9} wall {wall:>8}  waited {q:>7}  {j['label'] or ''}"
              + (f"  ERROR: {j['error']}" if j["error"] else ""))
    span = float(c["span_s"] or 0)
    print(f"  calls {c['calls']} (ok {c['ok']}), rejections {c['rejections']} "
          f"(output {c['rej_output']}, input {c['rej_input']}), truncated {c['truncated']}")
    print(f"  output tokens {c['output_tokens']:,}" + (f" = {c['output_tokens'] / span * 60:,.0f} per minute over {span:.0f}s" if span > 0 else ""))
    print(f"  input tokens {c['input_tokens']:,}, cache read {c['cache_read']:,}, cache write {c['cache_write']:,} "
          f"in {c['cache_writes']} call(s)")
    print(f"  peak calls in flight {s['peak_in_flight']}; cost about ${s['cost']:.2f}")
    if worker_summary:
        a = worker_summary["admission_ms"]
        print(f"  admission round trip: median {a['median']} ms, p95 {a['p95']} ms, max {a['max']} ms; "
              f"ledger checks {worker_summary['checks']}")


async def cmd_load(cfg: Section, args: argparse.Namespace) -> int:
    from .worker import Worker
    db = Db(cfg)
    try:
        if await _tables_missing(db):
            return 1
        total_jobs = args.jobs + args.bulk
        if args.jobs < 0 or args.bulk < 0 or total_jobs < 1 or total_jobs > planner.MAX_JOBS_PER_SUBMIT:
            print(f"submit between 1 and {planner.MAX_JOBS_PER_SUBMIT} jobs at a time (--jobs plus --bulk)")
            return 1
        if not args.dry_run:                  # a dry run reads only
            await sync_models(db, cfg, prune=False)
        flow = await db.fetchone("SELECT * FROM flows WHERE flow_id = %s", (args.flow,))
        if not flow:
            print("flow not found. Run `python -m doc_engine samples` and use the ids it prints.")
            return 1
        # The same choice Activity makes: the published version, else the latest saved one, else the draft.
        run = await planner.runnable(db, flow["flow_id"])
        flow = {**flow, "graph": run["graph"], "name": run["name"], "version": run["version"]}
        which = (f"v{run['version']}, {'published' if run['published'] else 'latest saved version, not published'}"
                 if run["version"] else "draft, no version saved")
        # --document ID (used for every source), or --document "Source name=ID" once per source
        try:
            by_source = _pairs(args.document, "--document", bare_ok=True)
        except ValueError as e:
            print(e)
            return 1
        default_id = next((d for d in args.document if "=" not in d), None)
        try:
            documents = await planner.resolve_documents(db, flow["graph"], by_source, default_id)
        except ValueError as e:
            print(f"{e}. Run `python -m doc_engine samples` and use the ids it prints.")
            return 1
        try:                                  # --value "Name=value", once per value input
            values = flows.resolve_values(flow["graph"], _pairs(args.value, "--value"),
                                          int(cfg.worker.get("max_value_chars", 20000)))
        except ValueError as e:
            print(f"{e}\nGive values as --value \"Name=value\".")
            return 1
        rows = await db.fetch("SELECT * FROM profiles")
        est = flows.estimate(flow["graph"], {k: d["pages"] for k, d in documents.items()}, cfg, flow["flow_id"],
                             {r["profile_key"]: r for r in rows},
                             keep_ratios=await planner.keep_ratios(db, flow["flow_id"]),
                             page_tokens={k: float(d["page_tokens"]) for k, d in documents.items() if d.get("page_tokens")})
        print(f"flow: {flow['name']} ({which})   " + "   ".join(f"document: {d['name']} ({d['pages']} pages)" for d in documents.values()))
        if values:
            print("values: " + ", ".join(f"{k} = {flows.render_value(v)}" for k, v in values.items()))
        print(f"jobs: {args.jobs} interactive + {args.bulk} bulk")
        print(f"per job: {est['calls']} calls, about {est['output_tokens']:,.0f} output tokens, about ${est['cost']:.2f}")
        print(f"total:   {est['calls'] * total_jobs} calls, about {est['output_tokens'] * total_jobs:,.0f} output tokens, "
              f"about ${est['cost'] * total_jobs:.2f}")
        if args.dry_run:
            return 0
        if total_jobs >= int(cfg.server.get("saturating_jobs", 4)) and not args.confirm_saturation:
            print("\nThis run can saturate the endpoint and throttle other applications in the workspace.\n"
                  "Re-run with --confirm-saturation when you are ready to start it.")
            return 2

        worker = None
        if not args.no_worker:
            worker = Worker(cfg, db)
            await worker.start()
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        hits = {"n": 0}

        def on_sigint() -> None:
            hits["n"] += 1
            if hits["n"] == 1:
                print("\nstopping cleanly (Ctrl+C again to abort)...")
                stop.set()
            else:
                sys.exit(130)
        try:
            loop.add_signal_handler(signal.SIGINT, on_sigint)
        except NotImplementedError:
            pass

        job_ids = []
        for i in range(total_jobs):
            pr = "interactive" if i < args.jobs else "bulk"
            job_ids.append(await planner.submit_job(
                db, cfg, graph=flow["graph"], flow_id=flow["flow_id"], flow_name=flow["name"],
                flow_version=flow["version"], documents=documents, priority=pr, label=f"{args.label} {pr} {i + 1}".strip(),
                values=values, values_resolved=True))
        if worker:
            worker.nudge()
        print(f"submitted {len(job_ids)} job(s)")
        t0 = time.monotonic()
        last = 0.0
        while not stop.is_set():
            await asyncio.sleep(0.5)
            r = await db.fetchone(
                "SELECT count(*) FILTER (WHERE state IN ('queued','running')) AS open, "
                "count(*) FILTER (WHERE state = 'done') AS done FROM jobs WHERE job_id = ANY(%s)", (job_ids,))
            if time.monotonic() - last >= 5:
                last = time.monotonic()
                c = await db.fetchone("SELECT count(*) FILTER (WHERE outcome='ok') AS ok, count(*) FILTER (WHERE outcome='429') AS rej "
                                      "FROM calls WHERE job_id = ANY(%s)", (job_ids,))
                print(f"  t+{time.monotonic() - t0:5.0f}s  jobs done {r['done']}/{len(job_ids)}  calls ok {c['ok']}  "
                      f"rejections {c['rej']}  in flight {worker.summary()['in_flight'] if worker else '-'}")
            if r["open"] == 0:
                break
        if stop.is_set():
            for j in job_ids:
                await planner.cancel_job(db, j)
        ws = worker.summary() if worker else None
        if worker:
            await worker.stop()
        print_summary(await run_summary(db, cfg, job_ids), ws)
    finally:
        await db.close()
    return 0


async def cmd_worker(cfg: Section, args: argparse.Namespace) -> int:
    from .worker import Worker
    db = Db(cfg)
    try:
        if await _tables_missing(db):
            await db.close()
            return 1
        await sync_models(db, cfg, prune=False)      # only the application removes a model's quota row
        w = Worker(cfg, db)
        await w.start()
    except BaseException:
        await db.close()
        raise
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    print(f"worker {w.worker_id} running. Ctrl+C stops it cleanly.")
    try:
        await stop.wait()
        await w.stop()
    finally:
        await db.close()
    return 0


async def cmd_export(cfg: Section, args: argparse.Namespace) -> int:
    db = Db(cfg)
    try:
        if await _tables_missing(db):
            return 1
        if not await db.fetchone("SELECT 1 AS x FROM jobs WHERE job_id = %s", (args.job,)):
            print(f"job not found: {args.job}. `python -m doc_engine jobs` lists recent job ids.")
            return 1
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for table in ("jobs", "job_steps", "tasks", "calls", "events", "reservations"):
            cols = "*" if table not in ("jobs",) else \
                "job_id, flow_id, flow_name, flow_version, document_name, pages, priority, state, label, error, submitted_at, started_at, finished_at"
            rows = await db.fetch(f"SELECT {cols} FROM {table} WHERE job_id = %s", (args.job,))
            with (out / f"{table}.csv").open("w", newline="") as f:
                if rows:
                    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    w.writeheader()
                    for r in rows:
                        w.writerow({k: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v for k, v in r.items()})
            print(f"  {table}.csv  {len(rows)} rows")
        print(f"written to {out}")
    finally:
        await db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print(f"Document Engine needs Python 3.11 or newer. This is Python {sys.version.split()[0]}.")
        return 1
    ap = argparse.ArgumentParser(prog="python -m doc_engine", description="Document Engine")
    ap.add_argument("--config", help="path to the config file (default: config.yaml, or DOC_ENGINE_CONFIG)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("db", help="create, check or remove the tables")
    p.add_argument("action", choices=["init", "check", "reset"])
    p.add_argument("--yes", action="store_true")

    p = sub.add_parser("samples", help="create the sample flows and documents")
    p.add_argument("--force", action="store_true", help="rebuild them even if present")

    sub.add_parser("preflight", help="check the config, the database and each model on the gateway")
    sub.add_parser("serve", help="run the web application")
    sub.add_parser("worker", help="run a worker process without the web application")

    p = sub.add_parser("jobs", help="list recent jobs")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("load", help="submit several jobs at once and report the result")
    p.add_argument("--flow", required=True)
    p.add_argument("--document", required=True, action="append",
                   help="document id; for a flow with several sources repeat as \"Source name=ID\"")
    p.add_argument("--value", action="append", default=[],
                   help="a value input as \"Name=value\"; repeat for each. Inputs left out take their default")
    p.add_argument("--jobs", type=int, default=1, help="interactive jobs")
    p.add_argument("--bulk", type=int, default=0, help="bulk jobs")
    p.add_argument("--label", default="load")
    p.add_argument("--dry-run", action="store_true", help="print calls and cost, send nothing")
    p.add_argument("--confirm-saturation", action="store_true")
    p.add_argument("--no-worker", action="store_true", help="only submit; a running app or worker does the work")

    p = sub.add_parser("probe", help="measure the gateway")
    p.add_argument("what", choices=["bucket"])
    p.add_argument("--model", required=True)
    p.add_argument("--calls", type=int, default=300)
    p.add_argument("--spacing", type=float, default=None,
                   help="seconds between calls (default: chosen from the model's OTPM)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--confirm-saturation", action="store_true")

    p = sub.add_parser("export", help="write a job's rows to CSV files")
    p.add_argument("--job", required=True)
    p.add_argument("--out", required=True)

    args = ap.parse_args(argv)
    _setup_logging(args.verbose)
    cfg = load_config(args.config)

    if args.cmd == "serve":
        from .api import serve
        return serve(cfg)
    if args.cmd == "preflight":
        from .preflight import cmd_preflight
        return asyncio.run(cmd_preflight(cfg))
    if args.cmd == "probe":
        from .preflight import cmd_probe_bucket
        return asyncio.run(cmd_probe_bucket(cfg, args))
    fn = {"db": cmd_db, "samples": cmd_samples, "jobs": cmd_jobs, "load": cmd_load, "worker": cmd_worker,
          "export": cmd_export}[args.cmd]
    if args.cmd != "db" and placeholders(cfg):
        print("config still has FILL-IN values: " + ", ".join(placeholders(cfg)))
    return asyncio.run(fn(cfg, args))
