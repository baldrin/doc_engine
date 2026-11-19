[Documentation](../README.md) › [Setup and operations](README.md) › Deploying to Databricks Apps

# Deploying to Databricks Apps

How to run Document Engine as a Databricks App with Lakebase as its database: the entry file, the environment
variables, the two ways to authenticate, what happens on first start, and what must be confirmed the first
time. For whoever deploys and operates it on a workspace.

> **Not yet confirmed:** Document Engine has not yet been deployed to Databricks Apps and has not yet used
> Lakebase. Everything on this page describes what the code is written to do. The
> [checklist](#what-to-confirm-in-the-first-deployment) lists what the first deployment has to confirm.

**On this page**

- [How the deployment is put together](#how-the-deployment-is-put-together)
- [app.yaml](#appyaml)
- [Environment variables](#environment-variables)
- [Authenticating to the gateway](#authenticating-to-the-gateway)
- [Authenticating to Lakebase](#authenticating-to-lakebase)
- [What the application does on first start](#what-the-application-does-on-first-start)
- [Running several instances](#running-several-instances)
- [What to confirm in the first deployment](#what-to-confirm-in-the-first-deployment)
- [The first session against the real gateway](#the-first-session-against-the-real-gateway)

## How the deployment is put together

The deployment needs Python only. The built frontend is committed under `doc_engine/static/`, so nothing is
compiled on the workspace.

No file needs editing on the workspace either. The app runs from the committed `config.example.yaml` and takes
the values that file leaves open from environment variables: the gateway address, the Postgres connection and
the two secrets.

## app.yaml

`app.yaml` in the repository root is the entry point:

```yaml
command: ["python", "-m", "doc_engine", "serve"]
env:
  - name: DOC_ENGINE_CONFIG
    value: config.example.yaml
  - name: DOC_ENGINE_GATEWAY_URL
    value: "FILL-IN"
  - name: DATABRICKS_TOKEN
    valueFrom: gateway-token
  - name: DOC_ENGINE_PG_PASSWORD_SOURCE
    value: databricks_oauth
```

| Entry | What it does |
|---|---|
| `command` | Starts the web server and its in-process worker. |
| `DOC_ENGINE_CONFIG` | Makes the app read `config.example.yaml` instead of looking for `config.yaml`. |
| `DOC_ENGINE_GATEWAY_URL` | Replace `FILL-IN` with the workspace endpoint, for example `https://<workspace-host>/serving-endpoints/anthropic`. This is the one value you must edit. |
| `DATABRICKS_TOKEN` | Takes the gateway token from an app secret resource named `gateway-token`. |
| `DOC_ENGINE_PG_PASSWORD_SOURCE` | Makes the app use its own OAuth token as the Lakebase password. |

## Environment variables

Every variable the application reads:

| Variable | Purpose | Where it comes from |
|---|---|---|
| `DOC_ENGINE_CONFIG` | Path of the settings file. Without it the app reads `config.yaml` in the repository root. | `app.yaml` |
| `DOC_ENGINE_GATEWAY_URL` | Overrides `gateway.base_url`. | `app.yaml` |
| `DOC_ENGINE_TOKEN_SOURCE` | Overrides `gateway.token_source`. Set to `databricks_oauth` to use the app's service principal. | `app.yaml`, optional |
| `DATABRICKS_TOKEN` | The gateway token, when `gateway.token_source` is `env`. The name is `gateway.token_env_var`. | An app secret |
| `DOC_ENGINE_PG_PASSWORD_SOURCE` | Overrides `postgres.password_source`. Set to `databricks_oauth` to use the app's OAuth token as the password. | `app.yaml` |
| `PGPASSWORD` | The Postgres password, when `postgres.password_source` is `env`. The name is `postgres.password_env_var`. | An app secret, optional |
| `PGHOST`, `PGDATABASE`, `PGUSER` | Fill `postgres.host`, `postgres.dbname` and `postgres.user`, which the example file leaves as `FILL-IN`. | Lakebase attached to the app as a resource |
| `PGPORT`, `PGSSLMODE` | Fill `postgres.port` and `postgres.sslmode`, which the example file leaves empty. Without them the port is 5432 and the mode is `require`. | Lakebase attached to the app as a resource |
| `DATABRICKS_APP_PORT` | The port the app listens on. Overrides `server.port`. | The platform |
| `PORT` | Used as the port when `DATABRICKS_APP_PORT` is not set. Also overrides `server.port`. | Optional |

## Authenticating to the gateway

There are two routes. Choose one.

| Route | How to set it up | What the app does |
|---|---|---|
| A token in an app secret | Store a token as an app secret resource named `gateway-token`. `app.yaml` already maps it to `DATABRICKS_TOKEN`. A personal access token works. | Reads `DATABRICKS_TOKEN` for every model call. |
| The app's service principal | Add `DOC_ENGINE_TOKEN_SOURCE` with the value `databricks_oauth` to `app.yaml`. The `DATABRICKS_TOKEN` entry is then not used. | Asks the Databricks SDK for the app's own OAuth token for every model call. The SDK refreshes it. |

## Authenticating to Lakebase

Attach Lakebase to the app as a resource. That provides the connection variables. The password has two routes.

| Route | How to set it up | What the app does |
|---|---|---|
| The app's OAuth token | `DOC_ENGINE_PG_PASSWORD_SOURCE` set to `databricks_oauth`. This is what `app.yaml` ships with. | Asks the Databricks SDK for the app's OAuth token each time it opens a database connection, and uses it as the password. |
| A password in an app secret | Remove `DOC_ENGINE_PG_PASSWORD_SOURCE` from `app.yaml` and map a secret to `PGPASSWORD`. | Reads `PGPASSWORD` each time it opens a database connection. |

Because the password is read at every connect, a short-lived token keeps working: when a connection is
refused or lost, the app drops it and opens a new one with a fresh password.

> **Not yet confirmed:** both `databricks_oauth` routes use the `databricks-sdk` package. It is in
> `requirements.txt`, but these routes are not exercised outside Databricks. The first deployment confirms
> them.

## What the application does on first start

On every start, in this order:

1. Applies the database schema. This creates any missing table, adds new columns, and installs the current
   versions of the functions that admit and complete calls. It needs permission to create tables and functions
   in the database. It keeps existing data.
2. Copies each model's limits from the settings into the `quota` table. The ledger's running state is kept.
3. If the database holds no flows and no files, creates the four sample flows and the ten sample files. This takes a few seconds.
   The sample flows are created already published, so the [public endpoint](../api/README.md) has something to
   call from the start.
4. Starts the worker inside the process, unless `worker.enabled` is `false`.
5. Listens on `DATABRICKS_APP_PORT`.

> **Note:** step 3 runs only on a database that has never held anything. If every flow is deleted, the samples
> do not come back at the next start. To get them back, run `python -m doc_engine samples`.

## Running several instances

Several instances can run at once. They share one quota, because the only authority on what may be sent is the
`quota` row per model in Postgres, and admission locks that row. See
[The quota ledger](../how-it-works/quota-ledger.md).

- Each instance runs its own worker, with up to `worker.concurrency` calls in flight and up to
  `postgres.pool_size` database connections.
- The live screens read the `events` table, so they show the same thing whichever instance answers.
- If an instance stops without warning, another instance returns its calls to the queue after
  `ledger.dead_worker_after_s` seconds. See [Failures and recovery](../how-it-works/failures-and-recovery.md).
- To run workers apart from the web server, set `worker.enabled: false` and start
  `python -m doc_engine worker` processes separately.

> **Not yet confirmed:** several worker processes and the recovery of a killed worker pass on the fake
> gateway. They have not been run on the real gateway or on Lakebase. They are checked after the first
> single-instance session succeeds.

## What to confirm in the first deployment

| # | Confirm | How |
|---|---|---|
| 1 | The platform installs `requirements.txt`. | The app starts; an import error at start means it did not. |
| 2 | `databricks-sdk` is available, if either `databricks_oauth` route is used. | The app connects to Lakebase and a model call succeeds. |
| 3 | The `gateway-token` secret reaches the app as `DATABRICKS_TOKEN`, if that route is used. | `python -m doc_engine preflight` gets an answer from each model. |
| 4 | Lakebase provides `PGHOST`, `PGDATABASE` and `PGUSER`, and its port and TLS mode match the settings file. | The app starts and `/api/health` answers. |
| 5 | The app's database role may create tables and functions. | The first start completes; `python -m doc_engine db check` prints `all tables present`. |
| 6 | `LISTEN/NOTIFY` is available on Lakebase. | Preflight prints `LISTEN/NOTIFY: available`. If not, the engine still works: it falls back to timed checks, and the log shows `notification listener lost`. |
| 7 | The app listens on the port the platform set. | The app's address opens the **Flows** screen. |
| 8 | `/api/health` reports at least one worker. | `{"ok": true, "workers": 1}` or more. |
| 9 | Each model accepts its "thinking off" form, adaptive thinking and image input. | Preflight, per model. See [Commands](commands.md#preflight). |

## The first session against the real gateway

Once the app is deployed and the checklist above is done, the gateway itself still has to be checked: this
codebase has not called it yet. [The first session on the real gateway](first-real-session.md) gives the
steps in order, from the cheap preflight to the runs that saturate a model on purpose.

The saturating steps slow every other application that uses the same endpoint. Agree a time with the
workspace's other users first, and leave at least a minute between saturating runs: the ledger starts each
process believing the quota is as it last recorded it, and it cannot see what the probe or other applications
used. See [Commands that can saturate the endpoint](commands.md#commands-that-can-saturate-the-endpoint).

## See also

- [The first session on the real gateway](first-real-session.md): the checks to run once the app is up.
- [Settings reference](settings.md): the settings the environment variables override, and how to re-size a model after the probe.
- [Commands](commands.md): `preflight`, `probe bucket` and `load` in full.
- [Troubleshooting](troubleshooting.md): when the app does not start or preflight fails.
- [Limits and what is not confirmed](limits.md): no sign-in yet, no retention period yet, synthetic files only.
