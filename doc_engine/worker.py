"""The worker: asks the ledger for the next task, makes the call, records what happened.

One dispatcher loop per process asks for admission, so a blocked queue is checked by one waiter
instead of by every idle worker (the POC made 108K to 178K blocked checks per saturated run).
While blocked it sleeps until a completion wakes it, or until the time the ledger says the head
task could fit.

Rules kept from the POC:
  - a 429 returns the task to ready without using an attempt, and pauses the model for everyone
  - timeouts and server errors retry up to a cap
  - refusals, empty replies and other permanent errors fail the job
  - a failed warm-up releases the calls that waited for it
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
import uuid
from collections import OrderedDict, deque
from typing import Any

import jsonschema
import psycopg

from . import flows, planner, prompts
from .config import Section
from .db import DatabaseUnavailable, Db, Jsonb
from .documents import DocumentCache
from .gateway import CallResult, call_cost, execute_call, make_client

log = logging.getLogger("doc_engine.worker")


class Worker:
    def __init__(self, cfg: Section, db: Db) -> None:
        self.cfg = cfg
        self.db = db
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.concurrency = int(cfg.worker.get("concurrency", 128))
        self.client = make_client(cfg)
        self.docs = DocumentCache(db)
        self._wake = asyncio.Event()
        self._stop = asyncio.Event()
        self._inflight: dict[int, asyncio.Task] = {}
        self._bg: list[asyncio.Task] = []
        self._jobs: OrderedDict[str, dict] = OrderedDict()
        self.admit_ms: deque[float] = deque(maxlen=5000)
        self.peak_inflight = 0
        self.stats = {"admitted": 0, "blocked": 0, "held": 0, "empty": 0}

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        await self.db.execute(
            "INSERT INTO workers (worker_id, info) VALUES (%s, %s) ON CONFLICT (worker_id) DO UPDATE SET heartbeat_at = clock_timestamp()",
            (self.worker_id, Jsonb({"concurrency": self.concurrency, "pid": os.getpid()})))
        log.info("worker %s starting: concurrency=%d", self.worker_id, self.concurrency)
        self._bg = [asyncio.create_task(self._heartbeat(), name="heartbeat"),
                    asyncio.create_task(self._reaper(), name="reaper"),
                    asyncio.create_task(self._listen(), name="listen"),
                    asyncio.create_task(self._dispatch(), name="dispatch")]

    async def stop(self) -> None:
        """Clean stop: in-flight calls are cancelled, their reservations closed, their tasks returned to ready."""
        self._stop.set()
        self._wake.set()
        for t in self._bg:
            t.cancel()
        tasks = list(self._inflight.values())
        for t in tasks:
            t.cancel()
        await asyncio.gather(*self._bg, *tasks, return_exceptions=True)
        try:
            await self.db.execute("DELETE FROM workers WHERE worker_id = %s", (self.worker_id,))
            # A clean stop returns this worker's calls to the queue; it never sets one aside as lost.
            await self.db.execute("SELECT de_reap(%s, 0)", (float(self.cfg.ledger.get("dead_worker_after_s", 30)),))
        except Exception:
            log.exception("worker cleanup failed")
        await self.client.close()
        log.info("worker %s stopped", self.worker_id)

    def nudge(self) -> None:
        self._wake.set()

    # ------------------------------------------------------------ background loops

    async def _heartbeat(self) -> None:
        while not self._stop.is_set():
            try:
                await self.db.execute(
                    "INSERT INTO workers (worker_id) VALUES (%s) ON CONFLICT (worker_id) DO UPDATE SET heartbeat_at = clock_timestamp()",
                    (self.worker_id,))
            except Exception as e:
                log.warning("heartbeat failed: %s", e)
            await asyncio.sleep(5)

    async def _reaper(self) -> None:
        interval = float(self.cfg.ledger.get("reaper_interval_s", 5))
        dead = float(self.cfg.ledger.get("dead_worker_after_s", 30))
        max_rec = int(self.cfg.ledger.get("max_recoveries_per_call", 3) or 0)
        while not self._stop.is_set():
            await asyncio.sleep(interval)
            try:
                row = await self.db.fetchone("SELECT de_reap(%s, %s) AS n", (dead, max_rec))
                if row and row["n"]:
                    log.warning("returned %d task(s) to the queue after a lost worker or lease", row["n"])
                    self.nudge()
                await self._fail_lost_too_often()      # every round, so one left by a stopped process is picked up
                await self.db.execute("DELETE FROM workers WHERE heartbeat_at < clock_timestamp() - interval '10 minutes'")
            except Exception as e:
                log.warning("reaper failed: %s", e)

    async def _fail_lost_too_often(self) -> None:
        """Fails the job of a call the reaper set aside as 'lost', so it cannot circulate for ever."""
        cfg = self.cfg
        for r in await self.db.fetch("SELECT task_id, job_id FROM tasks WHERE state = 'lost'"):

            async def go(conn: psycopg.AsyncConnection, r=r) -> None:
                cur = await conn.execute("SELECT * FROM jobs WHERE job_id = %s FOR UPDATE", (r["job_id"],))
                job = await cur.fetchone()
                cur = await conn.execute(
                    "SELECT * FROM tasks WHERE task_id = %s AND state = 'lost' FOR UPDATE", (r["task_id"],))
                task = await cur.fetchone()
                if task is None or job is None:
                    return
                err = (f"this call was returned to the queue {task['recoveries']} times because the worker sending it "
                       f"stopped each time. It was not sent again.")
                await conn.execute(
                    "UPDATE tasks SET state = 'failed', error = %s, finished_at = clock_timestamp() WHERE task_id = %s",
                    (err, task["task_id"]))
                await planner.emit(conn, "task_failed", job_id=task["job_id"], node_id=task["node_id"],
                                   task_id=task["task_id"], model=task["model"],
                                   data={"outcome": "lost", "error": err, "kind": task["kind"]})
                if task["kind"] == "warmup":     # caching is optional; the step's calls run without it
                    await planner.warm_lock(conn, task["model"], (task.get("payload") or {}).get("prefix_hash"))
                    await planner.release_gated(conn, cfg, task)
                else:
                    await planner.release_gated(conn, cfg, task)
                    title = flows.nodes_by_id(job["graph"]).get(task["node_id"], {}).get("data", {}).get("title") or task["node_id"]
                    await planner.fail_job(conn, task["job_id"], f"{title}: {err}")
            await self.db.tx(go)

    async def _listen(self) -> None:
        """Wakes the dispatcher when another process completes a call or submits a job."""
        while not self._stop.is_set():
            conn = None
            try:
                conn = await self.db.connect()
                await conn.execute("LISTEN de_wake")
                async for _ in conn.notifies():
                    self._wake.set()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("notification listener lost (%s); relying on timed checks, retrying in 5 s", str(e).strip())
                await asyncio.sleep(5)
            finally:
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass

    async def _wait(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self._wake.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        self._wake.clear()

    async def _dispatch(self) -> None:
        lease_s = float(self.cfg.ledger.get("lease_s", 900))
        while not self._stop.is_set():
            if len(self._inflight) >= self.concurrency:
                await self._wait(1.0)
                continue
            try:
                t0 = time.monotonic()
                row = await self.db.fetchone("SELECT de_admit(%s, %s) AS r", (self.worker_id, lease_s))
                r = row["r"]
                ms = (time.monotonic() - t0) * 1000
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("admission failed: %s", e)
                await asyncio.sleep(1.0)
                continue
            kind = r["kind"]
            self.stats[kind] = self.stats.get(kind, 0) + 1
            if kind == "admitted":
                self.admit_ms.append(ms)
                task = r["task"]
                t = asyncio.create_task(self._run(task, r["reservation_id"]), name=f"task-{task['task_id']}")
                self._inflight[task["task_id"]] = t
                self.peak_inflight = max(self.peak_inflight, len(self._inflight))
                continue
            await self._wait(1.0 if kind == "empty" else float(r.get("wait_s") or 0.25))

    # ------------------------------------------------------------ one task

    async def _job(self, job_id: str) -> dict:
        j = self._jobs.get(job_id)
        if j is None:
            j = await self.db.fetchone(
                "SELECT job_id, flow_id, graph, document_id, document_name, pages, documents, priority_rank, submitted_at "
                "FROM jobs WHERE job_id = %s", (job_id,))
            if j is None:
                raise KeyError(f"job {job_id} not found")
            j["nodes"] = flows.nodes_by_id(j["graph"])
            j["documents"] = planner.job_documents(j)
            j["multi"] = flows.multi_source(j["graph"])
            self._jobs[job_id] = j
            while len(self._jobs) > 200:
                self._jobs.popitem(last=False)
        return j

    async def _run(self, task: dict, reservation_id: int) -> None:
        tid = task["task_id"]
        try:
            res, parsed, thinking = await self._call(task)
            await asyncio.shield(self._record_patiently(task, reservation_id, res, parsed, thinking))
        except asyncio.CancelledError:
            await asyncio.shield(self._return_to_queue(task, reservation_id, "cancelled"))
            raise
        except DatabaseUnavailable as e:
            # The database was away while the call was being prepared. That says nothing about the call:
            # it goes back to the queue (by the reaper if this fails too) and the job carries on.
            log.error("task %s: the database was not reachable (%s); returning it to the queue", tid, e)
            await self._return_to_queue(task, reservation_id, "error")
        except Exception as e:
            log.exception("task %s failed inside the worker", tid)
            res = CallResult(outcome="permanent", error={"message": f"worker error: {type(e).__name__}: {e}"})
            from datetime import datetime, timezone
            res.sent_at = res.done_at = datetime.now(timezone.utc)
            try:
                await self._record(task, reservation_id, res, None, None)
            except Exception:
                log.exception("could not record the failure of task %s", tid)
                await self._return_to_queue(task, reservation_id, "error")
        finally:
            self._inflight.pop(tid, None)
            self._wake.set()

    async def _record_patiently(self, task: dict, reservation_id: int, res: CallResult, parsed: Any,
                                thinking: str | None) -> None:
        """Records a reply, waiting out a database interruption. The reply is already paid for, so it is
        kept and tried again for about a minute. If the database is still away, the task goes back to the
        queue (by the reaper if need be) and the call is made again; the job does not fail."""
        pauses = [1, 3, 6, 10, 15, 25]
        for i in range(len(pauses) + 1):
            try:
                await self._record(task, reservation_id, res, parsed, thinking)
                return
            except (DatabaseUnavailable, psycopg.OperationalError, psycopg.InterfaceError, OSError) as e:
                if i == len(pauses):
                    log.error("task %s: could not record its reply (%s); returning it to the queue", task["task_id"], e)
                    await self._return_to_queue(task, reservation_id, "error")
                    return
                log.warning("task %s: could not record its reply (%s); trying again in %d s",
                            task["task_id"], str(e).strip(), pauses[i])
                await asyncio.sleep(pauses[i])

    async def _call(self, task: dict) -> tuple[CallResult, Any, str | None]:
        job = await self._job(task["job_id"])
        node = job["nodes"].get(task["node_id"])
        if node is None:
            raise KeyError(f"step {task['node_id']} is not in the job's flow")
        step = flows.step_data(node)
        model = task["model"]
        payload = task.get("payload") or {}
        is_warmup = task["kind"] == "warmup"
        multi = job["multi"]
        title = lambda nid: flows.node_title(job["nodes"].get(nid))  # noqa: E731
        if is_warmup:
            params = prompts.warmup_request(self.cfg, step=step, model=model, multi=multi)
            thinking = "off"
        else:
            consume = payload.get("consume", "pages")
            pages = list(task.get("pages") or [])
            src_id = payload.get("src") or flows.lineage_source(job["graph"], task["node_id"])
            doc = job["documents"].get(src_id) or next(iter(job["documents"].values()))
            as_pdf = str(self.cfg.worker.get("send_images_as", "image")).lower() == "pdf"
            material = (await self.docs.material(doc["document_id"], pages, as_pdf)
                        if consume in ("pages", "both") and pages else None)
            sources: list[dict] = []
            if consume in ("outputs", "both") and payload.get("sources"):
                rows = await self.db.fetch(
                    "SELECT task_id, pages, output_text, output_data FROM tasks WHERE task_id = ANY(%s) ORDER BY seq",
                    (payload["sources"],))
                sources = [dict(r, input_name=title(src_id) if multi else None) for r in rows]
            refs: list[dict] = []
            for r in payload.get("refs") or []:
                if r["kind"] == "source":
                    whole = await self.docs.material(r["document_id"], list(range(1, int(r["pages"]) + 1)), as_pdf)
                    refs.append({**r, "material": whole})
                else:
                    rows = await self.db.fetch(
                        "SELECT task_id, pages, output_text, output_data, payload->>'src' AS src FROM tasks "
                        "WHERE task_id = ANY(%s) ORDER BY seq", (r.get("task_ids") or [],)) if r.get("task_ids") else []
                    refs.append({**r, "items": [dict(x, input_name=title(x["src"]) if multi and x["src"] else None)
                                                for x in rows]})
            params = prompts.build_request(self.cfg, step=step, model=model, doc_name=doc["name"],
                                           pages=pages, pdf=None, material=material, sources=sources, refs=refs,
                                           input_name=title(src_id) if multi else None,
                                           instruction=payload.get("instruction"), max_tokens=task["max_tokens"])
            thinking = flows.thinking_label(step["thinking"])

        size = prompts.request_bytes(params)
        limit = float(self.cfg.gateway.get("max_request_mb", 16)) * 1024 * 1024
        if size > limit:
            # The gateway answers an oversized body with a misleading "malformed JSON" 400. Say what it is.
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            res = CallResult(outcome="permanent", sent_at=now, done_at=now,
                             error={"message": f"request is {size / 1048576:.1f} MB; the limit is "
                                               f"{limit / 1048576:.0f} MB. Use a smaller window."})
            res.request_bytes = size
            return res, None, thinking

        mode = str(self.cfg.gateway.get("streaming", "auto")).lower()
        streaming = (mode == "always" or (mode == "auto" and bool(payload.get("stream")))) and not is_warmup

        async def progress(tokens: int) -> None:
            try:
                await self.db.execute(
                    "INSERT INTO events (kind, job_id, node_id, task_id, model, data) VALUES ('task_progress',%s,%s,%s,%s,%s)",
                    (task["job_id"], task["node_id"], task["task_id"], model, Jsonb({"tokens": tokens})))
            except Exception:
                pass

        res = await execute_call(self.client, self.cfg, params, streaming=streaming, is_warmup=is_warmup,
                                 on_progress=progress if streaming else None)
        res.request_bytes = size

        parsed = None
        if res.outcome == "ok" and not is_warmup and step["output"]["type"] == "schema":
            try:
                parsed = prompts.extract_json(res.text)
                jsonschema.validate(parsed, flows.json_schema(step["output"]["fields"]))
            except Exception as e:
                res.outcome = "invalid"
                msg = getattr(e, "message", None) or str(e)
                if res.truncated:
                    # Cut off at max output tokens: the same call would be cut off again, so it is not retried.
                    res.error = {"message": f"the reply was cut off at this step's max output tokens "
                                            f"({task['max_tokens']:,}), so it is not complete. Raise Max output tokens "
                                            f"for the step, or use a smaller window.", "reply": res.text[:2000]}
                else:
                    res.error = {"message": f"the reply did not match the output schema: {msg}"[:1000],
                                 "reply": res.text[:2000]}
        if is_warmup and res.outcome == "ok":
            settle = float(self.cfg.worker.get("warmup_settle_s", 0) or 0)
            if settle > 0:
                await asyncio.sleep(settle)
        return res, parsed, thinking

    async def _record(self, task: dict, reservation_id: int, res: CallResult, parsed: Any, thinking: str | None) -> None:
        """One transaction: the call row, the task's new state, what it unlocks, and the ledger credit."""
        cfg = self.cfg
        tid, job_id, nid, model = task["task_id"], task["job_id"], task["node_id"], task["model"]
        is_warmup = task["kind"] == "warmup"
        max_attempts = int(cfg.worker.get("max_transient_attempts", 3))
        max_rejections = int(cfg.worker.get("max_rejections_per_call", 50) or 0)

        async def go(conn: psycopg.AsyncConnection) -> None:
            cur = await conn.execute("SELECT * FROM jobs WHERE job_id = %s FOR UPDATE", (job_id,))
            job = await cur.fetchone()
            if is_warmup:      # calls of other jobs may be waiting for this warm-up; see planner.warm_lock
                await planner.warm_lock(conn, model, (task.get("payload") or {}).get("prefix_hash"))
            await conn.execute(
                """INSERT INTO calls (task_id, job_id, node_id, model, kind, thinking, sent_at, first_token_at, done_at,
                                      request_bytes, http_status, outcome, limit_type, stop_reason, input_tokens,
                                      output_tokens, cache_read, cache_write, truncated, request_id, error)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (tid, job_id, nid, model, task["kind"], thinking, res.sent_at, res.first_token_at, res.done_at,
                 res.request_bytes, res.http_status, res.outcome, res.limit_type, res.stop_reason,
                 res.input_tokens, res.output_tokens, res.cache_read, res.cache_write, res.truncated, res.request_id,
                 Jsonb(res.error) if res.error else None))

            # The reply counts only if this call still owns the task. A worker that stopped heartbeating has
            # its calls sent again by someone else; when its own reply arrives late, the call row above is
            # kept (the call was paid for) and nothing else changes.
            cur = await conn.execute("SELECT state, reservation_id FROM tasks WHERE task_id = %s FOR UPDATE", (tid,))
            now = await cur.fetchone()
            actual_out: float | None = float(res.output_tokens) if res.outcome in ("ok", "invalid", "empty", "refusal") else 0.0
            counted_in: float | None = float(res.counted_input) if res.outcome in ("ok", "invalid", "empty", "refusal") else 0.0
            if now is None or now["state"] != "running" or now["reservation_id"] != reservation_id:
                await planner.emit(conn, "task_late_reply", job_id=job_id, node_id=nid, task_id=tid, model=model,
                                   data={"outcome": res.outcome, "output_tokens": res.output_tokens})
                # Normally already released when the task was returned to the queue; then this does nothing.
                await conn.execute("SELECT de_release(%s, %s, %s, %s)", (reservation_id, "late", actual_out, counted_in))
                return

            live = job is not None and job["state"] in ("queued", "running")
            rejected = False

            if not live:
                await conn.execute("UPDATE tasks SET state = 'cancelled', lease_owner = NULL, finished_at = clock_timestamp() "
                                   "WHERE task_id = %s", (tid,))
                # Calls of other jobs may be waiting for this warm-up, or for this call as the first of a wave.
                await planner.release_gated(conn, cfg, task)
            elif res.outcome == "ok":
                await conn.execute(
                    """UPDATE tasks SET state = 'done', lease_owner = NULL, lease_expires_at = NULL, output_text = %s,
                              output_data = %s, output_tokens = %s, stop_reason = %s, finished_at = clock_timestamp()
                       WHERE task_id = %s""",
                    (None if is_warmup else res.text, Jsonb(parsed) if parsed is not None else None,
                     res.output_tokens, res.stop_reason, tid))
                if is_warmup:
                    await conn.execute(
                        "INSERT INTO cache_warm (model, prefix_hash, warmed_at) VALUES (%s,%s,clock_timestamp()) "
                        "ON CONFLICT (model, prefix_hash) DO UPDATE SET warmed_at = excluded.warmed_at",
                        (model, (task.get("payload") or {}).get("prefix_hash", "")))
                else:
                    if task.get("profile_key"):
                        await _learn(conn, task["profile_key"], res)
                    h = (task.get("payload") or {}).get("prefix_hash")
                    if h and (res.cache_read or res.cache_write):
                        # Every read keeps the entry alive, so other jobs can keep skipping their warm-up.
                        await conn.execute(
                            "INSERT INTO cache_warm AS c (model, prefix_hash, warmed_at) VALUES (%s,%s,clock_timestamp()) "
                            "ON CONFLICT (model, prefix_hash) DO UPDATE SET warmed_at = excluded.warmed_at "
                            "WHERE c.warmed_at < clock_timestamp() - interval '20 seconds'", (model, h))
                await planner.emit(conn, "task_done", job_id=job_id, node_id=nid, task_id=tid, model=model, data={
                    "kind": task["kind"], "pages": list(task.get("pages") or []), "output_tokens": res.output_tokens,
                    "input_tokens": res.input_tokens, "cache_read": res.cache_read, "cache_write": res.cache_write,
                    "duration_s": round(res.duration_s, 2), "truncated": res.truncated,
                    "cost": round(call_cost(cfg, model, res), 5), "summary": _summary(parsed, res.text)})
                task_now = dict(task)
                await planner.after_task_done(conn, cfg, job, task_now)
            elif res.outcome == "429" and not (max_rejections and task["rejections"] + 1 >= max_rejections):
                await conn.execute(
                    "UPDATE tasks SET state = 'ready', rejections = rejections + 1, lease_owner = NULL, "
                    "lease_expires_at = NULL, reservation_id = NULL WHERE task_id = %s", (tid,))
                rejected = True          # the event is written below, once the length of the pause is known
            elif (res.outcome in ("transient", "invalid") and task["attempts"] + 1 < max_attempts
                  and not (res.outcome == "invalid" and res.truncated)):   # a cut-off reply would be cut off again
                # A gateway error waits before the next attempt, so a short outage does not use every attempt
                # at once. An invalid reply is the model's doing, not the gateway's: it is retried at once.
                delay = _retry_delay(cfg, task["attempts"]) if res.outcome == "transient" else 0.0
                await conn.execute(
                    "UPDATE tasks SET state = 'ready', attempts = attempts + 1, lease_owner = NULL, lease_expires_at = NULL, "
                    "reservation_id = NULL, error = %s, not_before = clock_timestamp() + make_interval(secs => %s) "
                    "WHERE task_id = %s", (_err(res), delay, tid))
                await planner.emit(conn, "task_retry", job_id=job_id, node_id=nid, task_id=tid, model=model,
                                   data={"outcome": res.outcome, "attempt": task["attempts"] + 1, "error": _err(res),
                                         "delay_s": delay})
            else:
                err = _err(res)
                if res.outcome == "429":
                    err = (f"The gateway rejected this call {task['rejections'] + 1} times in a row"
                           f"{' (' + res.limit_type + ' limit)' if res.limit_type else ''}. The call may be larger than "
                           f"the model allows per minute (it sends about {round(task['input_estimate']):,} input tokens), "
                           f"or other work is using the model's quota.")
                counter = "rejections" if res.outcome == "429" else "attempts"
                await conn.execute(
                    f"UPDATE tasks SET state = 'failed', {counter} = {counter} + 1, lease_owner = NULL, lease_expires_at = NULL, "
                    "error = %s, stop_reason = %s, finished_at = clock_timestamp() WHERE task_id = %s",
                    (err, res.stop_reason, tid))
                await planner.emit(conn, "task_failed", job_id=job_id, node_id=nid, task_id=tid, model=model,
                                   data={"outcome": res.outcome, "error": err, "kind": task["kind"]})
                if is_warmup:
                    # Caching is an optimization. The step's calls run without it.
                    await planner.release_gated(conn, cfg, task)
                else:
                    await planner.release_gated(conn, cfg, task)     # other jobs' calls held back behind this one
                    title = (job["graph"] and flows.nodes_by_id(job["graph"]).get(nid, {}).get("data", {}).get("title")) or nid
                    await planner.fail_job(conn, job_id, f"{title}: {err}")

            # Last, so the quota row is locked only for the commit.
            await conn.execute("SELECT de_release(%s, %s, %s, %s)", (reservation_id, res.outcome, actual_out, counted_in))
            if rejected:
                cur = await conn.execute(
                    "SELECT greatest(0, extract(epoch FROM hold_until - clock_timestamp())) AS s FROM quota WHERE model = %s",
                    (model,))
                row = await cur.fetchone()
                await planner.emit(conn, "task_rejected", job_id=job_id, node_id=nid, task_id=tid, model=model,
                                   data={"limit_type": res.limit_type, "hold_s": round(float(row["s"]), 1) if row else None})

        await self.db.tx(go)

    async def _return_to_queue(self, task: dict, reservation_id: int, outcome: str) -> None:
        async def go(conn: psycopg.AsyncConnection) -> None:
            # A call whose job has already ended is not queued again. A warm-up is: calls of other jobs may be
            # waiting for it, and recording its reply is what releases them.
            await conn.execute(
                "UPDATE tasks t SET state = CASE WHEN t.kind <> 'warmup' AND NOT EXISTS (SELECT 1 FROM jobs j "
                "WHERE j.job_id = t.job_id AND j.state IN ('queued', 'running')) THEN 'cancelled' ELSE 'ready' END, "
                "lease_owner = NULL, lease_expires_at = NULL, reservation_id = NULL "
                "WHERE t.task_id = %s AND t.state = 'running' AND t.lease_owner = %s", (task["task_id"], self.worker_id))
            # The cancelled call may still complete at the gateway, so keep its expected output in the level.
            cur = await conn.execute("SELECT counted_output, counted_input FROM reservations WHERE reservation_id = %s",
                                     (reservation_id,))
            r = await cur.fetchone()
            if r:
                await conn.execute("SELECT de_release(%s, %s, %s, %s)",
                                   (reservation_id, outcome, r["counted_output"], r["counted_input"]))
        try:
            await self.db.tx(go)
        except Exception:
            log.exception("could not return task %s to the queue; the reaper will", task["task_id"])

    def summary(self) -> dict:
        ms = sorted(self.admit_ms)

        def pct(p: float) -> float | None:
            return round(ms[min(len(ms) - 1, int(p * len(ms)))], 1) if ms else None

        return {"worker_id": self.worker_id, "concurrency": self.concurrency, "in_flight": len(self._inflight),
                "peak_in_flight": self.peak_inflight, "admission_ms": {"median": pct(0.5), "p95": pct(0.95), "max": pct(1.0)},
                "checks": dict(self.stats)}


def _retry_delay(cfg: Section, attempts_so_far: int) -> float:
    """Seconds to wait before the next attempt after a gateway error: worker.retry_delays_s, last value repeated."""
    delays = list(cfg.worker.get("retry_delays_s", [2, 10, 30]) or [0])
    return max(0.0, float(delays[min(attempts_so_far, len(delays) - 1)]))


def _err(res: CallResult) -> str:
    e = res.error or {}
    msg = e.get("message") or ""
    if not msg and isinstance(e.get("body"), dict):
        msg = str(e["body"].get("message") or e["body"])
    if not msg:
        msg = str(e.get("body") or e.get("text") or res.outcome)
    prefix = {"refusal": "The model declined this request", "empty": "Empty reply",
              "transient": "Gateway error", "permanent": "Request failed", "invalid": "Invalid reply"}.get(res.outcome, res.outcome)
    status = f" (HTTP {res.http_status})" if res.http_status and res.http_status != 200 else ""
    if msg.strip().lower() in ("", res.outcome, prefix.lower()):
        return f"{prefix}{status}"
    return f"{prefix}{status}: {msg}"[:900]


def _summary(parsed: Any, text: str) -> str:
    """A few words about a result for the live feed, e.g. a classification value."""
    if isinstance(parsed, dict):
        for v in parsed.values():
            if isinstance(v, (str, int, float, bool)):
                return str(v)[:60]
            if isinstance(v, list):
                return f"{len(v)} rows"
    return ""


async def _learn(conn: psycopg.AsyncConnection, key: str, res: CallResult) -> None:
    """Running profile of what this step really costs: a plain mean for the first samples, then a moving average."""
    await conn.execute(
        """INSERT INTO profiles AS p (profile_key, n, out_mean, out_var, out_max, in_mean, dur_mean, truncated, updated_at)
           VALUES (%(k)s, 1, %(o)s, 0, %(o)s, %(i)s, %(d)s, %(t)s, now())
           ON CONFLICT (profile_key) DO UPDATE SET
               n = p.n + 1,
               out_mean = p.out_mean + greatest(0.1, 1.0 / (p.n + 1)) * (%(o)s - p.out_mean),
               out_var = (1 - greatest(0.1, 1.0 / (p.n + 1)))
                         * (p.out_var + greatest(0.1, 1.0 / (p.n + 1)) * (%(o)s - p.out_mean) ^ 2),
               out_max = greatest(p.out_max, %(o)s),
               in_mean = p.in_mean + greatest(0.1, 1.0 / (p.n + 1)) * (%(i)s - p.in_mean),
               dur_mean = p.dur_mean + greatest(0.1, 1.0 / (p.n + 1)) * (%(d)s - p.dur_mean),
               truncated = p.truncated + %(t)s,
               updated_at = now()""",
        {"k": key, "o": float(res.output_tokens), "i": float(res.counted_input), "d": float(res.duration_s),
         "t": 1 if res.truncated else 0})
