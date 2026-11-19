"""The web application: a JSON API, a live event stream, and the built frontend.

Live updates are read from the events table, not from process memory, so they are the same on
every instance behind the load balancer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from . import flows, planner, prompts, public_api, samples
from .config import ROOT, Section, public_models
from .db import Db, Jsonb, apply_schema, missing_tables, sync_models
from .documents import DocumentCache, store_document

log = logging.getLogger("doc_engine.api")
STATIC = Path(__file__).resolve().parent / "static"


def _json(o: Any) -> Any:
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if isinstance(o, (bytes, memoryview)):
        return None
    try:
        from decimal import Decimal
        if isinstance(o, Decimal):
            return float(o)
    except Exception:
        pass
    return str(o)


def J(data: Any, status: int = 200) -> Response:
    return Response(json.dumps(data, default=_json), status_code=status, media_type="application/json")


BLANK_GRAPH: dict = {"nodes": [], "edges": [], "inputs": []}       # a new flow starts empty


class EventHub:
    """Fans events out to connected browsers. Polls the events table only while someone is listening."""

    def __init__(self, db: Db, cfg: Section) -> None:
        self.db = db
        self.cfg = cfg
        self.subs: set[tuple[asyncio.Queue, str | None]] = set()
        self.last_id = 0
        self.seen: deque[int] = deque(maxlen=6000)
        self.seen_set: set[int] = set()
        self._task: asyncio.Task | None = None
        self.worker_summary: Any = None      # set by the app: this process's worker figures, or None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="event-hub")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def subscribe(self, job_id: str | None) -> tuple[asyncio.Queue, str | None]:
        sub = (asyncio.Queue(maxsize=5000), job_id)
        self.subs.add(sub)
        return sub

    def unsubscribe(self, sub: tuple[asyncio.Queue, str | None]) -> None:
        self.subs.discard(sub)

    def _push(self, kind: str, payload: dict, job_id: str | None = None) -> None:
        for q, want in list(self.subs):
            if kind == "event" and want is not None and want != job_id:
                continue
            try:
                q.put_nowait((kind, payload))
            except asyncio.QueueFull:
                self.subs.discard((q, want))   # a stalled browser reconnects and catches up from the database

    async def quota(self) -> dict:
        """The quota snapshot, with this process's worker figures (admission timing, peak in flight)."""
        snap = await quota_snapshot(self.db)
        snap["worker"] = self.worker_summary() if self.worker_summary else None
        return snap

    async def _loop(self) -> None:
        row = await self.db.fetchone("SELECT coalesce(max(event_id), 0) AS m FROM events")
        self.last_id = row["m"]
        last_quota = 0.0
        while True:
            try:
                await asyncio.sleep(0.25)
                if not self.subs:
                    continue
                # Ids are handed out before commit, so a row can appear behind a later id. Look back a little.
                rows = await self.db.fetch(
                    "SELECT event_id, ts, kind, job_id, node_id, task_id, model, data FROM events "
                    "WHERE event_id > %s ORDER BY event_id LIMIT 4000", (max(0, self.last_id - 300),))
                for r in rows:
                    eid = r["event_id"]
                    if eid in self.seen_set:
                        continue
                    if len(self.seen) == self.seen.maxlen:
                        self.seen_set.discard(self.seen[0])
                    self.seen.append(eid)
                    self.seen_set.add(eid)
                    self.last_id = max(self.last_id, eid)
                    self._push("event", r, r["job_id"])
                if time.monotonic() - last_quota >= 1.0:
                    last_quota = time.monotonic()
                    self._push("quota", await self.quota())
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("event hub: %s", e)
                await asyncio.sleep(1)


async def quota_snapshot(db: Db) -> dict:
    rows = await db.fetch(
        """SELECT q.model, q.gateway_name, q.otpm, q.itpm, q.in_capacity, q.capacity_mode,
                  -- The cap admission works with. In `duration` mode it is the one the last check used, or, before
                  -- any check, the one a call of the default length would get.
                  CASE WHEN q.capacity_mode = 'duration'
                       THEN coalesce(q.cap_used, (q.bucket_measured + q.otpm / 60.0 * 0.5 * q.default_call_s) * (1 - q.safety_margin))
                       ELSE q.out_capacity END AS out_capacity,
                  greatest(0, q.out_level - extract(epoch FROM clock_timestamp() - q.updated_at) * q.otpm / 60.0) AS out_level,
                  greatest(0, extract(epoch FROM q.hold_until - clock_timestamp())) AS hold_s,
                  q.rejections, q.admissions,
                  coalesce(r.open_output, 0) AS open_output, coalesce(r.open_calls, 0) AS open_calls,
                  coalesce(c.out_60, 0) AS out_60, coalesce(c.in_60, 0) AS in_60, coalesce(c.rej_60, 0) AS rej_60,
                  coalesce(t.ready, 0) AS ready, coalesce(t.ready_interactive, 0) AS ready_interactive,
                  coalesce(t.waiting, 0) AS waiting
           FROM quota q
           LEFT JOIN (SELECT model, sum(counted_output) AS open_output, count(*) AS open_calls
                      FROM reservations WHERE released_at IS NULL GROUP BY model) r USING (model)
           LEFT JOIN (SELECT model, sum(output_tokens) FILTER (WHERE outcome <> '429') AS out_60,
                             sum(input_tokens + cache_write) FILTER (WHERE outcome <> '429') AS in_60,
                             count(*) FILTER (WHERE outcome = '429') AS rej_60
                      FROM calls WHERE done_at > clock_timestamp() - interval '60 seconds' GROUP BY model) c USING (model)
           LEFT JOIN (SELECT model, count(*) FILTER (WHERE state = 'ready') AS ready,
                             count(*) FILTER (WHERE state = 'ready' AND priority_rank = 0) AS ready_interactive,
                             count(*) FILTER (WHERE state = 'waiting') AS waiting
                      FROM tasks WHERE state IN ('ready', 'waiting') GROUP BY model) t USING (model)
           ORDER BY q.model""")
    jobs = await db.fetchone(
        "SELECT count(*) FILTER (WHERE state = 'running') AS running, count(*) FILTER (WHERE state = 'queued') AS queued "
        "FROM jobs WHERE state IN ('queued','running')")
    return {"models": rows, "jobs": jobs, "ts": time.time()}


def create_app(cfg: Section) -> FastAPI:
    db = Db(cfg)
    hub = EventHub(db, cfg)
    docs = DocumentCache(db, max_docs=4, max_windows=200)
    state: dict[str, Any] = {"worker": None}
    hub.worker_summary = lambda: state["worker"].summary() if state["worker"] else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if await missing_tables(db):
            log.info("tables missing: applying the schema")
        await apply_schema(db)            # idempotent; also installs the current admission functions
        await sync_models(db, cfg)
        if (await db.fetchone("SELECT count(*) AS n FROM flows"))["n"] == 0:
            log.info("no flows yet: creating the sample flows and documents")
            await asyncio.to_thread(lambda: None)
            await samples.install_samples(db, cfg)
        hub.start()
        if cfg.worker.get("enabled", True):
            from .worker import Worker
            state["worker"] = Worker(cfg, db)
            await state["worker"].start()
        yield
        if state["worker"]:
            await state["worker"].stop()
        await hub.stop()
        await db.close()

    app = FastAPI(title="Document Engine", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.exception_handler(ValueError)
    async def value_error(_: Request, e: ValueError) -> Response:
        return J({"error": str(e)}, 400)

    def nudge() -> None:
        if state["worker"]:
            state["worker"].nudge()

    # ------------------------------------------------------------ config

    @app.get("/api/health")
    async def health() -> Response:
        """ok only when the database answers and at least one worker process is alive: without a worker,
        jobs are accepted and never processed."""
        row = await db.fetchone(
            "SELECT count(*) AS n FROM workers WHERE heartbeat_at > clock_timestamp() - make_interval(secs => %s)",
            (float(cfg.ledger.get("dead_worker_after_s", 30)),))
        if row["n"] == 0:
            return J({"ok": False, "workers": 0, "problem": "no worker is running, so no job is being processed"}, 503)
        return J({"ok": True, "workers": row["n"]})

    @app.get("/api/config")
    async def config() -> Response:
        return J({"models": public_models(cfg), "saturating_jobs": int(cfg.server.get("saturating_jobs", 4)),
                  "thinking_levels": ["off", "low", "medium", "high"], "rule_ops": list(flows.RULE_OPS),
                  "field_types": list(flows.FIELD_TYPES), "gateway": cfg.gateway.base_url,
                  "capacity_mode": cfg.ledger.get("capacity_mode", "fixed"),
                  "safety_margin": float(cfg.ledger.get("safety_margin_fraction", 0.05))})

    # ------------------------------------------------------------ flows

    async def flow_row(flow_id: str) -> dict:
        row = await db.fetchone("SELECT * FROM flows WHERE flow_id = %s", (flow_id,))
        if row is None:
            raise HTTPException(404, "flow not found")
        # Whether the draft has changed since the latest saved version.
        row["draft_differs"] = False
        if row["version"]:
            v = await db.fetchone("SELECT name, graph FROM flow_versions WHERE flow_id = %s AND version = %s",
                                  (flow_id, row["version"]))
            row["draft_differs"] = (v is None or v["name"] != row["name"]
                                    or flows.meaning(v["graph"]) != flows.meaning(row["graph"]))
        return row

    @app.get("/api/flows")
    async def list_flows() -> Response:
        rows = await db.fetch(
            """SELECT f.flow_id, f.name, f.description, f.version, f.published_version, f.is_sample, f.updated_at,
                      jsonb_array_length(f.graph->'nodes') AS nodes,
                      (SELECT count(*) FROM jobs j WHERE j.flow_id = f.flow_id) AS runs,
                      (SELECT max(submitted_at) FROM jobs j WHERE j.flow_id = f.flow_id) AS last_run
               FROM flows f ORDER BY f.is_sample DESC, f.updated_at DESC""")
        return J(rows)

    @app.post("/api/flows")
    async def create_flow(request: Request) -> Response:
        body = await request.json()
        fid = flows.new_id("flow")
        await db.execute("INSERT INTO flows (flow_id, name, description, graph) VALUES (%s,%s,%s,%s)",
                         (fid, body.get("name") or "Untitled flow", body.get("description") or "",
                          Jsonb(body.get("graph") or BLANK_GRAPH)))
        return J(await flow_row(fid))

    @app.get("/api/flows/{flow_id}")
    async def get_flow(flow_id: str) -> Response:
        row = await flow_row(flow_id)
        row["versions"] = await db.fetch("SELECT version, name, created_at FROM flow_versions WHERE flow_id = %s ORDER BY version DESC", (flow_id,))
        return J(row)

    @app.get("/api/flows/{flow_id}/runnable")
    async def get_runnable(flow_id: str) -> Response:
        """What Activity and `load` run for this flow: the published version, else the latest saved one, else the draft."""
        run = await planner.runnable(db, flow_id)
        if run is None:
            raise HTTPException(404, "flow not found")
        return J(run)

    @app.put("/api/flows/{flow_id}")
    async def save_flow(flow_id: str, request: Request) -> Response:
        body = await request.json()
        row = await flow_row(flow_id)
        await db.execute("UPDATE flows SET name = %s, description = %s, graph = %s, updated_at = now() WHERE flow_id = %s",
                         (body.get("name") or row["name"], body.get("description", row["description"]),
                          Jsonb(body.get("graph") or row["graph"]), flow_id))
        return J(await flow_row(flow_id))

    @app.delete("/api/flows/{flow_id}")
    async def delete_flow(flow_id: str) -> Response:
        await db.execute("DELETE FROM flows WHERE flow_id = %s", (flow_id,))
        return J({"ok": True})

    @app.post("/api/flows/{flow_id}/duplicate")
    async def duplicate_flow(flow_id: str) -> Response:
        row = await flow_row(flow_id)
        fid = flows.new_id("flow")
        await db.execute("INSERT INTO flows (flow_id, name, description, graph) VALUES (%s,%s,%s,%s)",
                         (fid, row["name"] + " (copy)", row["description"], Jsonb(row["graph"])))
        return J(await flow_row(fid))

    @app.post("/api/flows/{flow_id}/versions")
    async def save_version(flow_id: str) -> Response:
        row = await flow_row(flow_id)
        v = row["version"] + 1
        await db.execute("INSERT INTO flow_versions (flow_id, version, name, graph) VALUES (%s,%s,%s,%s)",
                         (flow_id, v, row["name"], Jsonb(row["graph"])))
        await db.execute("UPDATE flows SET version = %s, updated_at = now() WHERE flow_id = %s", (v, flow_id))
        return J(await flow_row(flow_id))

    @app.post("/api/flows/{flow_id}/publish")
    async def publish(flow_id: str) -> Response:
        row = await flow_row(flow_id)
        problems = [p for p in flows.validate(row["graph"], list(cfg.models)) if p["level"] == "error"]
        if problems:
            return J({"error": "Fix the problems before publishing.", "problems": problems}, 400)
        # Callers run a published flow by its name, so two published flows cannot share one.
        others = await db.fetch(
            """SELECT v.name FROM flows f JOIN flow_versions v ON v.flow_id = f.flow_id AND v.version = f.published_version
               WHERE f.published_version IS NOT NULL AND f.flow_id <> %s""", (flow_id,))
        if any(public_api.flow_key(o["name"]) == public_api.flow_key(row["name"]) for o in others):
            raise ValueError(f'Another published flow is already named "{row["name"]}". Callers run a flow by its name, '
                             f'so rename this one before publishing.')
        if not public_api.flow_key(row["name"]):
            raise ValueError("Give the flow a name before publishing. Callers run it by that name.")
        v = row["version"] + 1
        await db.execute("INSERT INTO flow_versions (flow_id, version, name, graph) VALUES (%s,%s,%s,%s)",
                         (flow_id, v, row["name"], Jsonb(row["graph"])))
        await db.execute("UPDATE flows SET version = %s, published_version = %s, updated_at = now() WHERE flow_id = %s",
                         (v, v, flow_id))
        return J(await flow_row(flow_id))

    @app.post("/api/flows/{flow_id}/unpublish")
    async def unpublish(flow_id: str) -> Response:
        """Stops callers from starting new jobs on this flow. Jobs already started carry on."""
        await flow_row(flow_id)
        await db.execute("UPDATE flows SET published_version = NULL, updated_at = now() WHERE flow_id = %s", (flow_id,))
        return J(await flow_row(flow_id))

    @app.post("/api/validate")
    async def validate(request: Request) -> Response:
        body = await request.json()
        graph = body.get("graph") or {}
        # Which steps have a static prompt long enough to be cached, by the rule the planner uses.
        cacheable: dict[str, bool] = {}
        try:
            multi = flows.multi_source(graph)
            for n in graph.get("nodes") or []:
                if n.get("type") == "step":
                    step = flows.step_data(n)
                    if step["model"] in cfg.models:
                        cacheable[n["id"]] = prompts.is_cacheable(cfg, step["model"], prompts.system_text(step, multi))
        except Exception:
            cacheable = {}
        return J({"problems": flows.validate(graph, list(cfg.models)), "cacheable": cacheable})

    @app.post("/api/estimate")
    async def estimate(request: Request) -> Response:
        body = await request.json()
        graph = body.get("graph") or {}
        flow_id = body.get("flow_id")
        # "pages" is one page count for every source, or {source node id: pages}.
        pages = body.get("pages") or 150
        pages = {k: int(v) for k, v in pages.items()} if isinstance(pages, dict) else int(pages)
        # "documents": {source node id: document id}. Images and text files carry their own tokens per page.
        chosen = {k: v for k, v in (body.get("documents") or {}).items() if v}
        page_tokens: dict[str, float] = {}
        if chosen:
            rows = {r["document_id"]: r for r in await db.fetch(
                "SELECT document_id, pages, page_tokens FROM documents WHERE document_id = ANY(%s)", (list(chosen.values()),))}
            if not isinstance(pages, dict):
                pages = {}
            for node_id, doc_id in chosen.items():
                if doc_id in rows:
                    pages[node_id] = rows[doc_id]["pages"]
                    if rows[doc_id]["page_tokens"]:
                        page_tokens[node_id] = float(rows[doc_id]["page_tokens"])
        if body.get("only_node"):
            try:
                graph = flows.prune_to(graph, body["only_node"])
            except ValueError:
                pass
        profs = {r["profile_key"]: r for r in await db.fetch(
            "SELECT * FROM profiles WHERE profile_key LIKE %s", (f"{flow_id or 'adhoc'}:%",))}
        ratios = await planner.keep_ratios(db, flow_id)
        try:
            return J(flows.estimate(graph, pages, cfg, flow_id, profs, ratios, page_tokens))
        except Exception as e:   # an estimate must never break editing
            return J({"calls": 0, "output_tokens": 0, "cost": 0, "per_node": {}, "pages": pages, "error": str(e)})

    # ------------------------------------------------------------ documents

    @app.get("/api/documents")
    async def list_documents(all: bool = False) -> Response:
        # Files that callers of the public endpoint sent are listed only when asked for (the Files screen).
        # jobs: how many runs used the file; active: how many of those are still queued or running.
        return J(await db.fetch(
            """SELECT d.document_id, d.name, d.pages, d.size_bytes, d.is_sample, d.created_at, d.kind, d.via_api,
                      coalesce(u.jobs, 0) AS jobs, coalesce(u.active, 0) AS active
               FROM documents d
               LEFT JOIN (SELECT e.value->>'document_id' AS document_id, count(DISTINCT j.job_id) AS jobs,
                                 count(DISTINCT j.job_id) FILTER (WHERE j.state IN ('queued','running')) AS active
                          FROM jobs j, jsonb_each(j.documents) e GROUP BY 1) u USING (document_id)
               WHERE %s OR NOT d.via_api
               ORDER BY d.is_sample DESC, d.created_at DESC""", (all,)))

    @app.post("/api/documents")
    async def upload(request: Request, name: str = "document.pdf") -> Response:
        """The body is the file itself: a PDF, an image or a text file. The kind is read from the content."""
        data = await request.body()
        if not data:
            raise ValueError("the upload was empty")
        if len(data) > 200 * 1024 * 1024:
            raise ValueError("the file is larger than 200 MB")
        return J(await store_document(db, name, data, cfg=cfg))

    @app.delete("/api/documents/{document_id}")
    async def delete_document(document_id: str) -> Response:
        """Removes an uploaded file. Past runs keep their results; their page views of this file stop working."""
        row = await db.fetchone("SELECT name, is_sample FROM documents WHERE document_id = %s", (document_id,))
        if not row:
            raise HTTPException(404, "file not found")
        if row["is_sample"]:
            raise ValueError("sample files cannot be removed")
        busy = await db.fetchone(
            """SELECT count(*) AS n FROM jobs j WHERE j.state IN ('queued','running')
               AND EXISTS (SELECT 1 FROM jsonb_each(j.documents) e WHERE e.value->>'document_id' = %s)""", (document_id,))
        if busy["n"]:
            raise ValueError(f"{row['name']} is in use by {busy['n']} run{'' if busy['n'] == 1 else 's'} that "
                             f"{'has' if busy['n'] == 1 else 'have'} not finished. Remove it when they are done.")
        await db.execute("DELETE FROM documents WHERE document_id = %s AND NOT is_sample", (document_id,))
        docs.forget(document_id)
        return J({"ok": True})

    @app.get("/api/documents/{document_id}/pages/{page}")
    async def page_pdf(document_id: str, page: int) -> Response:
        """One page as a person sees it: a one-page PDF, the image, or that page of a text file."""
        try:
            data, media_type = await docs.page_view(document_id, page)
        except (KeyError, IndexError):
            raise HTTPException(404, "page not found")
        return Response(data, media_type=media_type, headers={"Cache-Control": "private, max-age=3600",
                                                              "X-Content-Type-Options": "nosniff"})

    # ------------------------------------------------------------ jobs

    @app.post("/api/jobs")
    async def submit(request: Request) -> Response:
        body = await request.json()
        # With a graph (the builder's test run): that graph runs, labelled with a version only when it is
        # exactly that saved version. Without one (Activity): the published version runs, or the latest saved
        # version when the flow is not published, or the draft when no version has been saved.
        flow = await db.fetchone("SELECT * FROM flows WHERE flow_id = %s", (body.get("flow_id"),)) if body.get("flow_id") else None
        graph = body.get("graph")
        flow_name = flow["name"] if flow else body.get("flow_name") or "Unsaved flow"
        flow_version = None
        if graph and flow and flow["version"]:
            latest = await db.fetchone("SELECT graph FROM flow_versions WHERE flow_id = %s AND version = %s",
                                       (flow["flow_id"], flow["version"]))
            if latest and flows.meaning(latest["graph"]) == flows.meaning(graph):
                flow_version = flow["version"]
        elif not graph and flow:
            run = await planner.runnable(db, flow["flow_id"])
            graph, flow_name, flow_version = run["graph"], run["name"], run["version"]
        if not graph:
            raise ValueError("choose a flow")
        if body.get("only_node"):
            graph = flows.prune_to(graph, body["only_node"])
        # One document per source: {"documents": {source id or name: document id}}, or "document_id" for all.
        documents = await planner.resolve_documents(db, graph, body.get("documents"), body.get("document_id"))
        # Value inputs: {"values": {input name: value}}. Checked here so a bad value creates no job at all.
        values = flows.resolve_values(graph, body.get("values"), int(cfg.worker.get("max_value_chars", 20000)))
        n_int = int(body.get("count", 1))
        n_bulk = int(body.get("bulk_count", 0))
        if body.get("priority") == "bulk":
            n_int, n_bulk = 0, max(1, n_int)
        total = n_int + n_bulk
        if n_int < 0 or n_bulk < 0 or total < 1 or total > planner.MAX_JOBS_PER_SUBMIT:
            raise ValueError(f"submit between 1 and {planner.MAX_JOBS_PER_SUBMIT} jobs at a time")
        if total >= int(cfg.server.get("saturating_jobs", 4)) and not body.get("confirm_saturation"):
            return J({"error": "confirmation_required",
                      "message": f"{total} jobs at once can saturate the endpoint and slow other applications in the "
                                 f"workspace. Confirm to start."}, 409)
        ids = []
        for i in range(total):
            pr = "interactive" if i < n_int else "bulk"
            label = body.get("label") or ("Test run" if body.get("graph") else pr.title() if total == 1
                                          else f"{pr.title()} {i + 1 if pr == 'interactive' else i - n_int + 1}")
            ids.append(await planner.submit_job(
                db, cfg, graph=graph, flow_id=flow["flow_id"] if flow else None,
                flow_name=flow_name, flow_version=flow_version, documents=documents, priority=pr, label=label,
                values=values))
        nudge()
        return J({"job_ids": ids})

    JOB_LIST_SQL = """
        SELECT j.job_id, j.flow_id, j.flow_name, j.flow_version, j.document_id, j.document_name, j.pages, j.documents, j.input_values, j.priority,
               j.state, j.label, j.error, j.submitted_at, j.started_at, j.finished_at,
               extract(epoch FROM coalesce(j.finished_at, clock_timestamp()) - j.submitted_at) AS wall_s,
               coalesce(s.tasks_total, 0) AS tasks_total, coalesce(s.tasks_done, 0) AS tasks_done,
               coalesce(c.calls, 0) AS calls, coalesce(c.rejections, 0) AS rejections,
               coalesce(c.output_tokens, 0) AS output_tokens, coalesce(c.in_flight, 0) AS in_flight
        FROM jobs j
        LEFT JOIN LATERAL (SELECT sum(tasks_total) AS tasks_total, sum(tasks_done) AS tasks_done
                           FROM job_steps WHERE job_id = j.job_id) s ON true
        LEFT JOIN LATERAL (SELECT count(*) AS calls, count(*) FILTER (WHERE outcome = '429') AS rejections,
                                  sum(output_tokens) AS output_tokens,
                                  (SELECT count(*) FROM tasks t WHERE t.job_id = j.job_id AND t.state = 'running') AS in_flight
                           FROM calls WHERE job_id = j.job_id) c ON true
    """

    @app.get("/api/jobs")
    async def list_jobs(limit: int = 60) -> Response:
        return J(await db.fetch(JOB_LIST_SQL + " ORDER BY j.submitted_at DESC, j.job_id LIMIT %s", (min(limit, 300),)))

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str, events: bool = True) -> Response:
        job = await db.fetchone(JOB_LIST_SQL + " WHERE j.job_id = %s", (job_id,))
        if job is None:
            raise HTTPException(404, "job not found")
        g = await db.fetchone("SELECT graph FROM jobs WHERE job_id = %s", (job_id,))
        job["graph"] = g["graph"]
        job["steps"] = await db.fetch(
            "SELECT node_id, node_type, title, instruction, model, state, items_in, items_kept, tasks_total, tasks_done, "
            "started_at, finished_at FROM job_steps WHERE job_id = %s", (job_id,))
        job["cost"] = await _job_cost(job_id)
        if events:
            job["events"] = await db.fetch(
                "SELECT event_id, ts, kind, job_id, node_id, task_id, model, data FROM events WHERE job_id = %s "
                "ORDER BY event_id LIMIT 30000", (job_id,))
        return J(job)

    async def _job_cost(job_id: str) -> float:
        rows = await db.fetch(
            "SELECT model, coalesce(sum(input_tokens),0) AS i, coalesce(sum(output_tokens),0) AS o, "
            "coalesce(sum(cache_read),0) AS r, coalesce(sum(cache_write),0) AS w FROM calls WHERE job_id = %s GROUP BY model",
            (job_id,))
        cost = 0.0
        for r in rows:
            if r["model"] in cfg.models:
                p = cfg.models[r["model"]].pricing
                cost += (r["i"] * p.input + r["o"] * p.output + r["r"] * p.cache_read + r["w"] * p.cache_write) / 1e6
        return cost

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel(job_id: str) -> Response:
        await planner.cancel_job(db, job_id)
        return J({"ok": True})

    @app.get("/api/jobs/{job_id}/outputs")
    async def outputs(job_id: str) -> Response:
        data = await job_outputs(job_id)
        if data is None:
            raise HTTPException(404, "job not found")
        return J(data)

    async def job_outputs(job_id: str) -> dict | None:
        job = await db.fetchone("SELECT graph, document_id, document_name, pages, documents, input_values, state FROM jobs "
                                "WHERE job_id = %s", (job_id,))
        if job is None:
            return None
        nodes = flows.nodes_by_id(job["graph"])
        documents = planner.job_documents(job)
        multi = len(documents) > 1
        label = {nid: flows.node_title(nodes.get(nid)) for nid in documents}      # input names
        out = []
        steps = await db.fetch("SELECT node_id, title, state, items FROM job_steps WHERE job_id = %s AND node_type = 'output'", (job_id,))
        steps.sort(key=lambda r: (nodes.get(r["node_id"], {}).get("position") or {}).get("y", 0))
        for st in steps:
            node = nodes.get(st["node_id"], {})
            inc = flows.incoming(job["graph"], st["node_id"])
            feeder = nodes.get(inc[0]["source"]) if inc else None
            fields = flows.step_data(feeder)["output"]["fields"] if feeder and feeder["type"] == "step" else []
            ids = [it["task_id"] for it in (st["items"] or []) if it.get("task_id")]
            tasks = await db.fetch(
                "SELECT task_id, pages, output_text, output_data, stop_reason, output_tokens, payload->>'src' AS src "
                "FROM tasks WHERE task_id = ANY(%s) ORDER BY seq", (ids,)) if ids else []
            for t in tasks:
                t["input"] = label.get(t["src"]) if multi else None
            entry: dict[str, Any] = {"node_id": st["node_id"], "title": st["title"], "state": st["state"],
                                     "format": (node.get("data") or {}).get("format", "text"),
                                     "items": [{"pages": t["pages"], "text": t["output_text"], "data": t["output_data"],
                                                "input": t["input"],
                                                "truncated": t["stop_reason"] == "max_tokens"} for t in tasks]}
            entry["table"] = _table(tasks, fields)
            out.append(entry)
        # "inputs": the documents of this job by input name, in the order the sources are drawn.
        inputs = [{"node_id": n["id"], "input": label[n["id"]], **documents[n["id"]]}
                  for n in flows.sources(job["graph"]) if n["id"] in documents]
        return {"document_id": job["document_id"], "document_name": job["document_name"], "state": job["state"],
                "multi": multi, "inputs": inputs, "outputs": out,
                "values": [{"name": k, "value": v, "text": flows.render_value(v)}
                           for k, v in (job["input_values"] or {}).items()]}

    def _table(tasks: list[dict], fields: list[dict]) -> dict | None:
        """Rows from schema outputs: table fields are flattened, other fields repeat on each row.
        Columns follow the order of the step's schema (stored JSON does not keep key order)."""
        cols: list[str] = ["page"]
        for f in fields:
            if f.get("type") == "table":
                cols.extend(str(c) for c in f.get("columns") or [])
        cols.extend(f["name"] for f in fields if f.get("type") != "table" and f.get("name"))
        rows: list[dict] = []
        for t in tasks:
            d = t["output_data"]
            if not isinstance(d, dict):
                continue
            scalars = {k: v for k, v in d.items() if not isinstance(v, list)}
            lists = {k: v for k, v in d.items() if isinstance(v, list) and v and isinstance(v[0], dict)}
            page = flows_page(t["pages"])
            if t.get("input"):
                page = f"{t['input']} {page}"
            if lists:
                for v in lists.values():
                    for r in v:
                        rows.append({"page": page, **scalars, **r})
            else:
                rows.append({"page": page, **{k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in d.items()}})
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        return {"columns": cols, "rows": rows} if rows else None

    def flows_page(pages: list[int]) -> str:
        from .documents import page_ranges
        return page_ranges(list(pages or []))

    @app.get("/api/jobs/{job_id}/tasks")
    async def job_tasks(job_id: str, node_id: str, limit: int = 200) -> Response:
        return J(await db.fetch(
            "SELECT task_id, kind, seq, state, pages, output_text, output_data, output_tokens, stop_reason, error, "
            "attempts, rejections, extract(epoch FROM finished_at - started_at) AS duration_s FROM tasks "
            "WHERE job_id = %s AND node_id = %s AND kind = 'call' ORDER BY seq LIMIT %s", (job_id, node_id, limit)))

    @app.get("/api/flows/{flow_id}/last-outputs")
    async def last_outputs(flow_id: str, node_id: str) -> Response:
        job = await db.fetchone(
            "SELECT j.job_id FROM jobs j JOIN job_steps s USING (job_id) WHERE j.flow_id = %s AND s.node_id = %s "
            "AND s.tasks_done > 0 ORDER BY j.submitted_at DESC LIMIT 1", (flow_id, node_id))
        if job is None:
            return J({"job_id": None, "tasks": []})
        rows = await db.fetch(
            "SELECT task_id, pages, output_text, output_data, output_tokens, stop_reason FROM tasks "
            "WHERE job_id = %s AND node_id = %s AND kind = 'call' AND state = 'done' ORDER BY seq LIMIT 60",
            (job["job_id"], node_id))
        return J({"job_id": job["job_id"], "tasks": rows})

    # ------------------------------------------------------------ live

    @app.get("/api/quota")
    async def quota() -> Response:
        snap = await quota_snapshot(db)
        snap["worker"] = state["worker"].summary() if state["worker"] else None
        return J(snap)

    @app.get("/api/stream")
    async def stream(request: Request, job_id: str | None = None, after: int = 0) -> StreamingResponse:
        sub = hub.subscribe(job_id)

        async def gen():
            def frame(kind: str, payload: Any) -> bytes:
                return f"event: {kind}\ndata: {json.dumps(payload, default=_json)}\n\n".encode()
            try:
                yield b"retry: 1500\n\n"
                sent: set[int] = set()
                if job_id and after >= 0:
                    for r in await db.fetch(
                            "SELECT event_id, ts, kind, job_id, node_id, task_id, model, data FROM events "
                            "WHERE job_id = %s AND event_id > %s ORDER BY event_id LIMIT 30000", (job_id, after)):
                        sent.add(r["event_id"])
                        yield frame("event", r)
                yield frame("quota", await hub.quota())
                last = time.monotonic()
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        kind, payload = await asyncio.wait_for(sub[0].get(), timeout=10)
                    except asyncio.TimeoutError:
                        yield b": keepalive\n\n"
                        continue
                    if kind == "event" and payload["event_id"] in sent:
                        continue
                    yield frame(kind, payload)
                    if sub not in hub.subs:       # dropped for being slow
                        break
                    last = time.monotonic()
                _ = last
            finally:
                hub.unsubscribe(sub)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------ public endpoint

    public_api.register(app, db, cfg, nudge, job_outputs)

    # ------------------------------------------------------------ frontend

    @app.get("/{path:path}")
    async def spa(path: str) -> Response:
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (STATIC / path).resolve()
        if path and f.is_file() and STATIC.resolve() in f.parents:
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if "/assets/" in str(f) else {}
            return FileResponse(f, headers=headers)
        index = STATIC / "index.html"
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"error": "the frontend has not been built. See README: Frontend."}, status_code=503)

    return app


def serve(cfg: Section) -> int:
    port = int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or cfg.server.get("port", 8000))
    host = cfg.server.get("host", "0.0.0.0")
    print(f"Document Engine on http://{'localhost' if host == '0.0.0.0' else host}:{port}")
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="warning")
    return 0
