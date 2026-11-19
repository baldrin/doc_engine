"""End-to-end check against the fake gateway. Not collected by pytest; run it directly:

    python tests/e2e.py            # all checks, a few minutes
    python tests/e2e.py --keep     # leave the test schema in place afterwards

It needs a reachable Postgres (the same PG* variables or settings the application uses) and nothing else.
It starts its own fake gateway and its own copy of the application on free ports, and keeps its tables in a
separate schema (`de_e2e`), so a development database is not touched.

Nothing here says anything about the real gateway. It shows that the code still does what it did.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import psycopg
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from doc_engine.config import load_config, postgres_conninfo  # noqa: E402

SCHEMA = "de_e2e"
PY = sys.executable
results: list[tuple[bool, str]] = []
procs: list[subprocess.Popen] = []


class Reply:
    def __init__(self, status: int, body: bytes) -> None:
        self.status_code, self.text = status, body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text[:300]}")


class Http:
    """A few lines of urllib, so the check needs no package the application does not."""

    def __init__(self, base_url: str, timeout: float = 60) -> None:
        self.base, self.timeout = base_url, timeout

    def _send(self, method: str, path: str, body=None, params: dict | None = None) -> Reply:
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return Reply(r.status, r.read())
        except urllib.error.HTTPError as e:
            return Reply(e.code, e.read())

    def get(self, path: str, params: dict | None = None) -> Reply:
        return self._send("GET", path, params=params)

    def post(self, path: str, json=None) -> Reply:  # noqa: A002
        return self._send("POST", path, body=json)

    def upload(self, path: str, data: bytes, params: dict | None = None) -> Reply:
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return Reply(r.status, r.read())
        except urllib.error.HTTPError as e:
            return Reply(e.code, e.read())


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check(ok: bool, what: str, detail: str = "") -> bool:
    results.append((bool(ok), what))
    print(("  ok    " if ok else "  FAIL  ") + what + (f"   [{detail}]" if detail and not ok else ""), flush=True)
    return bool(ok)


def start(cmd: list[str], env: dict, log: Path) -> subprocess.Popen:
    p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log.open("w"), stderr=subprocess.STDOUT)
    procs.append(p)
    return p


def stop(p: subprocess.Popen, hard: bool = False) -> None:
    if p.poll() is None:
        p.send_signal(signal.SIGKILL if hard else signal.SIGTERM)
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
    if p in procs:
        procs.remove(p)


def wait_http(url: str, seconds: float = 40) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        try:
            if Http(url, 2).get("").status_code < 500:
                return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


class App:
    def __init__(self, base: str, conninfo: dict) -> None:
        self.base = base
        self.http = Http(base)
        self.pg = psycopg.connect(**conninfo, options=f"-c search_path={SCHEMA}", autocommit=True)

    def sql(self, q: str, *args) -> list[tuple]:
        return self.pg.execute(q, args).fetchall()

    def sample_files(self, flow_id: str) -> dict[str, str]:
        """The sample file each source of a sample flow names, as the Activity screen prefills them."""
        graph = self.http.get(f"/api/flows/{flow_id}/runnable").json()["graph"]
        return {n["id"]: n["data"]["default_document"] for n in graph["nodes"]
                if n["type"] == "source" and n["data"].get("default_document")}

    def submit(self, flow_id: str, count: int = 1, bulk: int = 0, **extra) -> list[str]:
        r = self.http.post("/api/jobs", json={"flow_id": flow_id, "count": count, "bulk_count": bulk,
                                              "documents": self.sample_files(flow_id),
                                              "confirm_saturation": True, **extra})
        r.raise_for_status()
        return r.json()["job_ids"]

    def wait_jobs(self, ids: list[str], seconds: float = 240) -> list[dict]:
        end = time.time() + seconds
        while True:
            jobs = [self.http.get(f"/api/jobs/{j}", params={"events": "false"}).json() for j in ids]
            if all(j["state"] in ("done", "failed", "cancelled") for j in jobs) or time.time() > end:
                return jobs
            time.sleep(0.5)

    def steps_exact(self, ids: list[str]) -> bool:
        """Every step of every job finished exactly its planned number of tasks."""
        rows = self.sql("SELECT count(*) FROM job_steps WHERE job_id = ANY(%s) AND tasks_done <> tasks_total", ids)
        return rows[0][0] == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep the test schema afterwards")
    ap.add_argument("--rounds", type=int, default=3, help="how many times to run ten jobs at once with a cold cache")
    ap.add_argument("--quota-scale", type=float, default=5, help="multiply the model limits, in the settings and the fake gateway alike")
    ap.add_argument("--speed", type=float, default=25, help="how much faster than life the fake gateway answers")
    args = ap.parse_args()

    base_cfg_path = ROOT / "config.fake.yaml"
    conninfo = {k: v for k, v in postgres_conninfo(load_config(base_cfg_path)).items() if k != "application_name"}
    tmp = Path(tempfile.mkdtemp(prefix="de_e2e_"))
    gw_port, app_port = free_port(), free_port()

    raw = yaml.safe_load(base_cfg_path.read_text())
    raw["gateway"]["base_url"] = f"http://127.0.0.1:{gw_port}"
    raw["server"]["port"] = app_port
    raw["ledger"]["dead_worker_after_s"] = 12   # heartbeats are every 5 seconds
    raw["ledger"]["reaper_interval_s"] = 1
    # Quota drains in real time whatever the gateway's speed, so ten jobs under the real limits take minutes.
    # The settings and the fake gateway are scaled up together: the scheduler is still under pressure, for less time.
    scale = args.quota_scale
    for m in raw["models"].values():
        for k in ("itpm", "otpm", "bucket_capacity_output", "bucket_measured"):
            if m.get(k):
                m[k] = int(m[k] * scale)
    cfg_path = tmp / "config.e2e.yaml"
    cfg_path.write_text(yaml.safe_dump(raw))

    env = {**os.environ, "DOC_ENGINE_CONFIG": str(cfg_path), "FAKE_TOKEN": "x",
           "PGOPTIONS": f"-c search_path={SCHEMA}", "PORT": str(app_port)}
    env.pop("DATABRICKS_APP_PORT", None)

    print(f"logs and settings: {tmp}")
    with psycopg.connect(**conninfo, autocommit=True) as c:
        c.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        c.execute(f"CREATE SCHEMA {SCHEMA}")

    def cli(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run([PY, "-m", "doc_engine", *a], cwd=ROOT, env=env, capture_output=True, text=True)

    try:
        # ---------------------------------------------------------------- commands before and after db init
        print("commands")
        r = cli("jobs")
        check(r.returncode == 1 and "db init" in r.stdout, "`jobs` before `db init` explains what to run", r.stdout + r.stderr)
        r = cli("db", "init")
        check(r.returncode == 0, "`db init` creates the tables", r.stdout + r.stderr)
        r = cli("samples")
        check(r.returncode == 0 and "created" in r.stdout, "`samples` loads the sample flows and files", r.stdout[-400:] + r.stderr[-400:])
        r = cli("export", "--job", "job_nope", "--out", str(tmp / "export"))
        check(r.returncode == 1 and "not found" in r.stdout, "`export` refuses an unknown job id", r.stdout)
        r = cli("load", "--flow", "flow_sample_medical", "--document", "doc_sample_medical_150", "--value", "oops", "--dry-run")
        check(r.returncode == 1 and "Name=value" in r.stdout, "`load` refuses a malformed --value", r.stdout)
        r = cli("load", "--flow", "flow_sample_medical", "--document", "doc_sample_medical_150", "--jobs", "51", "--dry-run")
        check(r.returncode == 1, "`load` refuses more than 50 jobs", r.stdout)
        r = cli("load", "--flow", "flow_sample_medical", "--document", "doc_sample_medical_150", "--dry-run")
        check(r.returncode == 0 and "per job" in r.stdout, "`load --dry-run` prints an estimate", r.stdout + r.stderr[-300:])

        # ---------------------------------------------------------------- start the gateway and the application
        gw = start([PY, "-m", "fake_gateway", "--port", str(gw_port), "--speed", str(args.speed),
                    "--otpm", str(100000 * scale), "--itpm", str(1000000 * scale), "--bucket", str(40000 * scale)],
                   env, tmp / "gateway.log")
        app_proc = start([PY, "-m", "doc_engine", "serve"], env, tmp / "app.log")
        base = f"http://127.0.0.1:{app_port}"
        if not check(wait_http(base + "/api/health"), "the application starts and answers /api/health"):
            print((tmp / "app.log").read_text()[-2000:])
            return 1
        a = App(base, conninfo)
        check(a.http.get("/api/health").json().get("ok") is True, "health reports a live worker")
        check(a.http.get("/").status_code == 200, "the screens are served")

        # ---------------------------------------------------------------- flows and files
        print("flows and files")
        r = a.http.post("/api/flows/flow_sample_contract/versions")
        check(r.status_code == 200 and r.json().get("unchanged") is True and r.json()["version"] == 1,
              "saving a version with nothing changed makes no new version", r.text[:200])
        new = a.http.post("/api/flows", json={"name": "e2e empty"}).json()
        r = a.http.post(f"/api/flows/{new['flow_id']}/versions")
        check(r.status_code == 400 and r.json().get("problems"), "a flow with errors cannot be saved as a version", r.text[:200])
        g = a.http.get("/api/flows/flow_sample_medical").json()["graph"]
        next(n for n in g["nodes"] if n["id"] == "classify")["data"]["max_tokens"] = 0
        probs = a.http.post("/api/validate", json={"graph": g}).json()["problems"]
        check(any("Max output tokens" in p["message"] for p in probs), "max output tokens of 0 is reported", str(probs)[:200])
        r1 = a.http.upload("/api/documents", b"A short note.\nSecond line.", {"name": "e2e note.txt"})
        r2 = a.http.upload("/api/documents", b"A short note.\nSecond line.", {"name": "e2e note.txt"})
        check(r1.status_code == 200 and not r1.json().get("reused") and r2.json().get("reused") is True
              and r1.json()["document_id"] == r2.json()["document_id"], "the same file uploaded twice is stored once")
        r = a.http.upload("/api/documents", b"PK\x03\x04" + b"\x00" * 64 + b"notes.txt", {"name": "bundle.zip"})
        check(r.status_code == 400 and "zip archive" in r.text, "a zip archive gets its own message", r.text[:200])
        r = a.http.upload("/api/documents", b"PK\x03\x04" + b"\x00" * 26 + b"word/document.xml", {"name": "letter.bin"})
        check(r.status_code == 400 and "office file" in r.text, "an office file is still named as one", r.text[:200])

        # ---------------------------------------------------------------- one job of each sample flow
        print("one job per sample flow")
        flows_ = {f["flow_id"]: f["name"] for f in a.http.get("/api/flows").json() if f.get("is_sample")}
        for fid, name in sorted(flows_.items()):
            ids = a.submit(fid)
            job = a.wait_jobs(ids)[0]
            outs = a.http.get(f"/api/jobs/{ids[0]}/outputs").json()
            n_out = len(outs.get("outputs", outs) if isinstance(outs, dict) else outs)
            check(job["state"] == "done" and job["rejections"] == 0 and a.steps_exact(ids) and n_out > 0,
                  f"{name}: done, no rejections, every step complete, has outputs",
                  f"state {job['state']}, error {job.get('error')}, rejections {job['rejections']}, outputs {n_out}")

        # ---------------------------------------------------------------- ten jobs at once
        print("ten jobs at once")
        # Several rounds, each with a cold cache, so the ten jobs need their warm-ups at the same moment. A job
        # waiting for another job's warm-up is the kind of thing that goes wrong one time in a few.
        for rnd in range(args.rounds):
            a.sql("DELETE FROM cache_warm RETURNING 1")
            ids = a.submit("flow_sample_contract", count=5, bulk=5)
            jobs = a.wait_jobs(ids, 300)
            sent, distinct = a.sql("SELECT count(*), count(DISTINCT (model, payload->>'prefix_hash')) FROM tasks "
                                   "WHERE job_id = ANY(%s) AND kind = 'warmup'", ids)[0]
            stuck = a.sql("SELECT count(*) FROM tasks WHERE job_id = ANY(%s) AND state = 'waiting'", ids)[0][0]
            ok = all(j["state"] == "done" for j in jobs) and sent == distinct and sent > 0
            check(ok, f"round {rnd + 1}: ten jobs with a cold cache all finish and share one warm-up per prompt",
                  f"{sent} warm-ups for {distinct} prompts; {stuck} calls still waiting; "
                  f"{[j['state'] for j in jobs if j['state'] != 'done']}")
            if not ok:
                bad_ids = [j["job_id"] for j in jobs if j["state"] != "done"]
                print("    calls of the unfinished jobs, by state:", a.sql(
                    "SELECT kind, state, model, count(*), min(not_before - clock_timestamp()), max(recoveries), "
                    "max(rejections), max(attempts) FROM tasks WHERE job_id = ANY(%s) GROUP BY 1,2,3 ORDER BY 1,2", bad_ids))
                print("    steps:", a.sql("SELECT job_id, node_id, state, tasks_done, tasks_total, planned FROM job_steps "
                                          "WHERE job_id = ANY(%s) AND state <> 'done'", bad_ids))
                print("    quota:", a.sql("SELECT model, out_level, cap_used, hold_until - clock_timestamp(), hold_streak, "
                                          "(SELECT count(*) FROM reservations r WHERE r.model = q.model AND released_at IS NULL) "
                                          "FROM quota q"))
                print("    workers:", a.sql("SELECT worker_id, clock_timestamp() - heartbeat_at FROM workers"))
                print("    app log tail:\n" + "\n".join((tmp / "app.log").read_text().splitlines()[-25:]))
                for j in ids:
                    a.http.post(f"/api/jobs/{j}/cancel")
                break
        check(all(j["state"] == "done" for j in jobs), "ten jobs (5 interactive, 5 bulk) all finish",
              str([(j["state"], j.get("error")) for j in jobs if j["state"] != "done"]))
        check(sum(j["rejections"] for j in jobs) == 0, "no call was rejected", str(sum(j["rejections"] for j in jobs)))
        check(a.steps_exact(ids), "every step ran exactly its planned calls")
        fin = {j["priority"]: [] for j in jobs}
        for j in jobs:
            fin[j["priority"]].append(j["finished_at"])
        if all(j["finished_at"] for j in jobs):
            check(max(fin["interactive"]) <= max(fin["bulk"]), "interactive jobs finished before the last bulk job")

        # ---------------------------------------------------------------- refusals leave nothing behind
        print("refusals")
        before = a.sql("SELECT count(*) FROM jobs")[0][0]
        r = a.http.post("/api/jobs", json={"flow_id": "flow_sample_three_way", "documents": a.sample_files("flow_sample_three_way"),
                                           "values": {"Price tolerance": "abc"}})
        check(r.status_code == 400, "a bad value is refused", f"{r.status_code} {r.text[:200]}")
        r = a.http.post("/api/jobs", json={"flow_id": "flow_sample_contract", "count": 4,
                                           "documents": a.sample_files("flow_sample_contract")})
        check(r.status_code == 409, "four jobs without confirmation ask for it", f"{r.status_code}")
        r = a.http.post("/api/jobs", json={"flow_id": "flow_sample_contract", "count": 51, "confirm_saturation": True,
                                           "documents": a.sample_files("flow_sample_contract")})
        check(r.status_code == 400, "more than 50 jobs are refused", f"{r.status_code}")
        check(a.sql("SELECT count(*) FROM jobs")[0][0] == before, "none of the refused requests created a job")

        # ---------------------------------------------------------------- cancel
        print("cancel")
        ids = a.submit("flow_sample_medical")
        time.sleep(1.0)
        a.http.post(f"/api/jobs/{ids[0]}/cancel").raise_for_status()
        job = a.wait_jobs(ids, 30)[0]
        time.sleep(1.5)
        left = a.sql("SELECT count(*) FROM tasks WHERE job_id = %s AND state IN ('queued','running')", ids[0])[0][0]
        check(job["state"] == "cancelled" and left == 0, "a cancelled job stops and leaves no waiting calls",
              f"state {job['state']}, tasks left {left}")

        # ---------------------------------------------------------------- the public endpoint
        print("public endpoint")
        r = a.http.post("/api/flows/flow_sample_three_way/publish")
        check(r.status_code == 200, "a flow can be published", f"{r.status_code} {r.text[:200]}")
        slug = "check-an-invoice-against-its-order"
        d = a.http.get(f"/api/v1/flows/{slug}")
        check(d.status_code == 200 and len(d.json().get("files", [])) == 3, "the published flow describes its files")
        r = a.http.post(f"/api/v1/flows/{slug}/jobs", json={"files": {
            "Purchase order": "doc_sample_trade_po", "Delivery note": "doc_sample_trade_delivery",
            "Invoice": "doc_sample_trade_invoice"}, "values": {"Price tolerance": 10}})
        ok = check(r.status_code == 202 and "job_id" in r.json(), "a job starts by flow name", f"{r.status_code} {r.text[:300]}")
        if ok:
            jid = r.json()["job_id"]
            early = a.http.get(f"/api/v1/jobs/{jid}/results")
            a.wait_jobs([jid])
            st = a.http.get(f"/api/v1/jobs/{jid}").json()
            res = a.http.get(f"/api/v1/jobs/{jid}/results")
            check(st["status"] == "done" and res.status_code == 200 and res.json()["outputs"],
                  "status ends at done and results are returned", f"{st.get('status')} {res.status_code}")
            check(early.status_code in (409, 200), "results asked for early answer 409 until the job is done", str(early.status_code))
        before = a.sql("SELECT count(*) FROM jobs")[0][0]
        r = a.http.post(f"/api/v1/flows/{slug}/jobs", json={"files": {"Purchase order": "doc_sample_trade_po"}})
        check(400 <= r.status_code < 500 and a.sql("SELECT count(*) FROM jobs")[0][0] == before,
              "a request missing files is refused and creates no job", f"{r.status_code}")
        a.http.post("/api/flows/flow_sample_compare/unpublish").raise_for_status()
        check(a.http.get("/api/v1/flows/compare-two-medication-lists").status_code == 404,
              "a flow that is not published answers 404")

        # ---------------------------------------------------------------- a worker that dies mid-run
        print("a worker killed mid-run")
        extra = start([PY, "-m", "doc_engine", "worker"], env, tmp / "worker.log")
        time.sleep(3)
        ids = a.submit("flow_sample_medical", count=2, bulk=0, confirm_saturation=True)
        time.sleep(1.2)
        stop(extra, hard=True)
        jobs = a.wait_jobs(ids, 300)
        check(all(j["state"] == "done" for j in jobs), "both jobs finish after a worker is killed",
              str([(j["state"], j.get("error")) for j in jobs]))
        check(a.steps_exact(ids), "no call was lost or counted twice")

        print("a call that keeps losing its worker")
        known = {w[0] for w in a.sql("SELECT worker_id FROM workers")}
        extra = start([PY, "-m", "doc_engine", "worker"], env, tmp / "worker2.log")
        new_id = None
        for _ in range(40):
            new = [w[0] for w in a.sql("SELECT worker_id FROM workers") if w[0] not in known]
            if new:
                new_id = new[0]
                break
            time.sleep(0.25)
        ids = a.submit("flow_sample_medical")
        held = 0
        for _ in range(200):      # until the new worker holds a call of this job, then lose it for the fourth time
            held = len(a.sql("UPDATE tasks SET recoveries = 3 WHERE job_id = %s AND state = 'running' AND lease_owner = %s "
                             "RETURNING 1", ids[0], new_id))
            if held:
                break
            time.sleep(0.05)
        stop(extra, hard=True)
        check(held > 0, "the second worker was holding a call when it was killed")
        job = a.wait_jobs(ids, 120)[0]
        check(job["state"] == "failed" and "returned to the queue" in (job.get("error") or ""),
              "a call lost four times fails its job with a clear message", f"{job['state']}: {job.get('error')}")

        q = {m["model"]: m for m in a.http.get("/api/quota").json()["models"]}
        used = a.sql("SELECT cap_used FROM quota WHERE model = 'sonnet'")[0][0]
        check(used is not None and abs(q["sonnet"]["out_capacity"] - used) < 1,
              "the quota panel reports the cap admission used", f"{q['sonnet']['out_capacity']} vs {used}")

        # ---------------------------------------------------------------- a gateway far smaller than the settings say
        print("rejections (a gateway with a much smaller quota than configured)")
        stop(gw)
        gw = start([PY, "-m", "fake_gateway", "--port", str(gw_port), "--speed", str(args.speed),
                    "--bucket", "6000", "--otpm", "30000"], env, tmp / "gateway-small.log")
        wait_http(f"http://127.0.0.1:{gw_port}/")
        ids = a.submit("flow_sample_contract")
        job = a.wait_jobs(ids, 400)[0]
        check(job["state"] == "done" and job["rejections"] > 0, "a job still finishes when the gateway rejects calls",
              f"state {job['state']}, error {job.get('error')}, rejections {job['rejections']}")
        check(a.steps_exact(ids), "rejected calls were sent again, each step exactly once")
        streak = a.sql("SELECT max((data->>'hold_s')::float) FROM events WHERE kind = 'task_rejected' AND job_id = %s", ids[0])[0][0]
        check(streak is not None and streak > 1, "the pause after rejections grew beyond its first value", str(streak))

        stop(app_proc)
        check(app_proc.returncode is not None, "the application stops cleanly")
    finally:
        for p in list(procs):
            stop(p)
        if not args.keep:
            try:
                with psycopg.connect(**conninfo, autocommit=True) as c:
                    c.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
            except Exception as e:  # noqa: BLE001
                print(f"could not remove the test schema: {e}")

    bad = [w for ok, w in results if not ok]
    print(f"\n{len(results) - len(bad)} of {len(results)} checks passed")
    for w in bad:
        print(f"  FAILED: {w}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
