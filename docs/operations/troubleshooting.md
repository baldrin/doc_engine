[Documentation](../README.md) › [Setup and operations](README.md) › Troubleshooting

# Troubleshooting

Symptoms, their causes in the code, and what to do. The messages are quoted as the application prints them,
so you can search this page for the text you see. For whoever installs or operates Document Engine.

**On this page**

- [The application will not start](#the-application-will-not-start)
- [Preflight reports a problem](#preflight-reports-a-problem)
- [A model refuses its "thinking off" form](#a-model-refuses-its-thinking-off-form)
- [Image input is refused](#image-input-is-refused)
- [Rejections appear](#rejections-appear)
- [Jobs stay queued](#jobs-stay-queued)
- [A job failed](#a-job-failed)
- [A run is refused before it starts](#a-run-is-refused-before-it-starts)
- [An upload is refused](#an-upload-is-refused)
- [A file cannot be removed](#a-file-cannot-be-removed)
- [The frontend has not been built](#the-frontend-has-not-been-built)

## The application will not start

### The settings file is missing

```text
config file not found: <path>
Copy config.example.yaml to config.yaml and fill it in, or set DOC_ENGINE_CONFIG.
```

The application looks for the file named by `--config`, then by `DOC_ENGINE_CONFIG`, then for `config.yaml`
in the repository root. Create it as [Local setup](local-setup.md#route-2-by-hand) describes. A relative path
in `DOC_ENGINE_CONFIG` is relative to the directory the command is run from.

### The settings break a rule

```text
config problems in <path>:
  - ledger.lease_s must exceed gateway.request_timeout_s
```

Each line names one problem.

| Message | What to do |
|---|---|
| `missing section: <name>` | Restore the section from `config.example.yaml`. |
| `models: at least one model is required` | Add a model under `models`. |
| `models.<name>.<field> is missing` | Add the field. `gateway_name`, `itpm`, `otpm`, `bucket_capacity_output` and `pricing` are required for every model. |
| `models.<name>.thinking_off must be disabled, between_tools or effort_low` | Use one of the three forms. |
| `ledger.lease_s must exceed gateway.request_timeout_s` | Raise `lease_s` or lower `request_timeout_s`. |
| `gateway.max_connections must exceed worker.concurrency` | Raise `max_connections` or lower `concurrency`. |

See [Rules enforced at start](settings.md#rules-enforced-at-start).

### The database cannot be reached

The log shows the attempts, then the start fails:

```text
postgres connect failed (attempt 1): ...
...
could not connect to Postgres after retries: ...
```

Six attempts are made, with pauses that grow from half a second to eight seconds. The text after the colon is
the database driver's own message. Common causes:

| Cause | What to do |
|---|---|
| The password variable is not exported in this shell. | `export PGPASSWORD=...`, or the variable named by `postgres.password_env_var`. Without it the connection is attempted with no password. |
| `postgres.host`, `dbname` or `user` is still `FILL-IN` and the matching `PGHOST`, `PGDATABASE` or `PGUSER` is not set. | Fill in the values, or set the variables. |
| `postgres.sslmode` is `require` and the server has no TLS, as with a plain local Postgres. | Set `sslmode: prefer`. The setup script does this. |
| The port is wrong. A `postgres.port` written in the file wins over `PGPORT`. | Correct `postgres.port`, or leave it empty to use `PGPORT`. |
| Postgres is not running. | Start it. In the development container, run `bash scripts/dev_up.sh` again. |
| `password_source` is `databricks_oauth` outside Databricks, or the `databricks-sdk` package is absent. | The start fails at once with an import error naming `databricks`, or with the SDK's own authentication error. Use `env` outside Databricks. |

While the application is running, a lost connection is retried by itself: the log shows
`database operation failed (attempt N): ...`, and broken connections are replaced.

### Tables are missing

`serve` creates missing tables by itself on every start, so it does not stop for this. If the start fails
while applying the schema, the database role lacks permission to create tables or functions.

Other commands do not create tables:

| Command | What you see |
|---|---|
| `db check` | `missing tables: ...` |
| `preflight` | ``tables missing (...). Run `python -m doc_engine db init`.`` |
| `load` | ``the database is not set up. Run `python -m doc_engine db init` first.`` |
| `samples`, `jobs`, `export`, `worker` | A Postgres error saying a relation does not exist. |

In every case, run `python -m doc_engine db init`.

## Preflight reports a problem

Preflight ends with `preflight found problems (see above)`. Find the line that caused it.

| Line | Cause | What to do |
|---|---|---|
| `FILL-IN values remain: ...` | The named settings are still `FILL-IN`, and for a `postgres` setting its `PG*` variable is not set either. | Fill them in, or set the variable. |
| `FAILED: could not connect to Postgres after retries: ...` | The database cannot be reached. | See [The database cannot be reached](#the-database-cannot-be-reached). |
| `tables missing (...)` | The schema has not been applied. | `python -m doc_engine db init` |
| `LISTEN/NOTIFY: not available (...)` | The database does not support notifications on this connection. | Nothing is required. Workers then notice new work by timed checks, at most a second late. This line does not make preflight fail. |
| `skipped: gateway.base_url is not set` | `gateway.base_url` is `FILL-IN` and `DOC_ENGINE_GATEWAY_URL` is not set. | Set one of them. |
| `thinking off as '<form>': permanent HTTP None: RuntimeError: environment variable DATABRICKS_TOKEN is not set (gateway token)` | The token variable is not exported. | See [The token variable is not set](#the-token-variable-is-not-set). |
| `thinking off as '<form>': permanent HTTP 400: ...` | The model refuses the configured form. | See [the next section](#a-model-refuses-its-thinking-off-form). |
| `thinking off as '<form>': permanent HTTP <401, 403 or 404>: ...` | The token is not accepted, or `gateway.base_url` or the model's `gateway_name` is wrong. The gateway's own message follows the colon. | Check the token, the address and the model name. Every model fails the same way when the token or address is at fault. |
| `thinking off as '<form>': transient ...` | A timeout, a connection failure, or a server error from the gateway. | Check that the address is reachable from this machine, then try again. |
| `thinking off as '<form>': 429 HTTP 429: ...` | The endpoint is saturated right now, by this or another application. | Wait a minute and run preflight again. |
| `adaptive thinking, low effort: <not ok> ...` | The model refuses the form used for thinking levels low, medium and high. | Steps on this model must keep thinking **off** until this is resolved. |
| `image input: ...` not `OK` | The model refuses image input. | See [Image input is refused](#image-input-is-refused). This line does not make preflight fail. |

> **Not yet confirmed:** the status codes the real gateway returns for a wrong token, address or model name
> have not been observed with this codebase. They will be seen, if at all, in the [first session on the real gateway](first-real-session.md).

## A model refuses its "thinking off" form

**Symptom.** Preflight prints `thinking off as '<form>': permanent HTTP 400: ...`. In a job, every call of a
step that has thinking off on that model fails with `Request failed (HTTP 400): ...`.

**Cause.** Models differ in how thinking can be turned off, and each model's entry says which form to send:

| `thinking_off` | What is sent | Shipped for |
|---|---|---|
| `disabled` | `{"type": "disabled"}` | Haiku |
| `between_tools` | `{"type": "between_tools"}`. The engine sends no tools, so this amounts to off. | Sonnet, which answers `disabled` with a 400 (measured in the proof of concept on Sonnet 5.5) |
| `effort_low` | Adaptive thinking at the lowest effort. Thinking cannot be turned off on such a model. | Opus |

**What to do.** After the failing line, preflight tries the other two forms and prints the remedy:

```text
      trying 'between_tools': ok
      -> set models.haiku.thinking_off: between_tools
```

Set that line in the settings file, restart, and run preflight again. If no form works, preflight prints no
remedy: steps on that model can then only run with a thinking level of low, medium or high, provided the
`adaptive thinking, low effort` line is `ok`.

## Image input is refused

**Symptom.** Preflight prints:

```text
    image input: permanent HTTP 400: ...
      -> image files cannot be sent as images to this model. Set worker.send_images_as: pdf
```

In a job, the calls of a step that reads an image file fail with `Request failed (HTTP ...): ...`.

**What to do.** Set `worker.send_images_as: pdf` and restart. Every image is then wrapped in a one-page PDF
before it is sent. The setting applies to all models. Nothing needs uploading again.

If the `thinking off` line for the same model also failed, fix that first and run preflight again: the image
check uses the same form and fails with it.

If preflight prints `image input: OK (reply '...', expected 742, ...)`, the model accepted the image but did
not read the number in it. Nothing is refused; look at the reply before relying on image files with that
model.

> **Not yet confirmed:** image input has not been sent to the real gateway. Preflight checks it per model in
> the first session. PDF input is the form the proof of concept measured.

## Rejections appear

**Symptom.** **Rejections, last 60 s** on **Activity** is above zero; the Run screen shows
`Gateway rejected a call (output) · <model> paused 1 s`; `load` reports `rejections N`.

**What a rejection does.** The gateway answered a call with HTTP 429. The call returns to the queue without
using one of its attempts, and admission for that model pauses for every worker: `ledger.hold_on_429_s` seconds at first, doubling
while rejections continue, up to `ledger.hold_on_429_max_s`. No job fails because of rejections. A few are harmless; a steady stream means the ledger's picture of
the quota is wrong.

| Cause | How to tell | What to do |
|---|---|---|
| Another application is using the same endpoint. The ledger cannot see its use. | Rejections come and go without relation to your own load. | Raise `ledger.safety_margin_fraction`, or agree on times with the other users. |
| A saturating run or a bucket probe finished less than a minute ago, or the application was restarted during heavy use. | Rejections at the start of a run, then none. | Leave at least a minute between saturating runs. |
| The limits in the settings are higher than the endpoint's. | Rejections whenever the load is high. | Correct `itpm`, `otpm` and `qph`, then [re-size the model](settings.md#re-sizing-a-model). |
| The model's budget is a placeholder. | The model is Haiku or Opus and has not been probed. | Run `probe bucket` for it. |
| `capacity_mode` is `fixed` and the calls are much shorter than the 9 seconds the fixed cap is tuned for. With much shorter calls the fixed cap admits too much. | Rejections on steps with short calls. | Raise `ledger.safety_margin_fraction`, or try `duration` mode, which adapts to the call length. |
| A step is new, so the ledger still counts its calls at the step's configured expected output. | Rejections in the first calls of a new step that writes more than expected. | Nothing: after three calls the learned figure is used. |

To see which limit is being hit, read `limit_type` in the `calls` table: `output`, `input` or `queries`. The
query is in [Monitoring](monitoring.md#rejections-in-the-last-hour).

> **Not yet confirmed:** `duration` mode has not run on the real gateway. That 45,000 gives no rejections in
> `fixed` mode was measured in the proof of concept on Sonnet 5.5, with calls of about 9 seconds.

## Jobs stay queued

A job is **Queued** until its first call is admitted. Work through these in order.

| Check | Cause | What to do |
|---|---|---|
| `/api/health` answers 503 with `"workers": 0`. | No worker is running: `worker.enabled` is `false` and no `python -m doc_engine worker` process is up, or the worker cannot reach the database. | Start a worker, or set `worker.enabled: true` and restart. Look for `heartbeat failed` and `admission failed` in the log. |
| The job was submitted with `load --no-worker`. | That option only submits. | Start the application or a worker. |
| Other jobs are ahead of it. | The queue is strict: interactive jobs before bulk jobs, then the job submitted earlier. Nothing behind the call at the head of a model's queue is sent before it. | Wait. A bulk job waits for as long as interactive work keeps arriving. See [Queue and priority](../how-it-works/queue-and-priority.md). |
| The model shows **paused after a rejection** repeatedly. | Rejections keep pausing admission. | See [Rejections appear](#rejections-appear). |
| **Burst budget in use** stays full with nothing in flight. | The ledger believes the bucket is full, for example straight after a saturating run. The level drains at OTPM/60 per second. | Wait about a minute. |
| The log shows `admission failed: ...`. | The database is unreachable or the admission function is missing. | See [The database cannot be reached](#the-database-cannot-be-reached); run `python -m doc_engine db init`. |

To see what is waiting and why, use the queries under
[The tables in Postgres](monitoring.md#the-tables-in-postgres): open jobs, the ledger per model, and what is
waiting per model.

A job that is **Running** but makes no progress while its calls are `waiting` is waiting for a warm-up call.
If the warm-up fails, its calls are released and run without the cache.

## A job failed

The job's error is shown on the Run screen as `Run failed · ...`, in the **Jobs** table, in the `load`
summary after `ERROR:`, and in the `error` column of the `jobs` table. It has the form
`<step title>: <kind of failure>: <detail>`.

When a job fails, its calls that have not started are cancelled, and calls in flight finish and are
discarded. Nothing resumes a failed job: fix the cause and run it again.

| The error contains | Cause | What to do |
|---|---|---|
| `Request failed (HTTP <status>): ...` | The gateway refused the request for good. It is not retried. A 400 usually means a request form the model does not accept; see the two sections above. Other statuses point at the token, the address or the model name. | Run `python -m doc_engine preflight`: it makes the same kind of call and names the problem. |
| `Request failed: request is N MB; the limit is 16 MB. Use a smaller window.` | The request was larger than `gateway.max_request_mb` and was not sent. | Use a smaller window on the step, or a smaller whole-file reference. |
| `Request failed: RuntimeError: environment variable DATABRICKS_TOKEN is not set (gateway token)` | See [below](#the-token-variable-is-not-set). | Export the token and restart. |
| `Request failed: worker error: ...` | The worker could not build or record the call. The log has a traceback under `task N failed inside the worker`. One cause is a file that was removed from the database while the job needed it. | Read the traceback. |
| `Gateway error (HTTP <status>): ...` | The gateway answered 408, 409, 500, 502, 503, 504 or 529, `worker.max_transient_attempts` times in a row for the same call. | Try again later. Raise `max_transient_attempts` if the endpoint is often unsteady. |
| `Gateway error: APITimeoutError: ...` | The call took longer than `gateway.request_timeout_s`, on every attempt. | Reduce what the step is asked to write, or its window. |
| `Gateway error: APIConnectionError: ...` | The gateway could not be reached, on every attempt. | Check `gateway.base_url` and the network. |
| `Invalid reply: the reply did not match the output schema: ...` | A step with a schema output got a reply that was not valid for the schema, on every attempt. | Simplify the schema or make the prompt more explicit. A reply cut off at the maximum output is a common cause: raise the step's maximum output. |
| `Empty reply: the reply held no text (stop_reason ..., blocks [...])` | The model returned no text. With `stop_reason max_tokens`, thinking used the whole maximum output. Not retried. | Raise the step's maximum output, or lower its thinking level. |
| `The model declined this request` | The model stopped with a refusal. Not retried. | Review the step's prompt and the file. The `error` column of the job's row in `calls` holds the category and explanation, when the gateway gave them. |
| `cancelled by the user` | Someone chose **Cancel**, called the cancel address, or stopped a `load` run with Ctrl+C. The job's state is **Cancelled**, not **Failed**. | Nothing. |

A failed warm-up call does not fail a job. The Run screen shows
`warm-up failed, continuing without the cache`, and the step runs without the prompt cache.

A reply cut off at the maximum output does not fail a job either, unless the step has a schema output. It is
marked as truncated: the Run screen shows `cut off at max output`, and the `calls` table has `truncated` set.

For the full detail of a failure, query the job's calls that did not succeed:
[Monitoring](monitoring.md#the-calls-of-a-job-that-did-not-succeed).
[Failures and recovery](../how-it-works/failures-and-recovery.md) explains the rules behind this table.

### The token variable is not set

The application starts without a token. The first model call then fails, and the job with it:

```text
Request failed: RuntimeError: environment variable DATABRICKS_TOKEN is not set (gateway token)
```

The log shows `unexpected error during a model call` with a traceback. Export the variable named by
`gateway.token_env_var` in the shell or the deployment that starts the application, and restart. The token is
read for every call, so the variable must be present in the application's own environment.

## A run is refused before it starts

These are answers to a submission, not failures of a job. No job is created.

| Message | Cause |
|---|---|
| `submit between 1 and 50 jobs at a time` | More than 50 jobs, or none, in one submission from the screens. |
| `<N> jobs at once can saturate the endpoint and slow other applications in the workspace. Confirm to start.` | `server.saturating_jobs` jobs or more. The screens ask **Start a saturating run?**; confirm to go on. |
| `choose a flow`, `choose a file for <source>`, `the file chosen for <source> was not found` | Something needed was not chosen, or the file has been removed. |
| `this flow cannot run yet: ...` | The flow has problems; each is listed. One of them is a step that `uses a model that is not configured`, after a model was renamed or removed in the settings. |
| `<file> has N pages and is attached whole to every call of <step>; the limit is 100 pages. Summarize it in a step first and use that step as the reference.` | A [reference](../glossary.md#reference) to a whole file longer than `worker.max_reference_pages`. |
| `Input "<name>" ...` | A [value input](../guide/value-inputs.md) is missing, of the wrong type, not on its list of choices, or `longer than 20,000 characters` (`worker.max_value_chars`). |

## An upload is refused

The message names the file. The kind of a file is decided from its content first and its name second.

| Message | Cause | What to do |
|---|---|---|
| `the upload was empty`, `<name> is empty` | The file has no content. | Check the file. |
| `the file is larger than 200 MB`, `<name> is larger than 200 MB.` | Over the upload limit. | Split the file. |
| `<name> is an office file, which is not supported. Save it as a PDF and upload that.` | A Word, Excel, PowerPoint or similar file. | Save it as a PDF. |
| `<name> could not be read as a PDF` | The name ends in `.pdf` but the content is not a PDF, or the PDF is damaged. | Open and re-save the file. |
| `<name> has no pages` | A PDF with no pages. | Check the file. |
| `<name> could not be read as an image` | The name has an image ending but the content is not a readable image. | Re-export the image. |
| `<name> is an empty image` | The image has no width or height. | Check the file. |
| `<name> is not a file type this can read. Send a PDF, an image (PNG, JPEG, GIF, WebP, BMP, TIFF) or a text file.` | Binary content of an unknown kind. | Convert it. |
| `<name> is larger than 5 MB of text. Split it, or send it as a PDF.` | A text file over the text limit. | Split it or convert it. |
| `<name> holds no text` | A text file with only blank lines. | Check the file. |

Uploading the same content under the same name again is not an error: the file already stored is used.

See [File types](../guide/file-types.md) for what is accepted, and [Limits](limits.md#hard-limits) for the
numbers.

## A file cannot be removed

| Message | Cause |
|---|---|
| `sample files cannot be removed` | The file is one of the installed samples. |
| `<name> is in use by N runs that have not finished. Remove it when they are done.` | A queued or running job uses the file. |

## The frontend has not been built

**Symptom.** Opening the application in a browser shows:

```json
{"error": "the frontend has not been built. See README: Frontend."}
```

**Cause.** `doc_engine/static/index.html` is missing. The built frontend is committed, so this happens only
when the directory was removed or the checkout is incomplete. The API still works.

**What to do.** Restore `doc_engine/static/` from the repository, or build it. Building needs Node.js:

```bash
cd frontend && npm install
npm run build      # writes ../doc_engine/static
```

## See also

- [Monitoring](monitoring.md): where the symptoms on this page are seen, and the queries to look closer.
- [Commands](commands.md#preflight): every line preflight prints.
- [Settings reference](settings.md): the settings named in the remedies.
- [Failures and recovery](../how-it-works/failures-and-recovery.md): why some failures are retried and others are not.
- [Limits and what is not confirmed](limits.md): the limits behind the refusals.
