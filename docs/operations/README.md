[Documentation](../README.md) › Setup and operations

# Setup and operations

This part is for the people who install Document Engine, configure it, deploy it to Databricks Apps with
Lakebase, and keep it running. It covers one machine, the workspace deployment, every setting and command,
what to watch, and what to do when something goes wrong.

**On this page**

- [What the application needs](#what-the-application-needs)
- [The one start command](#the-one-start-command)
- [Pages in this part](#pages-in-this-part)
- [What has been run so far](#what-has-been-run-so-far)

## What the application needs

Document Engine is one Python process. It holds the web server and the workers that make the model calls.
Everything it remembers is in Postgres: [flows](../glossary.md#flow), uploaded files, [jobs](../glossary.md#job),
results, the queue and the [quota ledger](../how-it-works/quota-ledger.md).

| Need | Detail |
|---|---|
| Python | 3.11 or newer. An older Python is refused at start: `Document Engine needs Python 3.11 or newer. This is Python <version>.` It is developed on Python 3.12. |
| Python packages | Those in `requirements.txt`: `anthropic`, `psycopg[binary]`, `pypdf`, `pyyaml`, `fastapi`, `uvicorn`, `jsonschema`, `pillow`, `python-multipart`. |
| Postgres | One database the application may create tables and functions in. Locally any Postgres; on Databricks, Lakebase. |
| A gateway endpoint | The workspace's Anthropic-style endpoint on the Databricks AI Gateway, set as `gateway.base_url` or `DOC_ENGINE_GATEWAY_URL`. |
| A gateway token | Read from an environment variable every time a call is made, never from a file. |

Nothing else is needed at run time. The built frontend is committed under `doc_engine/static/`, so there is no
Node.js step, and the screens load nothing from the internet: fonts are bundled.

The token and the Postgres password are never written in a file. Both are read from the environment each time
they are needed, so short-lived credentials keep working. [Settings](settings.md#environment-variables) lists
the variables.

## The one start command

```bash
python -m doc_engine serve
```

This starts the web server and, inside the same process, a worker. It prints the address it listens on, by
default `http://localhost:8000`. On each start it creates any missing tables, copies the model limits from the
settings into the database, and installs the sample flows and files if the database has never held anything.

Before the first start against a real gateway, run the cheap check:

```bash
python -m doc_engine preflight
```

## Pages in this part

| Page | Read it when |
|---|---|
| [Local setup](local-setup.md) | You are installing Document Engine on one machine for the first time. |
| [Deploying to Databricks Apps](databricks.md) | You are putting it on a workspace with Lakebase, or adding instances. |
| [Settings reference](settings.md) | You need the meaning or default of a setting, the start-up validation rules, or want to add or re-size a model. |
| [Commands](commands.md) | You need the options or the output of a `python -m doc_engine ...` command, or want to know which commands can saturate the endpoint. |
| [Monitoring](monitoring.md) | The application is running and you want to know whether it is healthy. |
| [Troubleshooting](troubleshooting.md) | Something failed. The page is organised by symptom and quotes the messages the code prints. |
| [Limits and what is not confirmed](limits.md) | You need a hard limit, want to know what is not built, or what has not yet been run on the real gateway. |
| [The fake gateway](fake-gateway.md) | You want to run the application or its tests with no gateway at all. |
| [The first session on the real gateway](first-real-session.md) | You hold the gateway token and are about to call the real gateway for the first time. |

## What has been run so far

The scheduler design was measured on the real Databricks AI Gateway in an earlier proof of concept, on
Sonnet 5.5 only. This codebase has so far run only against the [fake gateway](fake-gateway.md).

> **Not yet confirmed:** this codebase has not called the real gateway, has not used Lakebase and has not been
> deployed to Databricks Apps. The gateway is checked in
> [The first session on the real gateway](first-real-session.md), the rest in the first deployment described in
> [Deploying to Databricks Apps](databricks.md#what-to-confirm-in-the-first-deployment). The full table is in
> [Limits and what is not confirmed](limits.md#run-only-against-the-fake-gateway).

Until data handling has been decided, upload only synthetic files. See
[Limits](limits.md#use-only-synthetic-files-for-now).

## See also

- [Quick start](../start/quick-start.md): the shortest route from nothing to a first run.
- [Local setup](local-setup.md): the full installation on one machine.
- [How it works](../how-it-works/README.md): what the scheduler does with the quota you configure here.
- [API reference](../api/reference.md): the public endpoint that callers use once the application is running.
