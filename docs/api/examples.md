[Documentation](../README.md) › [API](README.md) › Examples

# Examples

Two complete clients to copy and adapt: one in Python, one in shell. Both start a job, poll until it ends and
print the results. They are also in the repository as files, under `docs/api/examples/`.

**On this page**

- [Python](#python)
- [Shell](#shell)
- [Running a flow on many files](#running-a-flow-on-many-files)
- [Advice for a production client](#advice-for-a-production-client)

## Python

[`examples/run_flow.py`](examples/run_flow.py) needs the `requests` package. It works as a command and as a
module: `start`, `wait` and `results` are the three calls a program needs, and `describe` reports what a flow
takes.

```bash
pip install requests
python run_flow.py http://localhost:8000 "Check an invoice against its order" \
    --file "Purchase order=purchase-order.pdf" \
    --file "Delivery note=delivery-note.png" \
    --file "Invoice=invoice.pdf" \
    --value "Price tolerance=10"
```

```python
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
```

What to notice:

- `check` turns every refusal into one exception that carries the engine's `code`. A program should branch on
  the code, not on the wording of the message.
- `start` sends each file under the name of its file input. For a flow with one file input the name `file`
  works, so the caller does not need to know what the input is called.
- `wait` treats `failed` and `cancelled` as final, the same as `done`. A loop that waits only for `done`
  never ends when a job fails.
- `requests` sends a `Content-Length` header with the form, which the endpoint requires. A client that sends
  a form without one is answered `411` with the code `length_required`.

## Shell

[`examples/run_flow.sh`](examples/run_flow.sh) needs `curl` and `jq`. It runs a flow that takes one file.

```bash
./run_flow.sh http://localhost:8000 medical-record-summary record.pdf
```

```bash
#!/usr/bin/env bash
# Run a published one-file flow on a file and print the results. Needs curl and jq.
#
#   ./run_flow.sh http://localhost:8000 medical-record-summary record.pdf
set -euo pipefail

base="$1"; flow="$2"; file="$3"

reply=$(curl -sS -X POST "$base/api/v1/flows/$flow/jobs" -F "file=@$file")
job=$(jq -r '.job_id // empty' <<<"$reply")
if [ -z "$job" ]; then
  echo "refused: $(jq -r '.error' <<<"$reply")" >&2
  exit 1
fi
echo "started $job" >&2

while true; do
  status=$(curl -sS "$base/api/v1/jobs/$job")
  state=$(jq -r '.status' <<<"$status")
  case "$state" in
    done) break ;;
    failed|cancelled) echo "$state: $(jq -r '.error' <<<"$status")" >&2; exit 1 ;;
  esac
  echo "  $state: $(jq -r '"\(.progress.calls_done) of \(.progress.calls_planned) calls so far"' <<<"$status")" >&2
  sleep 3
done

curl -sS "$base/api/v1/jobs/$job/results" | jq -r '.outputs[] | "=== \(.name) ===\n\(.text)\n"'
```

## Running a flow on many files

One request starts one job, so a set of files is a loop. Send them as `bulk` so that people working in the
builder are not held up behind them, then collect the results.

```python
from pathlib import Path
from run_flow import FlowError, results, start, wait

BASE = "http://localhost:8000"
FLOW = "medical-record-summary"

# Start everything first. The engine queues the jobs; it does not need to be fed slowly.
jobs = {}
for path in sorted(Path("records").glob("*.pdf")):
    jobs[path.name] = start(BASE, FLOW, {"file": path}, priority="bulk", label=path.name)

Path("summaries").mkdir(exist_ok=True)
for name, job_id in jobs.items():
    try:
        wait(BASE, job_id)
        text = results(BASE, job_id)[0]["text"]
        Path("summaries", name).with_suffix(".txt").write_text(text)
    except FlowError as e:
        print(f"{name}: {e}")
```

Starting many jobs at once is safe for the model quota: the engine admits calls only as the quota allows, so
the jobs wait in the queue instead of being rejected. They do take the quota that other users of the same
model endpoint would otherwise have. See [Under heavy load](../how-it-works/heavy-load.md).

> **Note:** a batch request, which starts many jobs under one batch id, is planned but not built. See
> [Limits](../operations/limits.md).

## Advice for a production client

- **Store the job id as soon as you have it.** It is the only handle on the job. If your program stops, the
  job carries on, and the id is all you need to pick it up again.
- **Poll every few seconds, not faster.** Status changes at the pace of model calls.
- **Set your own time limit.** A job has no deadline inside the engine. Decide how long you will wait, then
  cancel with `POST /api/v1/jobs/{job_id}/cancel`.
- **Check `truncated`.** An item with `"truncated": true` stopped at the step's maximum output. The fix is in
  the flow: raise the step's maximum output and publish again. See [Steps](../guide/steps.md).
- **Record `flow_version`.** It tells you which version of the flow produced a result, after the flow has
  moved on.
- **Ask what the flow needs rather than hard-coding it.** `GET /api/v1/flows/{flow}` lists the file and value
  inputs. A flow's author can add an optional value without breaking callers, but a new required value or a
  renamed file input will be refused until the caller sends it.

## See also

- [Running a flow from code](README.md): the overview
- [API reference](reference.md): every field and error code
- [Under heavy load](../how-it-works/heavy-load.md): what happens to a large batch of jobs
- [Queue and priority](../how-it-works/queue-and-priority.md): what `interactive` and `bulk` mean
