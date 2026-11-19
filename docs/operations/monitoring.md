[Documentation](../README.md) › [Setup and operations](README.md) › Monitoring

# Monitoring

What to watch while Document Engine runs: two screens, two addresses, one command, the tables in Postgres,
and the log. For whoever keeps the application running.

**On this page**

- [What healthy looks like](#what-healthy-looks-like)
- [The Activity screen](#the-activity-screen)
- [The Run screen](#the-run-screen)
- [/api/health](#apihealth)
- [/api/quota](#apiquota)
- [The jobs command](#the-jobs-command)
- [The tables in Postgres](#the-tables-in-postgres)
- [Log lines](#log-lines)
- [Exporting a job](#exporting-a-job)

## What healthy looks like

| Sign | Where to see it |
|---|---|
| At least one worker is reporting. | `/api/health` |
| Rejections are zero, or rare and isolated. | **Activity**, `/api/quota`, the `calls` table |
| The interactive lane is clear, or clears quickly. | **Activity** |
| Queued jobs start, and running jobs make progress. | **Activity**, the `jobs` command |
| No calls are being returned to the queue after a lost worker. | The log, the `events` table |

Everything the screens show is read from Postgres, so it is the same on every instance and the same as what
the queries below return.

## The Activity screen

**Activity** shows every job and the quota of every model. It is the first place to look. The
[Activity screen](../guide/activity-screen.md) page describes it for people who submit jobs; this is what an
operator reads from it.

> **Screenshot to add:** `images/activity-under-load.png`. The Activity screen while several jobs run: the five tiles at the top, the quota bars for each model, and the jobs table with at least one running and one queued job.

| On screen | What it tells you |
|---|---|
| The badge **Working** or **Idle** | Whether any job is queued or running. |
| **Jobs running**, **Jobs queued** | The counts right now. |
| **Calls in flight** | Model calls open at this moment, over all models and all instances. |
| **Rejections, last 60 s** | Calls the gateway rejected in the last minute. Green at zero, red otherwise. |
| **Interactive lane** | **Clear**, or how many calls of interactive jobs are waiting. Interactive calls go before bulk calls. |
| **Shared quota, by model** | Per model, three bars: **Output tokens per minute** and **Input tokens per minute** (what completed in the last 60 seconds, against the limit) and **Burst budget in use** (output charged plus output expected from calls in flight, against the output cap). The mark on a bar is the ceiling the scheduler stays under. |
| The line beside a model's name | `N in flight · N ready`, or **paused after a rejection** while admission for that model is held. |
| The **Jobs** table | Per job: place in the queue, priority, status, progress as calls done out of calls planned, calls in flight, rejections and elapsed time. Click a row to open its Run screen. A queued or running job has a **Cancel** button, which asks for confirmation first. |

Things to act on:

- **Rejections, last 60 s** above zero for more than a moment. See
  [Troubleshooting](troubleshooting.md#rejections-appear).
- A job that stays **Queued**. See [Troubleshooting](troubleshooting.md#jobs-stay-queued).
- A model that shows **paused after a rejection** again and again.

> **Note:** in `duration` capacity mode the cap used for admission is worked out per call from
> `bucket_measured` and the call length. The **Burst budget in use** bar compares against the cap that
> admission last used. Before any admission it uses the cap for a call of the default length,
> `ledger.default_call_s`.

A model that was taken out of the settings leaves these panels at the next start, once none of its calls are
waiting or in flight.

## The Run screen

The **Run** screen shows one job, live. Open it from a row of the **Jobs** table. The
[Run screen](../guide/run-screen.md) page describes it in full.

> **Screenshot to add:** `images/run-live-with-events.png`. The Run screen of a running job: the flow with per-step progress on the left, and on the right the Scheduler panel with a model's bars, the In flight, Rejections and Interactive lane tiles, and several lines in the Live events feed.

For an operator the useful parts are:

| On screen | What it tells you |
|---|---|
| The status badge | **Queued**, **Running**, **Complete**, **Failed** or **Cancelled**. |
| **Elapsed** and **Calls done** | Time since submission, and calls done out of calls planned so far. Calls are planned as earlier steps finish, so the planned figure grows. |
| The **Scheduler** panel | The same quota bars as on **Activity**, for the models this job uses. |
| **In flight**, **Rejections** | For this job only. |
| **Live events** | The most recent state changes of the job, newest first. |

Lines in **Live events** that matter to operations:

| Line | Meaning |
|---|---|
| `Gateway rejected a call (output) · <model> paused 1 s` | A rejection. The limit named is `output`, `input` or `queries`. The call returns to the queue and is sent again. |
| `<step> · retrying (...)` | A timeout, a gateway error or a reply that did not match its schema. The call is tried again. |
| `<step> · warm-up failed, continuing without the cache` | A warm-up call failed. The step runs without the prompt cache; the job is not affected otherwise. |
| `<step> · a lost call was returned to the queue` | A worker stopped, or a call outlived its lease, and the call was recovered. |
| `<step> · this call was returned to the queue N times because the worker sending it stopped each time. It was not sent again.` | The same call was lost more than `ledger.max_recoveries_per_call` times. The job fails. |
| `<step> · ... · cut off at max output` | A reply reached the step's maximum output and was truncated. |
| `Run failed · <step>: <reason>` | The job failed. The reason is the same text as the job's error. See [Troubleshooting](troubleshooting.md#a-job-failed). |

A finished run can be replayed with **Replay**. The replay uses the recorded events, so the times and counts
are the real ones.

## /api/health

```bash
curl http://localhost:8000/api/health
```

```json
{"ok": true, "workers": 1}
```

`workers` is the number of worker processes that reported within `ledger.dead_worker_after_s` (configured
default 30 seconds), over all instances. Each worker reports every 5 seconds.

| Reply | Meaning |
|---|---|
| `"workers"` is 1 or more | The web process and the database are up, and something can make calls. |
| HTTP 503 with `"ok": false, "workers": 0` | The web process and the database are up, but no worker is alive. Jobs will stay queued. |
| An error instead of JSON | The web process could not query the database. |

A monitor can watch the HTTP status alone: 200 means work is being processed, anything else means it is not.

## /api/quota

```bash
curl http://localhost:8000/api/quota
```

One snapshot of the ledger and the queue. The screens receive the same data once a second.

| Field | Meaning |
|---|---|
| `models[].model`, `gateway_name` | The model's key and the name sent to the gateway. |
| `models[].otpm`, `itpm` | The configured limits. |
| `models[].out_capacity`, `in_capacity` | The output cap and input cap, safety margin applied. In `duration` capacity mode `out_capacity` is the cap that admission last used, or, before any admission, the cap for a call of the default length. |
| `models[].capacity_mode` | `fixed` or `duration`. |
| `models[].out_level` | Output charged to the ledger and not yet drained, as of now. |
| `models[].open_calls`, `open_output` | Calls in flight, and the output they are expected to produce. |
| `models[].hold_s` | Seconds left of a pause after a rejection. `0` when not paused. |
| `models[].out_60`, `in_60`, `rej_60` | Output tokens, counted input tokens and rejections in the last 60 seconds. |
| `models[].ready`, `ready_interactive`, `waiting` | Calls ready to be admitted, how many of those belong to interactive jobs, and calls waiting for a warm-up. |
| `models[].admissions`, `rejections` | Totals since the model's row was created. |
| `jobs.running`, `jobs.queued` | Job counts. |
| `worker` | The worker inside the web process that answered: its id, `concurrency`, `in_flight`, `peak_in_flight`, `admission_ms` (median, p95, max) and `checks` (how often admission answered `admitted`, `blocked`, `held` or `empty`). `null` when `worker.enabled` is `false`. |

`worker.admission_ms` is the time one admission takes, database round trip included. If it grows, the
database is slow or far away. Behind several instances, `worker` describes whichever instance answered.

[The quota ledger](../how-it-works/quota-ledger.md) explains what the levels mean.

## The jobs command

```bash
python -m doc_engine jobs --limit 20
```

One line per recent job: id, state, priority, elapsed seconds, calls, rejections, flow and file names. It
reads the database directly, so it works when the web process is down. See [Commands](commands.md#jobs).

## The tables in Postgres

Two tables are the record of what happened. `calls` has one row for every model call, successful or not.
`events` has one row for every state change, and is what the live screens and the replay read. Connect with
any Postgres client using the same connection values as the application.

### Jobs that are open

```sql
SELECT job_id, state, priority, label, flow_name, submitted_at, started_at
FROM jobs
WHERE state IN ('queued', 'running')
ORDER BY priority_rank, submitted_at;
```

`started_at` is empty until the job's first call is admitted. The order is the order in which the scheduler
serves them.

### The ledger, per model

```sql
SELECT model, capacity_mode, out_capacity,
       round(greatest(0, out_level - extract(epoch FROM clock_timestamp() - updated_at) * otpm / 60.0)) AS out_level_now,
       hold_until, admissions, blocked_checks, rejections
FROM quota
ORDER BY model;
```

In `duration` capacity mode, the cap that admission last used is in the column `cap_used`; `out_capacity`
holds the fixed cap.

### What is waiting, per model

```sql
SELECT model, state, count(*)
FROM tasks
WHERE state IN ('waiting', 'ready', 'running')
GROUP BY model, state
ORDER BY model, state;
```

`waiting` calls wait for a warm-up, `ready` calls wait for admission, `running` calls are in flight.

### Rejections in the last hour

```sql
SELECT model, limit_type, count(*) AS rejections, min(done_at) AS first_at, max(done_at) AS last_at
FROM calls
WHERE outcome = '429' AND done_at > now() - interval '1 hour'
GROUP BY model, limit_type;
```

`limit_type` is the limit the gateway's message named: `output`, `input`, `queries` or `unknown`.

### How one job's calls ended

```sql
SELECT outcome, count(*) AS calls, sum(output_tokens) AS output_tokens,
       sum(cache_read) AS cache_read, sum(cache_write) AS cache_write
FROM calls
WHERE job_id = '<job-id>'
GROUP BY outcome;
```

The outcomes are `ok`, `429` (rejected), `transient` (timeout or gateway error), `permanent` (the request was
refused or could not be made), `refusal` (the model declined), `empty` (a reply with no text) and `invalid`
(a reply that did not match the step's schema).

### The calls of a job that did not succeed

```sql
SELECT call_id, node_id, model, http_status, outcome, stop_reason, request_id, error
FROM calls
WHERE job_id = '<job-id>' AND outcome NOT IN ('ok', '429')
ORDER BY done_at;
```

`request_id` is the gateway's `x-request-id` header, when it sent one. `error` holds the gateway's reply.

### The events of one job

```sql
SELECT event_id, ts, kind, node_id, task_id, model, data
FROM events
WHERE job_id = '<job-id>'
ORDER BY event_id;
```

The kinds are `job_submitted`, `job_started`, `step_planned`, `filter_applied`, `task_admitted`,
`task_progress`, `task_done`, `task_rejected`, `task_retry`, `task_failed`, `task_recovered`, `step_done`,
`job_done`, `job_failed` and `job_cancelled`.

### Calls recovered after a lost worker

```sql
SELECT ts, job_id, task_id, model, data->>'previous_owner' AS previous_owner
FROM events
WHERE kind = 'task_recovered'
ORDER BY event_id DESC
LIMIT 20;
```

### Workers

```sql
SELECT worker_id, started_at, heartbeat_at, info
FROM workers
ORDER BY heartbeat_at DESC;
```

A worker removes its row when it stops cleanly. A row with an old `heartbeat_at` is a worker that stopped
without warning; such rows are deleted after 10 minutes.

### Replies cut off at the maximum output

```sql
SELECT job_id, node_id, count(*) AS truncated_calls
FROM calls
WHERE truncated
GROUP BY job_id, node_id
ORDER BY truncated_calls DESC;
```

A step that appears here often needs a larger maximum output.

### How much is stored

```sql
SELECT count(*) AS files, pg_size_pretty(sum(size_bytes)) AS stored
FROM documents;
```

Files and results are kept until someone removes them. See
[Limits](limits.md#files-and-results-are-kept-until-removed).

## Log lines

The application writes its log to the terminal (standard error), one line per message:

```text
HH:MM:SS LEVEL logger: message
```

Informational lines at start and stop:

| Line | Meaning |
|---|---|
| `gateway client: base_url=... max_retries=0 timeout=...s http max_connections=...` | The gateway client was created. Printed once per worker. Confirms the address and the connection limit in use. |
| `tables missing: applying the schema` | First start on an empty database. |
| `empty database: creating the sample flows and files` | The samples are being installed. |
| `worker <id> starting: concurrency=N` | A worker started. |
| `worker <id> stopped` | A worker stopped cleanly. |

Warnings and errors, and what they mean:

| Line | Meaning |
|---|---|
| `postgres connect failed (attempt N): ...` | A connection attempt failed. Up to six attempts are made, with growing pauses. |
| `database operation failed (attempt N): ...` | A query lost its connection or hit a deadlock and is being retried, up to three times. |
| `admission failed: ...` | The worker could not ask the database for the next call. It tries again after a second. |
| `heartbeat failed: ...` | The worker could not report that it is alive. If this lasts longer than `ledger.dead_worker_after_s`, other workers take over its calls. |
| `reaper failed: ...` | The check for lost calls could not run this time. |
| `returned N task(s) to the queue after a lost worker or lease` | Calls were recovered from a worker that stopped, or from calls that outlived `ledger.lease_s`. |
| `notification listener lost (...); relying on timed checks, retrying in 5 s` | `LISTEN/NOTIFY` is not working. The engine keeps going on timed checks. |
| `event hub: ...` | The live feed to the browsers could not read the `events` table this time. |
| `unexpected error during a model call` | A call failed with an error that is not a gateway reply, for example a missing token. A traceback follows. |
| `task N failed inside the worker` | A call could not be prepared or recorded. A traceback follows; the job fails with `worker error: ...`. |
| `could not record the failure of task N`, `could not return task N to the queue; the reaper will` | The database was unavailable at that moment. The call is recovered later by the check for lost calls. |
| `worker cleanup failed` | The worker could not tidy up while stopping. Its calls are recovered by another worker. |

A few warnings in a long run are normal. Repeated database warnings mean the database is unreachable or
overloaded; see [Troubleshooting](troubleshooting.md#the-database-cannot-be-reached).

## Exporting a job

To keep the complete record of one job, or to analyse it elsewhere:

```bash
python -m doc_engine export --job <job-id> --out <directory>
```

It writes six CSV files: the job, its steps, its planned calls with their outputs, the calls made, the events
and the ledger reservations. [Commands](commands.md#export) lists the files. The export contains the model's
outputs, so handle it as you would the results.

## See also

- [Troubleshooting](troubleshooting.md): what to do about what you see here.
- [Commands](commands.md): `jobs`, `export` and `load` in full.
- [The quota ledger](../how-it-works/quota-ledger.md): the meaning of levels, caps and holds.
- [Failures and recovery](../how-it-works/failures-and-recovery.md): what retries, recovery and failure do to a job.
- [Activity screen](../guide/activity-screen.md): the same screen from the point of view of someone submitting jobs.
