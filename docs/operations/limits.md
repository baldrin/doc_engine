[Documentation](../README.md) › [Setup and operations](README.md) › Limits and what is not confirmed

# Limits and what is not confirmed

Every hard limit in the code, what is not built, what the application does not yet do about access and
retention, the rule about which files may be used for now, and what has only been run against the fake
gateway. For operators, and for anyone deciding whether Document Engine is ready for a given use.

**On this page**

- [Hard limits](#hard-limits)
- [What is not built](#what-is-not-built)
- [No sign-in and no job owners](#no-sign-in-and-no-job-owners)
- [Files and results are kept until removed](#files-and-results-are-kept-until-removed)
- [Use only synthetic files for now](#use-only-synthetic-files-for-now)
- [Measured on the real gateway](#measured-on-the-real-gateway)
- [Run only against the fake gateway](#run-only-against-the-fake-gateway)

## Hard limits

### Files

| Limit | Value | Set by | What happens beyond it |
|---|---|---|---|
| Size of an uploaded file | 200 MB | Fixed in the code | The upload is refused: `the file is larger than 200 MB`. On the public endpoint the reply is HTTP 413 with the code `file_too_large`. |
| Size of a text file | 5 MB | Fixed in the code | Refused: `<name> is larger than 5 MB of text. Split it, or send it as a PDF.` |
| Page size of a text file | About 3,000 characters, never under 200 | `documents.text_page_chars` | A longer file gets more pages. A single line longer than a page is split across pages. |
| Size of an image | Scaled down to 1,568 pixels on its long edge | `documents.image_max_px` | The image is scaled when uploaded, and stored as PNG or JPEG. The code aims to keep the stored image under 3.5 MB. |
| Frames of an animated GIF or multi-page TIFF | The first only | Fixed in the code | The other frames are ignored. |
| File kinds | PDF, image (PNG, JPEG, GIF, WebP, BMP, TIFF), text | Fixed in the code | Office files and unknown binary files are refused. |
| Files per source | One | Not built | See [What is not built](#what-is-not-built). |

### Runs

| Limit | Value | Set by | What happens beyond it |
|---|---|---|---|
| Jobs in one submission from the screens or `POST /api/jobs` | 1 to 50 | Fixed in the code | Refused: `submit between 1 and 50 jobs at a time`. |
| Jobs in one submission before confirmation is needed | 4 | `server.saturating_jobs` | The screens ask for confirmation; `load` needs `--confirm-saturation`. |
| Jobs per request on the public endpoint | One | Fixed in the code | Each request starts one job. There is no confirmation and no limit on the number of requests. |
| Pages of a file attached whole to a step as a [reference](../glossary.md#reference) | 100 | `worker.max_reference_pages` | The run is refused before a job is created. |
| Length of a text or JSON [value input](../guide/value-inputs.md) | 20,000 characters | `worker.max_value_chars` | The run is refused: `Input "<name>" is longer than 20,000 characters. Send long content as a file.` |
| Length of a job label on the public endpoint | 200 characters | Fixed in the code | The label is cut. |
| Published flows with the same name | One | Fixed in the code | Publishing is refused until the flow is renamed. Callers run a flow by its name. |

### Model calls

| Limit | Value | Set by | What happens beyond it |
|---|---|---|---|
| Size of one request to the gateway | 16 MB | `gateway.max_request_mb` | The request is not sent. The call fails with `request is N MB; the limit is 16 MB. Use a smaller window.` and the job fails. |
| Duration of one call | 600 seconds | `gateway.request_timeout_s` | The call counts as a timeout and is tried again. |
| Attempts per call for timeouts, gateway errors and replies that do not match their schema | 3 | `worker.max_transient_attempts` | The job fails. Rejections (429) never count. |
| Calls in flight per process | 128 | `worker.concurrency` | Further calls wait, even if the quota has room. |
| HTTP connections to the gateway per process | 512 | `gateway.max_connections` | Must exceed `worker.concurrency`. |
| Database connections per process | 16 | `postgres.pool_size` | Further database work waits for a free connection. |
| Time an admitted call may hold its place | 900 seconds | `ledger.lease_s` | The call is treated as lost and returned to the queue. |
| Input tokens, output tokens and queries per model | 1,000,000 per minute, 100,000 per minute, 360,000 per hour (Haiku: 200,000 and 20,000 per minute) | `models.<name>.itpm`, `otpm`, `qph` | The ledger holds calls back to stay under them. |

The 16 MB guard and the 100-page reference limit are separate. A whole-file reference within 100 pages can
still make a request larger than 16 MB if its pages are heavy, and the job then fails at that call.

### Screens and listings

| Limit | Value |
|---|---|
| Jobs returned by `GET /api/jobs` | 60 by default, at most 300 |
| Jobs listed on **Activity** | The 80 most recent |
| Events loaded for one job on the Run screen and in a replay | The first 30,000 |
| Calls listed for one step of a job | 200 by default |
| Jobs listed by the `jobs` command | 20 by default (`--limit`) |

## What is not built

- **Fold**. The instructions are Map, Reduce and Filter. A flow that uses Fold is refused:
  `Fold is not available yet. Use Map or Reduce.`
- Adaptive reduce.
- Batches of files as one source: the same flow on each of N files in one submission.
- Comments.
- A shared block library.
- Entitlements.
- Reuse of earlier results.
- A comparison with naive scheduling on the screens.
- An availability period for files and results.
- Job owners.
- Callbacks from the public endpoint. Callers poll the status address.

The public endpoint, once on this list, is built: callers run the published version of a flow by its name,
poll its status and fetch its results under `/api/v1/`. See the [API reference](../api/reference.md).

## No sign-in and no job owners

The application has no sign-in of its own, and a job records no owner.

- Anyone who can reach the application's address can use every screen and every address of the API: build,
  change, publish and delete flows; upload and remove files; submit and cancel any job; read any result.
- The public endpoint under `/api/v1/` asks for no key.
- A value input is written into the prompt as it was sent. Whoever can submit a run can therefore change what
  a step is told, within that one run.
- Nothing limits how many jobs a caller starts, so any caller can saturate the endpoint.

Access therefore has to be controlled around the application, by whatever serves its address.

> **Not yet confirmed:** what access control Databricks Apps puts in front of the application has not been
> looked at with this codebase. It will be, in the first deployment.

## Files and results are kept until removed

There is no retention period yet. Everything stays in Postgres until someone removes it.

| What | Where it is kept | How it is removed |
|---|---|---|
| Uploaded files, whole | The `documents` table | One at a time on the [Files screen](../guide/files-screen.md). A file used by a job that has not finished cannot be removed. Sample files cannot be removed. |
| Files sent with a job through the public endpoint | The `documents` table. They are listed on the Files screen. | The same way. A request that is refused keeps none of the files it brought. |
| Jobs, their outputs, every call and every event | The `jobs`, `job_steps`, `tasks`, `calls`, `events` and `reservations` tables | No screen and no command removes one job. `python -m doc_engine db reset --yes` removes everything. |

Removing a file keeps the results of past jobs, but their page views of that file stop working.

Storage only grows. The query in [Monitoring](monitoring.md#how-much-is-stored) shows how much the files
take.

## Use only synthetic files for now

Until data handling has been decided, upload only synthetic files: files that were made up and describe no
real person or organisation. The installed samples are fictional and are safe to use.

The reasons are in the sections above and in how the application works:

- An uploaded file is stored whole in the database and is sent, in parts or whole, to the model gateway.
- The model's outputs, which quote the files, are stored with the job, and `export` writes them to CSV files.
- There is no sign-in: everyone who can reach the application can read every file and every result.
- There is no retention period: nothing is removed unless someone removes it.

## Measured on the real gateway

These facts were measured in the proof of concept on Sonnet 5.5, at 1,000,000 input and 100,000 output tokens
per minute. They are what the scheduler is built around.

- The gateway reserves nothing when a call starts and charges the actual output when the call completes,
  against a bucket that refills at OTPM/60 per second.
- The gateway's own output bucket is about 40,000 tokens. An output cap of 45,000 gave no rejections in six
  runs with calls of about 9 seconds.
- A rejection names the limit only in its message text. It carries no retry timing.
- Sonnet 5.5 answers `{"type": "disabled"}` for thinking with a 400.
- A PDF page costs about 1,832 input tokens in a one-page window and about 1,623 per page in four-page
  windows.
- Cache reads do not count against the input limit; cache writes do.
- The largest request the gateway accepts is between 18.3 and 23.5 MB. Above it, the gateway answers with a
  misleading "malformed JSON" error.

Nothing has been measured for Haiku 5.5 or Opus 5.5.

## Run only against the fake gateway

This codebase has never called the real gateway. What follows has passed on the
[fake gateway](fake-gateway.md), which shows that the code runs and nothing more.

| Area | Status |
|---|---|
| The whole codebase | Run only against the fake gateway. |
| Haiku 5.5 and Opus 5.5 budgets | Placeholders until `probe bucket` has been run for each. |
| The `thinking_off` forms for Haiku and Opus | Not sent to the real gateway. Preflight checks them. |
| `duration` capacity mode | Not run on the real gateway. |
| Several worker processes; recovery after a worker is killed | Pass on the fake gateway. |
| Flows with several sources and references | Pass on the fake gateway. The prompts and page references have not met a real model. |
| Value inputs in prompts and filter rules | Pass on the fake gateway. Whether a real model acts on the values has not been checked. |
| Images and text files as sources | Pass on the fake gateway. Image input has not been sent to the real gateway; preflight checks it per model. |
| `preflight`, `probe bucket` and `load` | Run only against the fake gateway. |
| Lakebase | Not yet run. This includes `LISTEN/NOTIFY` and short-lived tokens as the password. |
| Databricks Apps deployment | Not yet run. This includes installation of `requirements.txt`, the `databricks_oauth` routes and the platform's port. |

> **Not yet confirmed:** every row of this table. The gateway rows are checked in the
> [first session on the real gateway](first-real-session.md); the
> Lakebase and Databricks Apps rows in the
> [first deployment](databricks.md#what-to-confirm-in-the-first-deployment).

## See also

- [The fake gateway](fake-gateway.md): what the stand-in imitates and why it proves nothing about the real one.
- [Deploying to Databricks Apps](databricks.md): the checklist that turns "not confirmed" into "confirmed".
- [Troubleshooting](troubleshooting.md): the messages a reader sees when a limit is reached.
- [Settings reference](settings.md): the settings behind the limits that can be changed.
- [File types](../guide/file-types.md): what each kind of file becomes when uploaded.
