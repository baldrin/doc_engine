[Documentation](../README.md) › [Setup and operations](README.md) › Commands

# Commands

Every command of `python -m doc_engine ...`: its options, what it prints, and when to use it. For whoever
operates Document Engine from a shell.

**On this page**

- [Overview](#overview)
- [Options for every command](#options-for-every-command)
- [Commands that can saturate the endpoint](#commands-that-can-saturate-the-endpoint)
- [db](#db)
- [samples](#samples)
- [preflight](#preflight)
- [serve](#serve)
- [worker](#worker)
- [load](#load)
- [probe bucket](#probe-bucket)
- [jobs](#jobs)
- [export](#export)
- [The end-to-end check](#the-end-to-end-check)

## Overview

| Command | What it does | Calls the gateway |
|---|---|---|
| [`db init`](#db) | Creates or updates the tables and functions; copies the model limits. | No |
| [`db check`](#db) | Says whether every table exists. | No |
| [`db reset --yes`](#db) | Removes every table and all data. | No |
| [`samples`](#samples) | Installs the sample flows and files. | No |
| [`preflight`](#preflight) | Checks the settings, the database and each model. | Yes, a few tiny calls |
| [`serve`](#serve) | Runs the web application and its worker. | When jobs run |
| [`worker`](#worker) | Runs a worker without the web application. | When jobs run |
| [`load`](#load) | Submits several jobs at the same moment and reports the result. | Yes, **can saturate** |
| [`probe bucket`](#probe-bucket) | Saturates one model on purpose to measure its bucket. | Yes, **saturates** |
| [`jobs`](#jobs) | Lists recent jobs. | No |
| [`export`](#export) | Writes one job's rows to CSV files. | No |

Every command reads the settings file first and stops if it is missing or breaks a rule. See
[Rules enforced at start](settings.md#rules-enforced-at-start).

Document Engine needs Python 3.11 or newer. On an older Python every command stops at once with
`Document Engine needs Python 3.11 or newer. This is Python <version>.` and exit code 1.

`samples`, `worker`, `load`, `jobs` and `export` need the tables. When they are missing, each prints
``the database is not set up. Run `python -m doc_engine db init` first.`` and exits with code 1.

One more check is not a command of `python -m doc_engine`: [`python tests/e2e.py`](#the-end-to-end-check)
runs the whole application against the fake gateway and reports what still works.

## Options for every command

These go **before** the command name:

| Option | Meaning |
|---|---|
| `--config PATH` | The settings file to use. Default: `DOC_ENGINE_CONFIG`, else `config.yaml` in the repository root. |
| `-v`, `--verbose` | Also print informational log lines from the libraries the application uses. The application's own informational lines are always printed. |

```bash
python -m doc_engine --config config.fake.yaml jobs
```

Except `db`, `preflight`, `probe` and `serve`, a command first prints
`config still has FILL-IN values: ...` if any remain, then carries on.

## Commands that can saturate the endpoint

Two commands can use the whole output quota of a model. While that lasts, every other application that uses
the same endpoint is slowed or rejected. Both refuse to start until you add a confirmation flag, and both have
a `--dry-run` that prints the size and cost and sends nothing.

| Command | Needs `--confirm-saturation` when | Without the flag |
|---|---|---|
| `load` | The number of jobs (`--jobs` plus `--bulk`) is `server.saturating_jobs` (4) or more. | Prints `This run can saturate the endpoint and throttle other applications in the workspace.` and exits with code 2. |
| `probe bucket` | Always. | Prints `This saturates the model on purpose and throttles every application using it.` and exits with code 2. |

The same threshold applies on the screens: submitting `server.saturating_jobs` jobs or more from **Activity**
asks for confirmation. A single **Test run** from the builder is never asked. See [Under heavy load](../how-it-works/heavy-load.md).

Leave at least a minute between saturating runs. The ledger cannot see what the probe used, nor what other
applications use, and it starts each process believing the quota is as it last recorded it.

> **Note:** the [public endpoint](../api/reference.md) starts one job per request and asks for no
> confirmation. A caller that sends many requests can saturate the endpoint too.

## db

```text
python -m doc_engine db init
python -m doc_engine db check
python -m doc_engine db reset --yes
```

| Action | What it does | What it prints |
|---|---|---|
| `init` | Applies `sql/001_schema.sql`: creates missing tables, adds new columns, and installs the current functions that admit and complete calls. Then copies each model's limits from the settings into the `quota` table. Keeps all data. | `schema applied; model limits copied from the config:` and one line per model with its gateway name, ITPM, OTPM and output cap (the safety margin already applied). |
| `check` | Looks for the fourteen tables the application needs. | `all tables present`, or `missing tables: ...` with exit code 1. |
| `reset` | Removes every Document Engine table and function. All flows, files, jobs and history are lost. | Without `--yes` it only prints a warning and exits with code 2. With `--yes`: ``all Document Engine tables removed. Run `python -m doc_engine db init` next.`` |

**When to use it.** `init` once at installation and again after every pull. `check` to confirm an
installation. `reset` only to start again from nothing.

## samples

```text
python -m doc_engine samples [--force]
```

Creates the four sample flows and the ten fictional sample files if they are missing. The tables must exist:
without them it prints ``the database is not set up. Run `python -m doc_engine db init` first.`` and exits
with code 1.

| Option | Meaning |
|---|---|
| `--force` | Rebuild the samples even if they are present. |

It prints `created N flow(s) and M document(s)`, then every flow and every file in the database with its id,
and for files the page count and size. Use those ids with [`load`](#load).

**When to use it.** After `db init`, or with `--force` after a pull that changed the samples. `serve` installs
the samples by itself only on a database that has never held anything: no flows and no files. If every flow
has been deleted, it does not bring the samples back; run `samples` for that.

## preflight

```text
python -m doc_engine preflight
```

Checks everything that can be checked cheaply before a job is run. It makes three small calls per model when
all is well, and up to five when a model refuses its "thinking off" form. It exits with code 0 when it passed
and 1 when it found problems.

### What it prints

**`== config ==`**

| Line | Meaning |
|---|---|
| `file: <path>` | The settings file in use. |
| `no FILL-IN values remain` | Good. |
| `FILL-IN values remain: ...` | The named settings are still `FILL-IN`. Counts as a problem. |

**`== database ==`**

| Line | Meaning |
|---|---|
| `connected: PostgreSQL ...` | The connection works; this is the server version. |
| `round trip: N ms average over 20 queries` | How long one small query takes. Every admission costs one round trip. |
| `tables: all present` | Good. |
| ``tables missing (...). Run `python -m doc_engine db init`.`` | Counts as a problem. |
| `LISTEN/NOTIFY: available` | Workers are woken at once when a call completes or a job arrives. |
| `LISTEN/NOTIFY: not available (...). The engine falls back to timed checks.` | Not counted as a problem. |
| `FAILED: ...` | The database could not be reached or queried. Counts as a problem. |

**`== gateway ==`**

If `gateway.base_url` is still `FILL-IN`, this section prints `skipped: gateway.base_url is not set` and
preflight ends there with exit code 1. Otherwise, for each configured model:

| Line | Meaning |
|---|---|
| `thinking off as '<form>': OK (...)` | The model answered a one-word request with its configured `thinking_off` form. Shows tokens in and out, the duration and the reply. |
| `thinking off as '<form>': <outcome> HTTP <status>: <message>` | The model refused the configured form, or the call failed. Counts as a problem. Preflight then tries the other forms, printing `trying '<form>': ...` for each, and for the first that works prints `-> set models.<name>.thinking_off: <form>`. |
| `adaptive thinking, low effort: ok` | The model accepts the form used for the thinking levels low, medium and high. Any other result counts as a problem. |
| `image input: OK (read correctly, N in)` | The model was sent a small image showing the number 742 and read it. |
| `image input: OK (reply '...', expected 742, N in)` | The model accepted the image but answered something else. Not counted as a problem. |
| `image input: <outcome> HTTP <status>: ...` followed by `-> image files cannot be sent as images to this model. Set worker.send_images_as: pdf` | The model refused the image. Counts as a problem until `worker.send_images_as` is `pdf`; with that setting the line is followed by a note that it is not a problem. |
| `image input: not checked, because no "thinking off" form was accepted. Fix that first.` | The image check needs a working "thinking off" form. Set the one preflight suggests and run it again. |

The last line is `preflight passed` or `preflight found problems (see above)`.

> **Note:** the image call uses the model's configured `thinking_off` form. If that form was refused, the
> image call fails for the same reason. Fix `thinking_off` and run preflight again before acting on the image
> line.

**When to use it.** Before the first run, after changing the settings, after adding a model, and whenever
calls start failing in a way that suggests the gateway changed.

> **Not yet confirmed:** preflight has only been run against the fake gateway. Its first run on the real
> gateway is step 1 of the [first session on the real gateway](first-real-session.md).

## serve

```text
python -m doc_engine serve
```

Runs the web application: the screens, the API, and a worker inside the same process (unless
`worker.enabled` is `false`). It has no options of its own.

It prints `Document Engine on http://localhost:<port>`. The port is `DATABRICKS_APP_PORT`, else `PORT`, else
`server.port` (8000). On start it applies the schema, copies the model limits into the `quota` table, and
installs the samples if the database holds no flows and no files. A model that was taken out of the settings
is removed from the `quota` table, and so from the quota panels, once none of its calls are waiting or in
flight. `db init` does the same. `worker` and `load` do not: see below. Stop it with Ctrl+C: calls in flight are cancelled and their
[tasks](../glossary.md#task) return to the queue.

[Monitoring](monitoring.md#log-lines) lists the log lines it prints.

## worker

```text
python -m doc_engine worker
```

Runs a worker without the web application. It prints `worker <id> running. Ctrl+C stops it cleanly.` The
tables must already exist: without them it prints
``the database is not set up. Run `python -m doc_engine db init` first.`` and exits with code 1.

On start it copies the model limits from its settings file into the `quota` table. It does not remove the
quota row of a model that is missing from that file, so a worker started with another settings file cannot
take a model away from the application.

**When to use it.** When `worker.enabled` is `false` in the web process, or to add a process that makes calls.
All workers share one quota through Postgres, so an extra worker adds room for calls in flight, not quota.

## load

```text
python -m doc_engine load --flow ID --document ID [--document "Source name=ID" ...]
                          [--value "Name=value" ...] [--jobs N] [--bulk K] [--label TEXT]
                          [--dry-run] [--confirm-saturation] [--no-worker]
```

Submits several jobs at the same moment, waits for them, and prints a summary. It is the command-line way to
see how the scheduler behaves under load. Like `worker`, it updates the `quota` rows of the models in its
settings file and does not remove the row of a model that is missing from it.

| Option | Default | Meaning |
|---|---|---|
| `--flow ID` | required | The flow to run, by its id (for example `flow_sample_medical`). The published version is run; if the flow is not published, the latest saved version; if none has been saved, the draft. The first line of output says which. |
| `--document ID` | required | The file to run it on, by its id. For a flow with [several sources](../guide/several-files.md), repeat it as `--document "Source name=ID"`, once per source. A bare id is used for every source not named. A `"=ID"` with no name before the `=` sign is refused. |
| `--value "Name=value"` | none | A [value input](../guide/value-inputs.md). Repeat for each. An input left out takes its default. A value that is not in the form `Name=value` is refused. |
| `--jobs N` | `1` | The number of interactive jobs. `--jobs` plus `--bulk` must be between 1 and 50, as on the screens. |
| `--bulk K` | `0` | The number of bulk jobs, submitted after the interactive ones. |
| `--label TEXT` | `load` | The start of each job's label. Jobs are labelled like `load interactive 1`. |
| `--dry-run` | off | Print the estimate and stop. Sends nothing and changes nothing in the database. It still needs to read the database. |
| `--confirm-saturation` | off | Needed when `--jobs` plus `--bulk` is `server.saturating_jobs` or more. |
| `--no-worker` | off | Only submit and wait. A running application or worker does the work. Without this option the command runs its own worker for the length of the run. |

### What it prints

First the plan:

```text
flow: <name> (<which version runs>)   document: <file name> (<pages> pages)
values: <name> = <value>, ...          (only when the flow has value inputs)
jobs: <N> interactive + <K> bulk
per job: <calls> calls, about <tokens> output tokens, about $<cost>
total:   <calls> calls, about <tokens> output tokens, about $<cost>
```

The estimate is the builder's [estimate](../how-it-works/estimates.md): it uses the share each filter kept in
the flow's most recent run, and each file's own tokens per page.

Then, unless it is a dry run, `submitted N job(s)` and a progress line every five seconds with the jobs done,
the calls that succeeded, the rejections and the calls in flight. When every job has finished it prints
`== summary ==`:

| Line | Meaning |
|---|---|
| One line per job | Its id, priority, state, wall time, how long it waited before its first call was admitted, its label, and `ERROR: ...` if it failed. |
| `calls N (ok N), rejections N (output N, input N), truncated N` | All calls of the run; rejections split by the limit the gateway named; replies cut off at the step's maximum output. |
| `output tokens N = N per minute over Ns` | Output volume and rate from the first call sent to the last call done. |
| `input tokens N, cache read N, cache write N in N call(s)` | Input volume and [prompt cache](../how-it-works/prompt-caching.md) use. |
| `peak calls in flight N; cost about $N` | The most calls open at once, and the cost at the configured prices. |
| `admission round trip: median N ms, p95 N ms, max N ms; ledger checks {...}` | Printed only when the command ran its own worker: how long admission took in the database, and how often the ledger answered admitted, blocked, held or empty. |

Press Ctrl+C once to stop cleanly: the jobs are cancelled and the summary is still printed. Press it again to
abort at once.

Messages when it cannot start:

| Message | Cause |
|---|---|
| ``the database is not set up. Run `python -m doc_engine db init` first.`` | Tables are missing. |
| `submit between 1 and 50 jobs at a time (--jobs plus --bulk)` | `--jobs` plus `--bulk` is less than 1 or more than 50, or one of them is negative. |
| ``flow not found. Run `python -m doc_engine samples` and use the ids it prints.`` | No flow has that id. |
| `choose a file for <source>` or `the file chosen for <source> was not found` | A source has no file, or the file id is wrong. |
| `--document "..." has no name before the = sign` | A `--document` was given as `"=ID"`. |
| `--value "..." is not in the form "Name=value"`, or `--value "..." has no name before the = sign`, then `Give values as --value "Name=value".` | A `--value` is malformed. It is refused, not ignored. |
| A message naming an input, then `Give values as --value "Name=value".` | A value is missing, of the wrong type, or not declared by the flow. |

Each of these exits with code 1, also in a dry run.

**When to use it.** For the ten-job run of the first session, and whenever you want measured numbers for a
change to the settings. Always run it with `--dry-run` first.

> **Note:** like the screens, `load` accepts at most 50 jobs in one submission: `--jobs` plus `--bulk`.

## probe bucket

```text
python -m doc_engine probe bucket --model NAME [--calls N] [--spacing S] [--dry-run] [--confirm-saturation]
```

Measures the gateway's output bucket for one model by sending calls until the gateway starts rejecting them.
It saturates that model on purpose. It talks to the gateway directly: it does not use the queue, the ledger or
the database, so a running application cannot see what the probe used.

| Option | Default | Meaning |
|---|---|---|
| `--model NAME` | required | The model's key in the settings, for example `haiku`. |
| `--calls N` | `300` | The most calls to send. |
| `--spacing S` | `0.1` | Seconds between the starts of two calls. |
| `--dry-run` | off | Print the plan and cost and stop. |
| `--confirm-saturation` | off | Always needed to send anything. |

Each call asks for a list of 150 short facts, with `max_tokens` 1500 and the model's `thinking_off` form. The
probe stops starting new calls 20 seconds after the first rejection, then waits for the calls in flight.

### What it prints

The plan, also in a dry run:

```text
bucket probe on <model> (<gateway name>)
  up to <N> calls, one every <S>s, about 1200 output tokens each
  at most about <tokens> output tokens, about $<cost>; stops 20 s after the first rejection
  configured OTPM <otpm>
```

After the run, `sent N, accepted N, rejected N`, and if there was a rejection:

| Line | Meaning |
|---|---|
| `first rejection at t+Ns; N calls had completed with N output tokens; N in flight` | When the gateway first said no, and what had been charged by then. |
| `refill during that time at the configured OTPM: N` | What the bucket regained meanwhile. |
| `=> output charged beyond refill before rejection began: about N tokens (the bucket estimate)` | The result. |
| `mean call duration Ns; rejection names: output` | The call length, and which limit the rejections named. |
| `after the first rejection the gateway accepted about N output tokens per minute` | The sustained rate under saturation, when the run went on long enough to tell. |
| `To use this: set models.<name>.bucket_measured to about N. Keep bucket_capacity_output until the result has been reviewed.` | What to change. |

If nothing was rejected it prints `no rejection: ...` and suggests `Increase --calls or lower --spacing.`

Last, `raw data: <path>`. The file is `results/<UTC date-time>_probe_bucket_<model>.json` in the repository
root, with the result and one record per call. The `results/` directory is not committed.

The cost in the plan is an upper bound: every call sent and none rejected. With the default options and the
prices in `config.example.yaml` it comes to about $0.27 for Haiku, $5.45 for Sonnet and $10.91 for Opus. A
probe that meets rejections stops early and costs less. The `--dry-run` output gives the figure for your
settings.

**When to use it.** Once per model before relying on its budget, and again when the endpoint tier changes. See
[Re-sizing a model](settings.md#re-sizing-a-model).

> **Not yet confirmed:** this command has only run against the fake gateway. Its runs for Haiku and Opus are
> step 3 of the [first session on the real gateway](first-real-session.md). The Sonnet 5.5
> values in the settings come from the proof of concept, not from this command.

## jobs

```text
python -m doc_engine jobs [--limit N]
```

Lists the most recent jobs, newest first. `--limit` defaults to 20. When the tables are missing it prints
``the database is not set up. Run `python -m doc_engine db init` first.`` and exits with code 1. One line per
job:

```text
<job id>  <state>   <priority>   <wall seconds>s  calls <N>  429s <N>  <flow name> / <file names>
```

For a job that has not finished, the time counts up to now. `429s` is the number of rejections.

**When to use it.** For a quick look without opening the screens, and to find a job id for `export`.

## export

```text
python -m doc_engine export --job ID --out DIR
```

Writes the rows of one job to CSV files in `DIR`, creating the directory if needed.

| File | Contents |
|---|---|
| `jobs.csv` | The job: flow, file names, pages, priority, state, label, error and times. The flow graph is left out. |
| `job_steps.csv` | One row per block of the job's flow, with its state and counts. |
| `tasks.csv` | One row per planned call, including its output text. |
| `calls.csv` | One row per call actually made, successful or not, with tokens, timing, outcome and error. |
| `events.csv` | Every state change of the job, in order. |
| `reservations.csv` | What the ledger counted for each admitted call. |

It prints each file name with its row count, then `written to <DIR>`.

A job id that does not exist prints ``job not found: <ID>. `python -m doc_engine jobs` lists recent job ids.``
and exits with code 1. Nothing is written. When the tables are missing it prints
``the database is not set up. Run `python -m doc_engine db init` first.`` and exits with code 1.

> **Note:** `tasks.csv` holds the model's outputs, and so whatever they quote from the files. Handle the
> export as you would the results themselves.

**When to use it.** To keep the evidence of a run, or to analyse one outside the application. See
[Monitoring](monitoring.md#exporting-a-job).

## The end-to-end check

```text
python tests/e2e.py [--rounds N] [--speed X] [--quota-scale X] [--keep]
```

Runs the whole application against the [fake gateway](fake-gateway.md) and checks that it still does what it
did: the commands, the screens' API, the public endpoint, ten jobs at once, a cancelled job, a killed worker,
a gateway that rejects calls, and streamed replies that fail part-way. It is not a command of `python -m doc_engine` and is not collected by
`pytest`; run it directly.

It needs only a reachable Postgres, the one `config.fake.yaml` and the `PG*` variables point at. It starts its
own fake gateway and its own copy of the application on free ports. It keeps its tables in a separate schema,
`de_e2e`, of that database, so the tables of a development database are not touched. The schema is removed at
the end. It takes a few minutes.

| Option | Default | Meaning |
|---|---|---|
| `--rounds N` | `3` | How many times to run ten jobs at once with a cold prompt cache. |
| `--speed X` | `25` | How much faster than life the fake gateway answers. |
| `--quota-scale X` | `5` | Multiplies the model limits, in the settings and in the fake gateway alike, so the runs take less time. |
| `--keep` | off | Leave the `de_e2e` schema in place afterwards, to look at it. |

It first prints `logs and settings: <directory>`, the temporary directory that holds the settings file it
wrote and the logs of the processes it started. Then it prints one line per check, `ok` or `FAIL` with the
reason. The last line is `N of N checks passed`, followed by the failed checks if there are any. The exit
code is 0 when every check passed and 1 otherwise.

**When to use it.** After a change to the code and after a pull, before trusting the application with a real
run.

> **Note:** this check says nothing about the real gateway. It shows that the code still runs as before
> against the fake one.

## See also

- [Settings reference](settings.md): the settings these commands read and tell you to change.
- [Monitoring](monitoring.md): the same information from the screens, the API and the tables.
- [Troubleshooting](troubleshooting.md#preflight-reports-a-problem): what to do about each preflight failure.
- [Under heavy load](../how-it-works/heavy-load.md): what saturation does and why it needs confirmation.
- [The fake gateway](fake-gateway.md): trying `load` and `probe bucket` at no cost.
