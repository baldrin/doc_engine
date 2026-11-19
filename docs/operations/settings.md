[Documentation](../README.md) › [Setup and operations](README.md) › Settings reference

# Settings reference

Every setting in the settings file, section by section, with its meaning, its default and when to change it;
the environment variables that override settings; the rules the application enforces at start; how prices are
set; and how to add or re-size a model. For whoever configures Document Engine.

**On this page**

- [Where settings come from](#where-settings-come-from)
- [gateway](#gateway)
- [models](#models)
- [ledger](#ledger)
- [worker](#worker)
- [postgres](#postgres)
- [server](#server)
- [documents](#documents)
- [Environment variables](#environment-variables)
- [Rules enforced at start](#rules-enforced-at-start)
- [Values that are not checked](#values-that-are-not-checked)
- [Prices](#prices)
- [Adding a model](#adding-a-model)
- [Re-sizing a model](#re-sizing-a-model)

## Where settings come from

Settings live in one YAML file. The application looks for it in this order:

1. the path given with `--config` on the command line;
2. the path in the environment variable `DOC_ENGINE_CONFIG`;
3. `config.yaml` in the repository root.

`config.example.yaml` is the documented template. Copy it to `config.yaml` and fill in the values marked
`FILL-IN`. `config.yaml` is not committed. No secret goes in the file.

Settings are read once, when a command starts. Change the file, then restart. The defaults below are the
values in `config.example.yaml`.

## gateway

How the application reaches the Databricks AI Gateway.

| Setting | Default | Meaning | When to change it |
|---|---|---|---|
| `base_url` | `FILL-IN` | The workspace's Anthropic-style endpoint, for example `https://<workspace-host>/serving-endpoints/anthropic`. | Always: it must be set, here or with `DOC_ENGINE_GATEWAY_URL`. |
| `token_env_var` | `DATABRICKS_TOKEN` | The *name* of the environment variable that holds the bearer token. | When your token is in a differently named variable. |
| `token_source` | `env` | `env` reads the variable above. `databricks_oauth` uses the app's service principal on Databricks Apps. | On Databricks Apps, if you prefer the service principal to a stored token. |
| `request_timeout_s` | `600` | Seconds before a model call is abandoned as a timeout. The gateway's documented execution limit is 597 seconds. | Rarely. `ledger.lease_s` must stay larger. |
| `max_connections` | `512` | The most HTTP connections the process keeps to the gateway. Logged at start. | Only together with `worker.concurrency`, which it must exceed. |
| `streaming` | `auto` | `auto` streams the calls of a step that makes one or two calls (typically a Reduce), so the Run screen can show progress. `always` streams every call. `never` streams none. Warm-up calls are never streamed. | If streaming causes trouble on your gateway, set `never`. |
| `max_request_mb` | `16` | A request larger than this is not sent; the [task](../glossary.md#task) fails with a clear message instead. The gateway's ceiling was measured between 18.3 and 23.5 MB in the proof of concept on Sonnet 5.5, and above it the gateway answers with a misleading "malformed JSON" error. | Leave it below the measured ceiling. |

## models

One entry per model. The key (`haiku`, `sonnet`, `opus`) is the name [steps](../glossary.md#step) store and the
`--model` option takes. Each model has its own budget; the engine never shares a budget between models.

| Setting | Default | Meaning | When to change it |
|---|---|---|---|
| `label` | for example `Claude Sonnet` | The name shown on the screens. Falls back to the key. | To rename a model on screen. |
| `gateway_name` | for example `system.ai.claude-sonnet-5-5` | The model name sent to the gateway. | When the workspace serves the model under another name. |
| `itpm` | `1000000` (`200000` for Haiku) | The endpoint's input tokens per minute for this model. | When the endpoint tier changes. |
| `otpm` | `100000` (`20000` for Haiku) | The endpoint's output tokens per minute for this model. The ledger drains at this rate. | When the endpoint tier changes. Then [re-size the model](#re-sizing-a-model). |
| `qph` | `360000` | Queries per hour. The ledger stops admitting when the last hour's admissions reach it. It counts whole minutes, so it may count up to one minute more than the hour, which errs on the safe side. `0` or absent turns the check off. | When the endpoint tier changes. |
| `bucket_capacity_output` | `45000` (`8000` for Haiku) | The output cap in `fixed` capacity mode, before the safety margin. | Only from a reviewed bucket probe result. |
| `bucket_measured` | `40000` (`8000` for Haiku) | The gateway's own output bucket, used in `duration` capacity mode. Falls back to `bucket_capacity_output`, then `otpm`. | After a bucket probe: the probe prints the value to set. |
| `thinking_off` | per model | How "thinking off" is sent to this model: `disabled`, `between_tools` or `effort_low`. | When preflight says the model refuses its form; preflight prints the line to set. |
| `cache_min_tokens` | `1024` or `4096` | The model's minimum cacheable prompt size. A shorter static prompt is not marked for caching and gets no warm-up. | When the model's minimum changes. |
| `input_tokens_per_page` | `1728` | Estimated input tokens for one PDF page, used in estimates and admission. Images and text files carry their own figure. | When measured page costs differ on your files. |
| `pricing` | per model | USD per million tokens: `input`, `output`, `cache_read`, `cache_write`. See [Prices](#prices). | When list prices or your rates change. |

What is and is not measured for the shipped values:

| Model | `thinking_off` | Budget values |
|---|---|---|
| `sonnet` | `between_tools`. This model answers `{"type": "disabled"}` with a 400. | `bucket_capacity_output: 45000` gave no rejections in six runs, and the gateway's own bucket is about 40,000: measured in the proof of concept on Sonnet 5.5. |
| `haiku` | `disabled` | `itpm: 200000` and `otpm: 20000` are the endpoint's limits for this model. `bucket_capacity_output: 8000` and `bucket_measured: 8000` are an estimate (the same share of OTPM as Sonnet's measured bucket), not a measurement. `qph` is copied from Sonnet. |
| `opus` | `effort_low`. Thinking cannot be turned off on this model, so "off" sends the lowest effort. | Placeholders copied from Sonnet. |

> **Not yet confirmed:** the Haiku bucket values, the Opus budgets, and all three `thinking_off` forms as sent by this
> codebase. Preflight checks the forms in the [first session on the real gateway](first-real-session.md); `probe bucket` measures the Haiku and Opus
> budgets in the same session.

## ledger

How the [quota ledger](../how-it-works/quota-ledger.md) decides what may be sent.

| Setting | Default | Meaning | When to change it |
|---|---|---|---|
| `safety_margin_fraction` | `0.05` | The share of each cap left unused. | Raise it if rejections appear in normal running. |
| `capacity_mode` | `fixed` | How the output cap is worked out. `fixed`: `bucket_capacity_output` × (1 − margin). `duration`: (`bucket_measured` + refill during half a call) × (1 − margin), using the learned call length when `learn_estimates` is `true`, so it adapts to short and long calls. With `learn_estimates: false` it always uses `default_call_s`. The quota panels and `/api/quota` show the cap that admission last used. | `duration` when call lengths are far from the 9 seconds `fixed` was validated with. |
| `default_call_s` | `9` | In `duration` mode, the call length assumed until a step has three recorded calls, and always when `learn_estimates` is `false`. | When typical calls are much shorter or longer. |
| `hold_on_429_s` | `1` | The first pause after a rejection: admission for that model stops this many seconds, for every worker. | Rarely. |
| `hold_on_429_max_s` | `15` | The longest pause. Each further round of rejections doubles the pause up to this; an accepted call puts it back to `hold_on_429_s`. Set it equal to `hold_on_429_s` for a fixed pause. | Raise it if the gateway rejects for longer than this after an overrun. |
| `learn_estimates` | `true` | Count each call in flight at the learned mean output of its step once the step has three recorded calls. When `false`, the step's configured expectation is always used, and `duration` mode always uses `default_call_s` as the call length. | Set `false` only to diagnose estimates. |
| `lease_s` | `900` | How long an admitted call may run before it is treated as lost and returned to the queue. | Must exceed `gateway.request_timeout_s`. |
| `dead_worker_after_s` | `30` | A worker that has not reported for this long is treated as gone, and its calls return to the queue. | Lower for faster recovery; not below a few heartbeats (workers report every 5 seconds). |
| `max_recoveries_per_call` | `3` | How often one call may be returned to the queue because its worker was lost or its lease ran out. A call returned more often than this is not sent again, and its job fails with a message that says so. A warm-up in that position is dropped, and the step's calls run without it. A clean stop of a worker returns its calls but never fails a job this way. `0` means no limit. See [Failures and recovery](../how-it-works/failures-and-recovery.md#a-worker-that-dies). | Rarely. |
| `reaper_interval_s` | `5` | How often each worker looks for lost calls. | Rarely. |

> **Not yet confirmed:** `duration` mode has not run on the real gateway. It is the mode `config.fake.yaml`
> uses. It will be tried on the real gateway after the first session's fixed-mode runs.

## worker

The workers that make the model calls.

| Setting | Default | Meaning | When to change it |
|---|---|---|---|
| `enabled` | `true` | Run a worker inside the web process. | Set `false` to run `python -m doc_engine worker` processes separately. |
| `concurrency` | `128` | The most model calls in flight per process. | Must stay below `gateway.max_connections`. |
| `max_transient_attempts` | `3` | How many times a call is tried when it times out, gets a server error, or returns a reply that does not match its schema. A rejection (429) never counts. | Raise for an unreliable endpoint. |
| `retry_delays_s` | `[2, 10, 30]` | Seconds to wait before the second, third and later attempts after a timeout or server error. The last value repeats. A reply that does not match its schema is retried at once. | Lengthen to ride out longer gateway outages. |
| `max_rejections_per_call` | `50` | A call rejected (429) this many times in a row fails, and its job fails. `0` means no limit. | Raise if other applications share the quota and long waits are acceptable. |
| `cache_warmup` | `true` | Send one small call per model and static prompt to write the prompt cache; the step's calls wait for it. Jobs submitted together share that one call. See [Prompt caching](../how-it-works/prompt-caching.md). | Set `false` to stop warm-ups. |
| `warmup_max_tokens` | `1` | `max_tokens` of the warm-up call. | Rarely. |
| `warmup_min_tasks` | `3` | Steps with fewer calls than this get no warm-up. | Rarely. |
| `max_reference_pages` | `100` | The largest file that may be attached whole to a step as a [reference](../glossary.md#reference). A run that would exceed it is refused. | With care: a whole-file reference is sent, and paid for, on every call of the step. |
| `max_value_chars` | `20000` | The longest text or JSON [value input](../guide/value-inputs.md). | Rarely; longer content belongs in a file. |
| `send_images_as` | `image` | `image` sends an image file as an image. `pdf` wraps it in a one-page PDF. | Set `pdf` when preflight shows a model refuses image input. |
| `warmup_ttl_s` | `240` | A cache entry warmed more recently than this is reused by other jobs, which then skip their own warm-up. | Rarely. |
| `warmup_settle_s` | `0` | Pause after a warm-up before the step's calls are released. Off by default. | A remedy if the first calls after a warm-up miss the cache. |
| `first_wave_size` | `0` | `0` means no limit. Otherwise, after a warm-up, release this many calls, and the rest when the first of them completes. Off by default. | The other remedy for first-wave cache misses. |

## postgres

The database connection.

| Setting | Default | Meaning | When to change it |
|---|---|---|---|
| `host` | `FILL-IN` | Database host. Empty or `FILL-IN` falls back to `PGHOST`. | Always, here or in the environment. |
| `port` | empty | Database port. Empty falls back to `PGPORT`, then 5432. | When the database listens elsewhere and `PGPORT` is not set. |
| `dbname` | `FILL-IN` | Database name. Empty or `FILL-IN` falls back to `PGDATABASE`. | Always, here or in the environment. |
| `user` | `FILL-IN` | Database user. Empty or `FILL-IN` falls back to `PGUSER`. | Always, here or in the environment. |
| `password_env_var` | `PGPASSWORD` | The *name* of the environment variable that holds the password. Read at every connect. | When the password is in a differently named variable. |
| `password_source` | `env` | `env` reads the variable above. `databricks_oauth` uses the app's OAuth token as the password (Lakebase from a Databricks App). | On Databricks Apps. |
| `password_command` | empty | An optional shell command that prints the password. Run at every connect. | When the password comes from a credential tool. |
| `sslmode` | empty | TLS mode of the connection. Empty falls back to `PGSSLMODE`, then `require`. | `prefer` for a local Postgres without TLS. |
| `pool_size` | `16` | The most database connections one process uses at a time. | Raise if the database allows and the process is busy. |

The password is chosen in this order: `password_source: databricks_oauth`, then `password_command` if set,
then the environment variable. If none yields a value, the connection is attempted without a password.

## server

| Setting | Default | Meaning | When to change it |
|---|---|---|---|
| `host` | `0.0.0.0` | The address the web server binds. | To restrict it to one interface. |
| `port` | `8000` | The port. `DATABRICKS_APP_PORT`, then `PORT`, override it. | When 8000 is taken. |
| `saturating_jobs` | `4` | Submitting this many jobs at once, or more, asks for confirmation on the screens and in the `load` command. | To match how many simultaneous jobs your endpoint tolerates. |

## documents

How uploaded files are prepared. The section is optional; the defaults apply without it.

| Setting | Default | Meaning | When to change it |
|---|---|---|---|
| `image_max_px` | `1568` | An uploaded image is scaled down to this on its long edge. | Rarely. Affects new uploads only. |
| `text_page_chars` | `3000` | A text file is split into pages of about this many characters, at line ends. Values under 200 are treated as 200. | To change page size. Affects new uploads only: a text file's pages are fixed when it is uploaded. |

See [File types](../guide/file-types.md) for what each kind of file becomes.

## Environment variables

| Variable | Effect |
|---|---|
| `DOC_ENGINE_CONFIG` | Path of the settings file. |
| `DOC_ENGINE_GATEWAY_URL` | Replaces `gateway.base_url`. |
| `DOC_ENGINE_TOKEN_SOURCE` | Replaces `gateway.token_source`. |
| `DOC_ENGINE_PG_PASSWORD_SOURCE` | Replaces `postgres.password_source`. |
| `DATABRICKS_TOKEN` (or the name in `gateway.token_env_var`) | The gateway token. Read for every call. |
| `PGPASSWORD` (or the name in `postgres.password_env_var`) | The Postgres password. Read at every connect. |
| `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE` | Used for a `postgres` value that is empty in the file (or `FILL-IN`). A value written in the file wins. |
| `DATABRICKS_APP_PORT`, then `PORT` | The port `serve` listens on. Either overrides `server.port`. |

The three `DOC_ENGINE_...` overrides exist so that a deployment can run from `config.example.yaml` with no
edits. See [Deploying to Databricks Apps](databricks.md#environment-variables).

## Rules enforced at start

Every command reads and checks the settings before doing anything. If a rule fails, the command stops and
prints `config problems in <path>:` followed by one line per problem.

| Rule | Message |
|---|---|
| The sections `gateway`, `models`, `ledger`, `worker`, `postgres` and `server` must all be present. | `missing section: <name>` |
| At least one model must be configured. | `models: at least one model is required` |
| Each model must have `gateway_name`, `itpm`, `otpm`, `bucket_capacity_output` and `pricing`. | `models.<name>.<field> is missing` |
| Each model's `thinking_off` must be one of the three forms. | `models.<name>.thinking_off must be disabled, between_tools or effort_low` |
| `ledger.lease_s` must be larger than `gateway.request_timeout_s`. | `ledger.lease_s must exceed gateway.request_timeout_s` |
| `gateway.max_connections` must be larger than `worker.concurrency`. | `gateway.max_connections must exceed worker.concurrency` |

If the file does not exist, the command stops with `config file not found: <path>`.

Values still set to `FILL-IN` do not stop a command. `preflight` reports them, and most other commands print
`config still has FILL-IN values: ...` and carry on.

## Values that are not checked

A few settings are not validated. A mistyped value is accepted silently and behaves like this:

| Setting | A value that is not recognised behaves as |
|---|---|
| `ledger.capacity_mode` | `fixed` (only the exact word `duration` selects duration mode) |
| `gateway.streaming` | `never` |
| `worker.send_images_as` | `image` |
| `gateway.token_source`, `postgres.password_source` | `env` |

A model's `pricing` is checked only for being present. A missing price inside it causes an error later, when
a cost is worked out.

## Prices

Prices are set per model under `models.<name>.pricing`, in USD per million tokens:

```yaml
pricing: { input: 3.00, output: 15.00, cache_read: 0.30, cache_write: 3.75 }
```

All four values are needed. They feed the cost [estimate](../how-it-works/estimates.md) in the builder, the
cost shown for a job, the summary of the `load` command and the estimate `probe bucket` prints. Haiku is priced
at its short-context rate.

A job's cost is worked out from its recorded token counts each time it is shown, with the prices then in the
settings. Changing a price therefore changes the cost shown for past jobs as well.

## Adding a model

1. Add an entry under `models` with a key of your choice. `gateway_name`, `itpm`, `otpm`,
   `bucket_capacity_output` and `pricing` are required. Set `label`, `cache_min_tokens` and
   `input_tokens_per_page` too; start `bucket_capacity_output` and `bucket_measured` from a model already
   measured, and treat them as placeholders.
2. Restart. At start the limits are copied into the model's row in the `quota` table, and the model appears
   in the builder.
3. Run `python -m doc_engine preflight`. It tells you whether the model answers and which `thinking_off` form
   it accepts, and prints the line to set if the configured one is refused.
4. Measure its bucket: [re-size the model](#re-sizing-a-model).

Removing or renaming a model's key has two effects. A flow whose step uses the old key can no longer run or
be published: validation reports that the step "uses a model that is not configured". And the old row stays in
the `quota` table, so the model still appears in `/api/quota` and on the quota panels until the row is deleted
by hand.

## Re-sizing a model

Do this when the endpoint tier changes, and for Haiku and Opus before relying on them.

1. Set `itpm`, `otpm` and `qph` to the new limits.
2. See what the probe will send and cost:

   ```bash
   python -m doc_engine probe bucket --model <name> --dry-run
   ```

3. Run it. It saturates the model on purpose, so agree a time first.

   ```bash
   python -m doc_engine probe bucket --model <name> --confirm-saturation
   ```

4. The probe prints a bucket estimate and the line to set: `models.<name>.bucket_measured`. It writes its raw
   data under `results/`.
5. Keep `bucket_capacity_output` as it is until the result has been reviewed. Do not scale the bucket by hand
   in proportion to the limits.
6. Restart every instance. Each start copies the limits into the shared `quota` row, so all instances must run
   with the same settings.

See [Commands](commands.md#probe-bucket) for the probe's options and output.

## See also

- [Commands](commands.md): `preflight` and `probe bucket`, which tell you what to set.
- [Deploying to Databricks Apps](databricks.md): running from the example file with environment variables.
- [The quota ledger](../how-it-works/quota-ledger.md): what the `models` and `ledger` values control.
- [Prompt caching](../how-it-works/prompt-caching.md): what the warm-up settings do.
- [Troubleshooting](troubleshooting.md#the-application-will-not-start): when the settings are refused at start.
