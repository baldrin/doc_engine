"""The public endpoint: run a published flow by name, then poll for status and results.

    GET  /api/v1/flows                    the published flows and what each one needs
    GET  /api/v1/flows/{flow}             one flow: its files, values and outputs
    POST /api/v1/flows/{flow}/jobs        start a job; the reply holds the job id
    GET  /api/v1/jobs/{job_id}            status
    GET  /api/v1/jobs/{job_id}/results    the outputs, once the job is done
    POST /api/v1/jobs/{job_id}/cancel     stop a job
    POST /api/v1/files                    store a file for reuse; the reply holds its id

`{flow}` is the flow's name (case, spacing and punctuation do not matter, so "Contract file review" and
"contract-file-review" are the same flow) or its flow id. Only the published version of a flow runs here;
edits made in the builder, a new name included, change nothing for callers until the flow is published again.

Everything a caller sends is checked before a job exists: a refused request creates no job and stores no file
it did not already hold. There are no callbacks; callers poll the status address.
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import UploadFile

from . import flows, planner
from .config import Section
from .db import Db
from .documents import MAX_FILE_BYTES, FileTooLarge, read_body, read_part
from .documents import store_document

ACTIVE = ("queued", "running")


def flow_key(name: Any) -> str:
    """A flow's name as callers may write it: case, spacing and punctuation do not matter."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", str(name or "").lower()).split())


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def contract(flow: dict, graph: dict, base: str = "") -> dict:
    """What a caller needs to know to run a published flow."""
    nodes = flows.nodes_by_id(graph)
    outs = sorted((n for n in graph.get("nodes", []) if n["type"] == "output"),
                  key=lambda n: (n.get("position") or {}).get("y", 0))
    return {
        "name": flow["name"], "flow_id": flow["flow_id"], "version": flow["published_version"],
        "description": flow.get("description") or "",
        "files": [{"name": flows.node_title(n)} for n in flows.sources(graph)],
        "values": [{"name": i["name"], "type": i["type"], "required": i["default"] is None, "default": i["default"],
                    **({"choices": i["choices"]} if i["type"] == "choice" else {}),
                    "description": i.get("description") or ""} for i in flows.value_inputs(graph)],
        "outputs": [{"name": flows.node_title(nodes[n["id"]]), "format": (n.get("data") or {}).get("format", "text")}
                    for n in outs],
        "submit_url": f"{base}/api/v1/flows/{flow['flow_id']}/jobs",
    }


def register(app: FastAPI, db: Db, cfg: Section, nudge: Callable[[], None],
             job_outputs: Callable[[str], Awaitable[dict | None]]) -> None:
    def J(data: Any, status: int = 200) -> Response:
        from .api import J as _J
        return _J(data, status)

    @app.exception_handler(ApiError)
    async def api_error(_: Request, e: ApiError) -> Response:
        return JSONResponse({"error": e.message, "code": e.code, **e.extra}, status_code=e.status)

    def base_url(request: Request) -> str:
        return str(request.base_url).rstrip("/")

    async def published(ref: str) -> tuple[dict, dict]:
        """The flow a caller named and the graph of its published version."""
        # The name callers use is the name the flow had when it was published. Renaming the draft changes
        # nothing for callers until the flow is published again.
        rows = await db.fetch(
            """SELECT f.flow_id, v.name, f.description, f.version, f.published_version FROM flows f
               JOIN flow_versions v ON v.flow_id = f.flow_id AND v.version = f.published_version
               WHERE f.published_version IS NOT NULL""")
        hit = [r for r in rows if r["flow_id"] == ref] or [r for r in rows if flow_key(r["name"]) == flow_key(ref)]
        if not hit:
            drafts = await db.fetch("SELECT flow_id, name FROM flows WHERE published_version IS NULL")
            if any(d["flow_id"] == ref or flow_key(d["name"]) == flow_key(ref) for d in drafts):
                raise ApiError(404, "flow_not_published", f'The flow "{ref}" exists but is not published. '
                                                          f'Publish it in the builder to make it callable.')
            raise ApiError(404, "flow_not_found", f'No published flow is named "{ref}".')
        if len(hit) > 1:
            raise ApiError(409, "flow_name_ambiguous", f'{len(hit)} published flows are named "{ref}". Use a flow id.',
                           flow_ids=[r["flow_id"] for r in hit])
        flow = hit[0]
        v = await db.fetchone("SELECT graph FROM flow_versions WHERE flow_id = %s AND version = %s",
                              (flow["flow_id"], flow["published_version"]))
        if v is None:
            raise ApiError(404, "flow_not_published", f'The published version of "{flow["name"]}" is missing. Publish it again.')
        return flow, v["graph"]

    # ------------------------------------------------------------ flows

    @app.get("/api/v1/flows")
    async def v1_flows(request: Request) -> Response:
        rows = await db.fetch(
            """SELECT f.flow_id, v.name, f.description, f.published_version, v.graph FROM flows f
               JOIN flow_versions v ON v.flow_id = f.flow_id AND v.version = f.published_version
               WHERE f.published_version IS NOT NULL ORDER BY lower(v.name)""")
        return J({"flows": [contract(r, r["graph"], base_url(request)) for r in rows]})

    @app.get("/api/v1/flows/{flow}")
    async def v1_flow(flow: str, request: Request) -> Response:
        f, graph = await published(flow)
        return J(contract(f, graph, base_url(request)))

    # ------------------------------------------------------------ files

    @app.post("/api/v1/files")
    async def v1_upload(request: Request, name: str = "") -> Response:
        """The file as the request body (with ?name=), or as one multipart part named `file`."""
        ctype = request.headers.get("content-type", "")
        if ctype.startswith("multipart/form-data"):
            form = await request.form()
            part = form.get("file")
            if not isinstance(part, UploadFile):
                raise ApiError(400, "invalid_request", 'Send the file as a form part named "file".')
            name = name or part.filename or ""
            data = await _limited(read_part(part, name or "The file"))
        else:
            data = await _limited(read_body(request, name or "The file"))
        if not name:
            raise ApiError(400, "invalid_request", "Give the file a name: add ?name=report.pdf to the address.")
        return J(_file(await _store(name, data)), 201)

    async def _limited(reading: Awaitable[bytes]) -> bytes:
        try:
            return await reading
        except FileTooLarge as e:
            raise ApiError(413, "file_too_large", f"{e}.") from None

    async def _store(name: str, data: bytes) -> dict:
        if not data:
            raise ApiError(400, "invalid_file", f"{name} is empty.")
        if len(data) > MAX_FILE_BYTES:
            raise ApiError(413, "file_too_large", f"{name} is larger than 200 MB.")
        try:
            return await store_document(db, name, data, cfg=cfg, via_api=True)
        except ValueError as e:
            raise ApiError(400, "invalid_file", str(e)) from None

    def _file(d: dict) -> dict:
        return {"file_id": d["document_id"], "name": d["name"], "kind": d.get("kind") or "pdf", "pages": d["pages"]}

    # ------------------------------------------------------------ jobs

    @app.post("/api/v1/flows/{flow}/jobs")
    async def v1_submit(flow: str, request: Request) -> Response:
        f, graph = await published(flow)
        srcs = flows.sources(graph)
        by_key = {flow_key(flows.node_title(n)): n for n in srcs}
        declared = {flows.value_key(i["name"]): i["name"] for i in flows.value_inputs(graph)}
        ctype = request.headers.get("content-type", "")
        uploads: dict[str, tuple[str, bytes]] = {}      # source node id -> (file name, content)
        file_ids: dict[str, str] = {}                   # source node id -> file id
        values: dict[str, Any] = {}
        opts: dict[str, Any] = {}

        def source_for(field: str) -> dict | None:
            if flow_key(field) in by_key:
                return by_key[flow_key(field)]
            return srcs[0] if field == "file" and len(srcs) == 1 else None

        def bad(message: str) -> ApiError:
            return ApiError(400, "invalid_request", message)

        def take_values(raw: Any) -> None:
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except ValueError:
                    raise bad('"values" must be a JSON object, such as {"Price tolerance": 10}.') from None
            if not isinstance(raw, dict):
                raise bad('"values" must be an object of input name to value.')
            values.update(raw)

        if ctype.startswith("multipart/form-data"):
            form = await request.form()
            for field, v in form.multi_items():
                src = source_for(field)
                if isinstance(v, UploadFile):
                    if src is None:
                        raise bad(f'This flow has no file input named "{field}". It takes: '
                                  + ", ".join(flows.node_title(n) for n in srcs) + ".")
                    fname = v.filename or flows.node_title(src)
                    uploads[src["id"]] = (fname, await _limited(read_part(v, fname)))
                elif src is not None:
                    file_ids[src["id"]] = str(v).strip()
                elif field == "values":
                    take_values(v)
                elif field in ("priority", "label"):
                    opts[field] = str(v)
                elif flows.value_key(field) in declared:
                    values[field] = v
                else:
                    raise bad(f'Unknown field "{field}".')
        else:
            try:
                body = await request.json()
            except ValueError:
                raise bad("Send multipart/form-data with the files, or a JSON body with file ids.") from None
            if not isinstance(body, dict):
                raise bad("The JSON body must be an object.")
            for k, v in body.items():
                if k == "files":
                    if not isinstance(v, dict):
                        raise bad('"files" must be an object of file input name to file id.')
                    for name, fid in v.items():
                        src = source_for(name)
                        if src is None:
                            raise bad(f'This flow has no file input named "{name}".')
                        file_ids[src["id"]] = str(fid)
                elif k == "values":
                    take_values(v)
                elif k in ("priority", "label"):
                    opts[k] = str(v)
                else:
                    raise bad(f'Unknown field "{k}".')

        priority = opts.get("priority") or "interactive"
        if priority not in ("interactive", "bulk"):
            raise bad('"priority" must be interactive or bulk.')
        missing = [flows.node_title(n) for n in srcs if n["id"] not in uploads and n["id"] not in file_ids]
        if missing:
            raise bad("A file is needed for: " + ", ".join(missing) + ".")
        # Values first: they cost nothing to check, and a refusal here must not leave new files behind.
        try:
            resolved = flows.resolve_values(graph, values, int(cfg.worker.get("max_value_chars", 20000)))
        except ValueError as e:
            raise ApiError(400, "invalid_values", str(e)) from None
        for nid, fid in file_ids.items():
            if nid not in uploads and not await db.fetchone("SELECT 1 AS x FROM documents WHERE document_id = %s", (fid,)):
                raise ApiError(400, "file_not_found", f'No file has the id "{fid}".')
        stored: list[str] = []
        try:
            for nid, (name, data) in uploads.items():
                d = await _store(name, data)
                if not d.get("reused"):
                    stored.append(d["document_id"])
                file_ids[nid] = d["document_id"]
            documents = await planner.resolve_documents(db, graph, file_ids)
            job_id = await planner.submit_job(
                db, cfg, graph=graph, flow_id=f["flow_id"], flow_name=f["name"], flow_version=f["published_version"],
                documents=documents, priority=priority, label=(opts.get("label") or "API")[:200], values=resolved)
        except Exception as e:
            for fid in stored:      # nothing ran on them: do not keep what the refused request brought
                await db.execute("DELETE FROM documents WHERE document_id = %s AND NOT is_sample", (fid,))
            if isinstance(e, ValueError):
                raise ApiError(400, "invalid_request", str(e)) from None
            raise
        nudge()
        base = base_url(request)
        return J({"job_id": job_id, "status": "queued", "flow": f["name"], "flow_version": f["published_version"],
                  "status_url": f"{base}/api/v1/jobs/{job_id}", "results_url": f"{base}/api/v1/jobs/{job_id}/results"}, 202)

    async def job_row(job_id: str) -> dict:
        job = await db.fetchone(
            """SELECT j.job_id, j.flow_name, j.flow_version, j.state, j.priority, j.label, j.error, j.graph, j.documents,
                      j.document_id, j.document_name, j.pages, j.input_values, j.submitted_at, j.started_at, j.finished_at,
                      coalesce(s.planned, 0) AS planned, coalesce(s.done, 0) AS done
               FROM jobs j LEFT JOIN LATERAL (SELECT sum(tasks_total) AS planned, sum(tasks_done) AS done
                                              FROM job_steps WHERE job_id = j.job_id) s ON true
               WHERE j.job_id = %s""", (job_id,))
        if job is None:
            raise ApiError(404, "job_not_found", f'No job has the id "{job_id}".')
        return job

    def status_of(job: dict, base: str) -> dict:
        nodes = flows.nodes_by_id(job["graph"])
        docs = planner.job_documents(job)
        return {
            "job_id": job["job_id"], "status": job["state"], "flow": job["flow_name"], "flow_version": job["flow_version"],
            "priority": job["priority"], "label": job["label"],
            "submitted_at": job["submitted_at"], "started_at": job["started_at"], "finished_at": job["finished_at"],
            # Calls are planned as earlier steps finish, so "planned" grows while a job runs.
            "progress": {"calls_done": int(job["done"]), "calls_planned": int(job["planned"])},
            "error": job["error"],
            "files": [{"input": flows.node_title(n), "file_id": docs[n["id"]]["document_id"], "name": docs[n["id"]]["name"],
                       "kind": docs[n["id"]].get("kind") or "pdf", "pages": docs[n["id"]]["pages"]}
                      for n in flows.sources(job["graph"]) if n["id"] in docs and n["id"] in nodes],
            "values": job["input_values"] or {},
            "status_url": f"{base}/api/v1/jobs/{job['job_id']}",
            "results_url": f"{base}/api/v1/jobs/{job['job_id']}/results",
        }

    @app.get("/api/v1/jobs/{job_id}")
    async def v1_status(job_id: str, request: Request) -> Response:
        return J(status_of(await job_row(job_id), base_url(request)))

    @app.get("/api/v1/jobs/{job_id}/results")
    async def v1_results(job_id: str, request: Request) -> Response:
        job = await job_row(job_id)
        if job["state"] in ACTIVE:
            raise ApiError(409, "job_not_finished", f"The job is {job['state']}. Poll its status until it is done.",
                           job_status=job["state"])
        if job["state"] != "done":
            raise ApiError(409, f"job_{job['state']}", job["error"] or f"The job was {job['state']}.", job_status=job["state"])
        raw = await job_outputs(job_id) or {"outputs": []}
        outs = []
        for o in raw["outputs"]:
            items = [{"pages": it["pages"], **({"input": it["input"]} if it.get("input") else {}),
                      "text": it["text"], "data": it["data"], "truncated": it["truncated"]} for it in o["items"]]
            entry: dict[str, Any] = {"name": o["title"], "format": o["format"],
                                     "text": "\n\n".join(it["text"] for it in items if it["text"]), "items": items}
            if o.get("table"):
                entry["table"] = o["table"]
            outs.append(entry)
        st = status_of(job, base_url(request))
        return J({"job_id": job_id, "status": "done", "flow": st["flow"], "flow_version": st["flow_version"],
                  "finished_at": st["finished_at"], "files": st["files"], "values": st["values"], "outputs": outs})

    @app.post("/api/v1/jobs/{job_id}/cancel")
    async def v1_cancel(job_id: str, request: Request) -> Response:
        await job_row(job_id)
        await planner.cancel_job(db, job_id)
        return J(status_of(await job_row(job_id), base_url(request)))

    @app.api_route("/api/v1/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def v1_unknown(rest: str) -> Response:
        raise ApiError(404, "not_found", f"There is no /api/v1/{rest} here.")


__all__ = ["register", "flow_key", "contract", "ApiError"]
