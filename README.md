# Document Engine

A general document-processing engine. People build **flows** out of **steps** (model calls) in a
visual editor, run them on documents, and watch them execute. Underneath, one scheduler decides
which model call goes next, so that many jobs share one model quota without overrunning it and
interactive jobs stay fast while bulk work is running.

This repository follows the scheduler proof of concept (kept separately in `docengine-scheduler-poc`).
The scheduler here is rewritten around what was **measured** on the Databricks AI Gateway on
2026-11-14 to 16, not around the gateway's documentation.

## What has and has not been run

| | Status |
|---|---|
| Scheduler design (bucket ledger, expected-output accounting, 429 hold) | Measured on the real gateway in the POC, on Sonnet 5.5 at 1M / 100K |
| This codebase | Run only against the **fake gateway** in `fake_gateway/`. It has never called the real gateway. |
| Haiku 5.5 and Opus 5.5 budgets | Placeholders until the bucket probe has been run for each |
| Several worker processes, killed-worker recovery | Pass on the fake gateway. Not yet run on the real one. |
| Flows with several sources and references | Pass on the fake gateway. The prompts and page references have not met a real model. |
| Value inputs in prompts and filter rules | Pass on the fake gateway. Whether a real model acts on the values has not been checked. |
| Images and text files as sources | Pass on the fake gateway. Image input has not been sent to the real gateway: preflight now checks it per model. |
| The public endpoint (`/api/v1`) | Passes on the fake gateway. Not yet run on Databricks Apps, where the platform decides who can reach it. |
| Lakebase, Databricks Apps deployment | Not yet run |

Nothing the fake gateway shows is evidence about the real gateway. It only shows the code runs.

## Documentation

Everything is in [`docs/`](docs/README.md): a user guide, the API, how the scheduler works, and setup and
operations. Start at the [documentation home](docs/README.md).

| To | Read |
|---|---|
| See what it is and try it | [Overview](docs/start/overview.md), [Quick start](docs/start/quick-start.md) |
| Build a flow | [Build a flow](docs/guide/build-a-flow.md) |
| Run a flow from a program | [Running a flow from code](docs/api/README.md) |
| Understand the scheduler | [How it works](docs/how-it-works/README.md), [Under heavy load](docs/how-it-works/heavy-load.md) |
| Install, configure, deploy | [Setup and operations](docs/operations/README.md) |
| Run the first session on the real gateway | [The first session](docs/operations/first-real-session.md) |

## Run it locally

```bash
bash scripts/dev_up.sh          # Postgres, Python environment, config.yaml, schema, sample material
. .venv/bin/activate
export PGPASSWORD=docengine
export DATABRICKS_TOKEN='dapi...'
# set gateway.base_url in config.yaml (the file is not committed)
python -m doc_engine preflight  # cheap checks before spending anything
python -m doc_engine serve      # http://localhost:8000
```

No secret goes in any file: the token and the Postgres password are read from the environment each time they
are needed. After every pull, run `pip install -r requirements.txt` and `python -m doc_engine db init`.
Details and the manual route: [Local setup](docs/operations/local-setup.md).

To run with no gateway at all:

```bash
python -m fake_gateway --port 8765 --speed 10
DOC_ENGINE_CONFIG=config.fake.yaml FAKE_TOKEN=x python -m doc_engine serve    # port 8100
```

See [The fake gateway](docs/operations/fake-gateway.md).

## Call a published flow

```bash
curl -X POST 'http://localhost:8000/api/v1/flows/check-an-invoice-against-its-order/jobs' \
  -F 'Purchase order=@purchase-order.pdf' -F 'Delivery note=@delivery-note.pdf' -F 'Invoice=@invoice.pdf' \
  -F 'values={"Price tolerance": 10}'
curl 'http://localhost:8000/api/v1/jobs/JOB_ID'            # poll until "status" is "done"
curl 'http://localhost:8000/api/v1/jobs/JOB_ID/results'
```

The **API** button in the flow builder shows these commands for the flow on the canvas.

## Layout

| Path | What it holds |
|---|---|
| `doc_engine/` | The application: `api.py` (web), `public_api.py` (the `/api/v1` endpoint), `planner.py`, `worker.py`, `flows.py`, `documents.py`, `prompts.py`, `gateway.py`, `cli.py` |
| `doc_engine/static/` | The built frontend, committed, so a deployment needs Python only |
| `sql/001_schema.sql` | Tables and the ledger functions (`de_admit`, `de_release`, `de_reap`) |
| `frontend/` | Frontend source: React, TypeScript, Vite, React Flow |
| `fake_gateway/` | A stand-in for the gateway, for development and tests |
| `docs/` | The documentation |
| `tests/` | Unit tests: `python -m pytest -q` |

## Changing the frontend

```bash
cd frontend && npm install
npm run dev        # http://localhost:5173, proxies /api to port 8100
npm run build      # writes ../doc_engine/static
```

Fonts are bundled. Nothing is loaded from the internet at run time.

## Not built yet

Fold, adaptive reduce, batches of files under one batch id, comments, a shared block library, sign-in and
job owners, an availability period for files and results, reuse of earlier results, and a naive-mode
comparison in the UI. See [Limits and what is not confirmed](docs/operations/limits.md).
