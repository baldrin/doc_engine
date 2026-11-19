"""Run a published Document Engine flow and print its results.

    pip install requests
    python run_flow.py http://localhost:8000 "Check an invoice against its order" \
        --file "Purchase order=purchase-order.pdf" --file "Delivery note=delivery-note.png" \
        --file "Invoice=invoice.pdf" --value "Price tolerance=10"

A flow with one file input also accepts  --file report.pdf  with no name.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests


TIMEOUT_S = 120      # for one request; uploading a large file can take a while


class FlowError(Exception):
    """The engine refused a request, or the job did not finish. `code` is the engine's error code."""

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


def check(reply: requests.Response) -> dict:
    """The reply's JSON, or FlowError carrying the engine's own message."""
    try:
        body = reply.json()
    except ValueError:
        reply.raise_for_status()
        raise
    if not reply.ok:
        raise FlowError(body.get("error", reply.reason), body.get("code", ""))
    return body


def describe(base: str, flow: str) -> dict:
    """What the flow needs: its file inputs, its value inputs and its outputs."""
    return check(requests.get(f"{base}/api/v1/flows/{flow}", timeout=TIMEOUT_S))


def start(base: str, flow: str, files: dict[str, Path], values: dict | None = None,
          priority: str = "interactive", label: str = "") -> str:
    """Starts a job and returns its id. `files` maps a file input's name to a path."""
    opened = {name: (path.name, path.open("rb")) for name, path in files.items()}
    data = {"priority": priority}
    if values:
        data["values"] = json.dumps(values)
    if label:
        data["label"] = label
    try:
        reply = requests.post(f"{base}/api/v1/flows/{flow}/jobs", files=opened, data=data, timeout=TIMEOUT_S)
        return check(reply)["job_id"]
    finally:
        for _, handle in opened.values():
            handle.close()


def wait(base: str, job_id: str, every_s: float = 3.0, timeout_s: float = 3600.0) -> dict:
    """Polls until the job ends. Returns the final status, or raises if it failed or was cancelled."""
    deadline = time.monotonic() + timeout_s
    while True:
        status = check(requests.get(f"{base}/api/v1/jobs/{job_id}", timeout=TIMEOUT_S))
        if status["status"] == "done":
            return status
        if status["status"] in ("failed", "cancelled"):
            raise FlowError(f"job {job_id} {status['status']}: {status['error']}", f"job_{status['status']}")
        if time.monotonic() > deadline:
            raise FlowError(f"job {job_id} is still {status['status']} after {timeout_s:.0f} s", "timeout")
        done, planned = status["progress"]["calls_done"], status["progress"]["calls_planned"]
        print(f"  {status['status']}: {done} of {planned} calls so far", file=sys.stderr)
        time.sleep(every_s)


def results(base: str, job_id: str) -> list[dict]:
    """The outputs of a finished job."""
    return check(requests.get(f"{base}/api/v1/jobs/{job_id}/results", timeout=TIMEOUT_S))["outputs"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a published flow and print its results.")
    ap.add_argument("base_url", help="address of the application, such as http://localhost:8000")
    ap.add_argument("flow", help="the flow's name or id")
    ap.add_argument("--file", action="append", default=[], metavar="[INPUT=]PATH",
                    help="a file for a file input; repeat for each input")
    ap.add_argument("--value", action="append", default=[], metavar="NAME=VALUE", help="a value input; repeatable")
    ap.add_argument("--bulk", action="store_true", help="run behind interactive jobs")
    args = ap.parse_args()

    files = {}
    for item in args.file:
        name, sep, path = item.partition("=")
        files[name if sep else "file"] = Path(path if sep else item)
    values = dict(item.split("=", 1) for item in args.value)

    base = args.base_url.rstrip("/")
    try:
        job_id = start(base, args.flow, files, values, "bulk" if args.bulk else "interactive")
        print(f"started {job_id}", file=sys.stderr)
        wait(base, job_id)
        for out in results(base, job_id):
            print(f"\n=== {out['name']} ===")
            if "table" in out:
                print("\t".join(out["table"]["columns"]))
                for row in out["table"]["rows"]:
                    print("\t".join(str(row.get(c, "")) for c in out["table"]["columns"]))
            else:
                print(out["text"])
    except FlowError as e:
        print(f"error ({e.code}): {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
