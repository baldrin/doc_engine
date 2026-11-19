"""Jobs and planning: turns a flow and a document into tasks, one step at a time.

Tasks for a step are created when the step before it finishes, because a filter's result is not
known in advance. Every function here takes an open connection and runs inside the caller's
transaction, with the job row locked, so two completions of one job cannot plan the same step twice.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg

from . import flows, prompts
from .config import Section, model_cfg
from .db import Db, Jsonb

log = logging.getLogger("doc_engine.planner")

PRIORITY_RANK = {"interactive": 0, "bulk": 1}


async def emit(conn: psycopg.AsyncConnection, kind: str, *, job_id: str | None = None, node_id: str | None = None,
               task_id: int | None = None, model: str | None = None, data: dict | None = None) -> None:
    await conn.execute("INSERT INTO events (kind, job_id, node_id, task_id, model, data) VALUES (%s,%s,%s,%s,%s,%s)",
                       (kind, job_id, node_id, task_id, model, Jsonb(data or {})))


def job_documents(job: dict) -> dict[str, dict]:
    """{source node id: {document_id, name, pages}} for a job (jobs from before several sources had one)."""
    docs = job.get("documents") or {}
    if docs:
        return docs
    one = {"document_id": job["document_id"], "name": job["document_name"], "pages": job["pages"]}
    return {n["id"]: one for n in flows.sources(job["graph"])}


async def resolve_documents(db: Db, graph: dict, by_source: dict[str, str] | None = None,
                            default_id: str | None = None) -> dict[str, dict]:
    """The document for every source of a flow. `by_source` is keyed by source node id or by the
    source's name; `default_id` fills any source not named (and is all a one-source flow needs)."""
    by_source = by_source or {}
    out: dict[str, dict] = {}
    for n in flows.sources(graph):
        title = flows.node_title(n)
        doc_id = by_source.get(n["id"]) or by_source.get(title) or default_id
        if not doc_id:
            raise ValueError(f"choose a file for {title}")
        doc = await db.fetchone("SELECT document_id, name, pages, kind, page_tokens FROM documents WHERE document_id = %s",
                                (doc_id,))
        if doc is None:
            raise ValueError(f"the file chosen for {title} was not found")
        out[n["id"]] = doc
    if not out:
        raise ValueError("this flow has no source")
    return out


class CallTooLarge(ValueError):
    """A planned call would send more input than its model accepts in a minute, so it could never be admitted."""


async def runnable(db: Db, flow_id: str) -> dict | None:
    """What runs when a flow is started without a graph of its own: the published version, or the latest
    saved version when none is published, or the draft when no version has been saved.
    Returns {flow_id, name, version (None for the draft), published, graph}."""
    flow = await db.fetchone("SELECT flow_id, name, graph, version, published_version FROM flows WHERE flow_id = %s",
                             (flow_id,))
    if flow is None:
        return None
    v = flow["published_version"] or flow["version"]
    row = await db.fetchone("SELECT name, graph FROM flow_versions WHERE flow_id = %s AND version = %s",
                            (flow_id, v)) if v else None
    if row is None:
        return {"flow_id": flow_id, "name": flow["name"], "version": None, "published": False, "graph": flow["graph"]}
    return {"flow_id": flow_id, "name": row["name"], "version": v, "published": bool(flow["published_version"]),
            "graph": row["graph"]}


async def submit_job(db: Db, cfg: Section, *, graph: dict, flow_id: str | None, flow_name: str,
                     flow_version: int | None, documents: dict[str, dict], priority: str = "interactive",
                     label: str = "", values: dict | None = None) -> str:
    """`documents` maps every source node id of the flow to {document_id, name, pages}.
    `values` holds the flow's value inputs by name; an input left out takes its default."""
    problems = [p for p in flows.validate(graph, list(cfg.models)) if p["level"] == "error"]
    if problems:
        raise ValueError("this flow cannot run yet: " + "; ".join(p["message"] for p in problems))
    # Filled in once, here. The job's copy of the graph holds the values, so nothing later sees a placeholder.
    values = flows.resolve_values(graph, values, int(cfg.worker.get("max_value_chars", 20000)))
    graph = flows.apply_values(graph, values)
    if priority not in PRIORITY_RANK:
        raise ValueError("priority must be interactive or bulk")
    nodes = flows.nodes_by_id(graph)
    srcs = flows.sources(graph)
    for n in srcs:
        if n["id"] not in documents:
            raise ValueError(f"choose a file for {flows.node_title(n)}")
    documents = {n["id"]: {k: documents[n["id"]].get(k) for k in ("document_id", "name", "pages", "kind", "page_tokens")}
                 for n in srcs}
    # A source used as a reference is attached whole to every call of the step that uses it.
    limit = int(cfg.worker.get("max_reference_pages", 100))
    for e in graph.get("edges", []):
        if flows.is_reference(e) and nodes[e["source"]]["type"] == "source" and documents[e["source"]]["pages"] > limit:
            d = documents[e["source"]]
            raise ValueError(
                f"{d['name']} has {d['pages']} pages and is attached whole to every call of "
                f"{flows.node_title(nodes[e['target']])}; the limit is {limit} pages. "
                f"Summarize it in a step first and use that step as the reference.")
    job_id = flows.new_id("job")
    first = documents[srcs[0]["id"]]
    names = ", ".join(d["name"] for d in documents.values())
    total_pages = sum(d["pages"] for d in documents.values())

    async def go(conn: psycopg.AsyncConnection) -> None:
        cur = await conn.execute(
            """INSERT INTO jobs (job_id, flow_id, flow_name, flow_version, graph, document_id, document_name, pages,
                                 documents, input_values, priority, priority_rank, label)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (job_id, flow_id, flow_name, flow_version, Jsonb(graph), first["document_id"], names, total_pages,
             Jsonb(documents), Jsonb(values), priority, PRIORITY_RANK[priority], label))
        job = await cur.fetchone()
        for n in nodes.values():
            d = n.get("data") or {}
            ins = model = None
            if n["type"] == "step":
                e = flows.material_edge(graph, n["id"])
                ins = flows.edge_data(e, nodes[e["source"]]["type"])["instruction"]
                model = flows.step_data(n)["model"]
            is_src = n["type"] == "source"
            await conn.execute(
                "INSERT INTO job_steps (job_id, node_id, node_type, title, instruction, model, state, items_in, planned) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (job_id, n["id"], n["type"], d.get("title") or n["type"].title(), ins, model,
                 "done" if is_src else "waiting", documents[n["id"]]["pages"] if is_src else None, is_src))
        await emit(conn, "job_submitted", job_id=job_id,
                   data={"flow": flow_name, "document": names, "pages": total_pages,
                         "priority": priority, "label": label,
                         "documents": {k: {"name": v["name"], "pages": v["pages"]} for k, v in documents.items()}})
        for n in srcs:                       # every source is ready before anything is planned
            items = [{"pages": [p], "task_id": None, "src": n["id"]} for p in range(1, documents[n["id"]]["pages"] + 1)]
            await conn.execute(
                "UPDATE job_steps SET items = %s, finished_at = clock_timestamp() WHERE job_id = %s AND node_id = %s",
                (Jsonb(items), job_id, n["id"]))
            await emit(conn, "step_done", job_id=job_id, node_id=n["id"], data={"items": len(items), "source": True})
        for n in srcs:
            await plan_from(conn, cfg, job, n["id"])
        await conn.execute("SELECT pg_notify('de_wake', 'submit')")

    await db.tx(go)
    return job_id


async def plan_from(conn: psycopg.AsyncConnection, cfg: Section, job: dict, node_id: str) -> None:
    """A node has finished. Plan every node after it that now has all it needs."""
    graph = job["graph"]
    nodes = flows.nodes_by_id(graph)
    seen: set[str] = set()
    for edge in flows.outgoing(graph, node_id):
        if edge["target"] in nodes and edge["target"] not in seen:
            seen.add(edge["target"])
            await try_plan(conn, cfg, job, nodes[edge["target"]])


async def try_plan(conn: psycopg.AsyncConnection, cfg: Section, job: dict, target: dict) -> None:
    """Plans `target` once: when the node it works through and every node it references are done."""
    graph = job["graph"]
    job_id = job["job_id"]
    edge = flows.material_edge(graph, target["id"])
    if edge is None:
        return
    needed = [edge["source"]] + [r["source"] for r in flows.reference_edges(graph, target["id"])]
    cur = await conn.execute(
        "SELECT node_id, state, planned, items FROM job_steps WHERE job_id = %s AND node_id = ANY(%s)",
        (job_id, needed + [target["id"]]))
    rows = {r["node_id"]: r for r in await cur.fetchall()}
    mine = rows.get(target["id"])
    if mine is None or mine["planned"] or any(rows.get(n, {}).get("state") != "done" for n in needed):
        return
    await conn.execute("UPDATE job_steps SET planned = true WHERE job_id = %s AND node_id = %s", (job_id, target["id"]))
    nodes = flows.nodes_by_id(graph)
    await plan_target(conn, cfg, job, nodes[edge["source"]], edge, target, list(rows[edge["source"]]["items"] or []),
                      {n: list(rows[n]["items"] or []) for n in needed[1:]})


async def plan_target(conn: psycopg.AsyncConnection, cfg: Section, job: dict, src: dict, edge: dict, target: dict,
                      items: list[dict], ref_items: dict[str, list[dict]]) -> None:
    job_id = job["job_id"]
    nid = target["id"]
    if target["type"] == "output":
        await conn.execute(
            "UPDATE job_steps SET state = 'done', items_in = %s, items = %s, started_at = clock_timestamp(), "
            "finished_at = clock_timestamp() WHERE job_id = %s AND node_id = %s",
            (len(items), Jsonb(items), job_id, nid))
        await emit(conn, "step_done", job_id=job_id, node_id=nid, data={"items": len(items), "output": True})
        return
    if target["type"] != "step":
        return

    graph = job["graph"]
    nodes = flows.nodes_by_id(graph)
    documents = job_documents(job)
    multi = flows.multi_source(graph)
    step = flows.step_data(target)
    ed = flows.edge_data(edge, src["type"])
    ins = ed["instruction"]
    kept = None
    n_in = len(items)
    if ins == "filter":
        ids = [it["task_id"] for it in items if it.get("task_id")]
        data_by_task: dict[int, Any] = {}
        if ids:
            cur = await conn.execute("SELECT task_id, output_data FROM tasks WHERE task_id = ANY(%s)", (ids,))
            data_by_task = {r["task_id"]: r["output_data"] for r in await cur.fetchall()}
        items = [it for it in items if flows.rule_matches(ed.get("rule") or {}, data_by_task.get(it.get("task_id")))]
        kept = len(items)
        groups = [[i] for i in range(len(items))]
    elif ins == "reduce":
        groups = [list(range(len(items)))] if items else []
    else:
        groups = flows.windows(len(items), ed["window"], ed["overlap"])

    if not groups:
        await conn.execute(
            "UPDATE job_steps SET state = 'done', items_in = coalesce(%s, items_in), items_kept = %s, items = '[]'::jsonb, "
            "started_at = clock_timestamp(), finished_at = clock_timestamp() WHERE job_id = %s AND node_id = %s",
            (n_in, kept, job_id, nid))
        await emit(conn, "step_planned", job_id=job_id, node_id=nid,
                   data={"tasks": 0, "kept": kept, "instruction": ins})
        await emit(conn, "step_done", job_id=job_id, node_id=nid, data={"items": 0})
        await plan_from(conn, cfg, job, nid)
        return

    model = step["model"]
    mcfg = model_cfg(cfg, model)
    system = prompts.system_text(step, multi)
    static_tokens = flows.text_tokens(system)
    cacheable = prompts.is_cacheable(cfg, model, system)
    per_page = float(mcfg.get("input_tokens_per_page", 1728))
    pkey = flows.profile_key(job.get("flow_id"), nid, model, step["thinking"])
    n = len(groups)

    # Warm-up: one small call writes the static prompt to the cache; the step's calls wait for it.
    gate_id = None
    w = cfg.worker
    h = prompts.prefix_hash(model, system) if cacheable else None
    if (w.get("cache_warmup", True) and cacheable and n >= int(w.get("warmup_min_tasks", 3))):
        cur = await conn.execute(
            "SELECT 1 FROM cache_warm WHERE model = %s AND prefix_hash = %s "
            "AND warmed_at > clock_timestamp() - make_interval(secs => %s)", (model, h, float(w.get("warmup_ttl_s", 240))))
        if await cur.fetchone() is None:
            seq = await _take_seq(conn, job_id, 1)
            cur = await conn.execute(
                """INSERT INTO tasks (job_id, node_id, kind, seq, state, model, priority_rank, job_submitted_at,
                                      max_tokens, expected_output, input_estimate, payload)
                   VALUES (%s,%s,'warmup',%s,'ready',%s,%s,%s,%s,1,%s,%s) RETURNING task_id""",
                (job_id, nid, seq, model, job["priority_rank"], job["submitted_at"],
                 max(1, int(w.get("warmup_max_tokens", 1))), static_tokens, Jsonb({"prefix_hash": h})))
            gate_id = (await cur.fetchone())["task_id"]

    upstream_tokens: dict[int, int] = {}
    if ed["consume"] in ("outputs", "both"):
        ids = [it["task_id"] for it in items if it.get("task_id")]
        if ids:
            cur = await conn.execute("SELECT task_id, coalesce(output_tokens, 0) AS t FROM tasks WHERE task_id = ANY(%s)", (ids,))
            upstream_tokens = {r["task_id"]: r["t"] for r in await cur.fetchall()}

    # References: sent whole with every call of this step.
    refs: list[dict] = []
    ref_tokens = 0.0
    for r in flows.reference_edges(graph, nid):
        rn = nodes[r["source"]]
        if rn["type"] == "source":
            d = documents[rn["id"]]
            refs.append({"kind": "source", "node_id": rn["id"], "label": flows.node_title(rn),
                         "document_id": d["document_id"], "name": d["name"], "pages": d["pages"]})
            ref_tokens += d["pages"] * float(d.get("page_tokens") or per_page)
        else:
            ids = [it["task_id"] for it in ref_items.get(rn["id"], []) if it.get("task_id")]
            refs.append({"kind": "step", "node_id": rn["id"], "label": flows.node_title(rn), "task_ids": ids})
            if ids:
                cur = await conn.execute("SELECT coalesce(sum(output_tokens), 0) AS t FROM tasks WHERE task_id = ANY(%s)", (ids,))
                ref_tokens += float((await cur.fetchone())["t"])

    seq0 = await _take_seq(conn, job_id, n)
    stream = n <= 2
    rows = []
    for i, g in enumerate(groups):
        members = [items[j] for j in g]
        pages = sorted({p for it in members for p in it.get("pages", [])})
        sources = [it["task_id"] for it in members if it.get("task_id")]
        srcs = {it.get("src") for it in members if it.get("src")}
        src_id = next(iter(srcs)) if len(srcs) == 1 else None
        est = 150.0 + (0.0 if cacheable else static_tokens) + ref_tokens
        if ed["consume"] in ("pages", "both"):      # a PDF page costs the model's figure; images and text carry their own
            est += len(pages) * float((documents.get(src_id) or {}).get("page_tokens") or per_page)
        if ed["consume"] in ("outputs", "both"):
            est += sum(upstream_tokens.get(s, 800) for s in sources)
        rows.append((job_id, nid, seq0 + i, "waiting" if gate_id else "ready", model, job["priority_rank"],
                     job["submitted_at"], gate_id, pages,
                     Jsonb({"consume": ed["consume"], "sources": sources, "instruction": ins, "stream": stream,
                            "prefix_hash": h, "src": src_id, "refs": refs}),
                     step["max_tokens"], step["expected_output"], est, pkey))
    # A call above the model's input limit per minute would be rejected every time it was sent. Refuse it here.
    itpm = float(mcfg.get("itpm") or 0)
    biggest = max((r[12] for r in rows), default=0.0)
    if itpm and biggest > itpm:
        raise CallTooLarge(
            f"{flows.node_title(target)}: one call would send about {round(biggest):,} input tokens, and "
            f"{mcfg.get('label', model)} accepts {round(itpm):,} per minute. Use a smaller window, attach less as a "
            f"reference, or summarize the input in an earlier step.")
    async with conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO tasks (job_id, node_id, seq, state, model, priority_rank, job_submitted_at, gate_task_id,
                                  pages, payload, max_tokens, expected_output, input_estimate, profile_key)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)
    await conn.execute(
        "UPDATE job_steps SET items_in = coalesce(%s, items_in), items_kept = %s, tasks_total = %s, instruction = %s "
        "WHERE job_id = %s AND node_id = %s", (n_in, kept, n, ins, job_id, nid))
    if ins == "filter":
        await emit(conn, "filter_applied", job_id=job_id, node_id=nid,
                   data={"kept": kept, "rule": flows.describe_rule(ed.get("rule"))})
    await emit(conn, "step_planned", job_id=job_id, node_id=nid, model=model,
               data={"tasks": n, "kept": kept, "instruction": ins, "warmup": gate_id is not None,
                     "window": ed["window"], "overlap": ed["overlap"], "references": [r["label"] for r in refs]})


async def _take_seq(conn: psycopg.AsyncConnection, job_id: str, n: int) -> int:
    cur = await conn.execute("UPDATE jobs SET next_seq = next_seq + %s WHERE job_id = %s RETURNING next_seq", (n, job_id))
    return (await cur.fetchone())["next_seq"] - n


async def release_gated(conn: psycopg.AsyncConnection, cfg: Section, task: dict) -> int:
    """Tasks that were waiting for this one (a warm-up, or the first of a first wave) become ready."""
    first_wave = int(cfg.worker.get("first_wave_size", 0) or 0)
    if task["kind"] == "warmup" and first_wave > 0:
        cur = await conn.execute(
            "SELECT task_id FROM tasks WHERE gate_task_id = %s AND state = 'waiting' ORDER BY seq", (task["task_id"],))
        ids = [r["task_id"] for r in await cur.fetchall()]
        wave, rest = ids[:first_wave], ids[first_wave:]
        if wave:
            await conn.execute("UPDATE tasks SET state = 'ready', gate_task_id = NULL WHERE task_id = ANY(%s)", (wave,))
        if rest:
            await conn.execute("UPDATE tasks SET gate_task_id = %s WHERE task_id = ANY(%s)", (wave[0], rest))
        return len(wave)
    cur = await conn.execute(
        "UPDATE tasks SET state = 'ready', gate_task_id = NULL WHERE gate_task_id = %s AND state = 'waiting'",
        (task["task_id"],))
    return cur.rowcount


async def after_task_done(conn: psycopg.AsyncConnection, cfg: Section, job: dict, task: dict) -> None:
    """Called with the job row locked, after `task` was marked done."""
    job_id = job["job_id"]
    await release_gated(conn, cfg, task)
    if task["kind"] != "call":
        return
    nid = task["node_id"]
    cur = await conn.execute(
        "UPDATE job_steps SET tasks_done = tasks_done + 1 WHERE job_id = %s AND node_id = %s RETURNING tasks_done, tasks_total",
        (job_id, nid))
    st = await cur.fetchone()
    cur = await conn.execute(
        "SELECT count(*) AS open FROM tasks WHERE job_id = %s AND node_id = %s AND kind = 'call' AND state <> 'done'",
        (job_id, nid))
    if (await cur.fetchone())["open"] > 0:
        return
    cur = await conn.execute(
        "SELECT task_id, pages, payload->>'src' AS src FROM tasks WHERE job_id = %s AND node_id = %s AND kind = 'call' "
        "ORDER BY seq", (job_id, nid))
    items = [{"pages": list(r["pages"]), "task_id": r["task_id"], "src": r["src"]} for r in await cur.fetchall()]
    await conn.execute(
        "UPDATE job_steps SET state = 'done', items = %s, finished_at = clock_timestamp() WHERE job_id = %s AND node_id = %s",
        (Jsonb(items), job_id, nid))
    await emit(conn, "step_done", job_id=job_id, node_id=nid, data={"items": len(items), "tasks": st["tasks_total"]})
    try:
        await plan_from(conn, cfg, job, nid)
    except CallTooLarge as e:
        await fail_job(conn, job_id, str(e))
        return
    await finish_job_if_done(conn, job_id)


async def finish_job_if_done(conn: psycopg.AsyncConnection, job_id: str) -> bool:
    cur = await conn.execute("SELECT count(*) AS open FROM job_steps WHERE job_id = %s AND state <> 'done'", (job_id,))
    if (await cur.fetchone())["open"] > 0:
        return False
    cur = await conn.execute(
        "UPDATE jobs SET state = 'done', finished_at = clock_timestamp() WHERE job_id = %s AND state IN ('queued','running') "
        "RETURNING extract(epoch FROM finished_at - submitted_at) AS wall_s", (job_id,))
    row = await cur.fetchone()
    if row is None:
        return False
    cur = await conn.execute(
        "SELECT count(*) AS calls, count(*) FILTER (WHERE outcome = '429') AS rejections FROM calls WHERE job_id = %s", (job_id,))
    c = await cur.fetchone()
    await emit(conn, "job_done", job_id=job_id,
               data={"wall_s": float(row["wall_s"]), "calls": c["calls"], "rejections": c["rejections"]})
    return True


async def fail_job(conn: psycopg.AsyncConnection, job_id: str, error: str, state: str = "failed") -> None:
    """Stops a job. Calls already in flight finish and are discarded."""
    cur = await conn.execute(
        "UPDATE jobs SET state = %s, error = %s, finished_at = clock_timestamp() WHERE job_id = %s "
        "AND state IN ('queued','running') RETURNING job_id", (state, error, job_id))
    if await cur.fetchone() is None:
        return
    await conn.execute("UPDATE tasks SET state = 'cancelled' WHERE job_id = %s AND state IN ('waiting','ready')", (job_id,))
    await conn.execute(
        "UPDATE job_steps SET state = %s, finished_at = clock_timestamp() WHERE job_id = %s AND state <> 'done'",
        ("cancelled" if state == "cancelled" else "failed", job_id))
    await emit(conn, "job_cancelled" if state == "cancelled" else "job_failed", job_id=job_id, data={"error": error})


async def cancel_job(db: Db, job_id: str) -> None:
    async def go(conn: psycopg.AsyncConnection) -> None:
        await conn.execute("SELECT 1 FROM jobs WHERE job_id = %s FOR UPDATE", (job_id,))
        await fail_job(conn, job_id, "cancelled by the user", state="cancelled")
    await db.tx(go)
