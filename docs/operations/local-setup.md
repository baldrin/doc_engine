[Documentation](../README.md) › [Setup and operations](README.md) › Local setup

# Local setup

How to install Document Engine on one machine: with the setup script, or step by step. For whoever sets up a
development or trial copy. For a workspace deployment see [Deploying to Databricks Apps](databricks.md).

**On this page**

- [Before you start](#before-you-start)
- [Route 1: the setup script](#route-1-the-setup-script)
- [Route 2: by hand](#route-2-by-hand)
- [The token and the Postgres password](#the-token-and-the-postgres-password)
- [Check it before spending anything](#check-it-before-spending-anything)
- [Start it](#start-it)
- [Confirm it is working](#confirm-it-is-working)
- [Run it with no gateway at all](#run-it-with-no-gateway-at-all)
- [After every pull](#after-every-pull)

## Before you start

You need Python (see [what the application needs](README.md#what-the-application-needs)), a Postgres database,
the address of the workspace's Anthropic-style gateway endpoint, and a token for it. A personal access token
works.

## Route 1: the setup script

`scripts/dev_up.sh` prepares a Debian development container in one step. It uses `apt-get`, `sudo` and
`service`, so it is not for other systems. It is safe to run again, and should be run after every re-creation
of the container.

```bash
bash scripts/dev_up.sh
```

What it does, in order:

1. Installs the `postgresql` package if Postgres is missing.
2. Starts Postgres if it is not accepting connections on `127.0.0.1`.
3. Creates the role `docengine` and the database `docengine` if they are missing. The role gets a fixed local
   development password, `docengine`.
4. Creates the Python environment `.venv` if missing and installs `requirements.txt` into it.
5. Creates `config.yaml` from `config.example.yaml` if it does not exist, with `postgres.host` set to
   `127.0.0.1`, `postgres.dbname` and `postgres.user` set to `docengine`, and `postgres.sslmode` set to
   `prefer`. It leaves `gateway.base_url` for you to fill in.
6. Runs `python -m doc_engine db init` and `python -m doc_engine samples`.

The script cannot change your shell, so finish in the shell yourself:

```bash
. .venv/bin/activate
export PGPASSWORD=docengine
export DATABRICKS_TOKEN='<your-token>'
```

Then open `config.yaml` and set `gateway.base_url`, for example
`https://<workspace-host>/serving-endpoints/anthropic`. `config.yaml` is not committed.

Continue at [Check it before spending anything](#check-it-before-spending-anything).

## Route 2: by hand

1. Create a Postgres database and a role that may create tables and functions in it.

2. Create the Python environment and install the packages.

   ```bash
   python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
   ```

3. Create the settings file.

   ```bash
   cp config.example.yaml config.yaml
   ```

   Fill in the four values marked `FILL-IN`: `gateway.base_url`, `postgres.host`, `postgres.dbname` and
   `postgres.user`. The example sets `postgres.sslmode: require`; a local Postgres without TLS needs
   `prefer`. Every other setting has a working default. [Settings reference](settings.md) explains each one.

4. Export the token and the Postgres password, as described in
   [the next section](#the-token-and-the-postgres-password).

5. Create the tables. This also installs the database functions that admit and complete calls, and copies each
   model's limits from the settings into the database.

   ```bash
   python -m doc_engine db init
   ```

6. Install the sample material: four sample flows and ten fictional sample files.

   ```bash
   python -m doc_engine samples
   ```

   The command prints the id of every flow and file. The [`load`](commands.md#load) command takes those ids.

> **Note:** steps 5 and 6 are optional if you go straight to `serve`. The application creates missing tables
> on every start, and installs the samples when it finds no flows.

## The token and the Postgres password

No secret goes in any file. The settings file holds only the *names* of two environment variables, and the
application reads their values each time it needs them.

| Secret | Variable read by default | Setting that names the variable |
|---|---|---|
| Gateway token | `DATABRICKS_TOKEN` | `gateway.token_env_var` |
| Postgres password | `PGPASSWORD` | `postgres.password_env_var` |

```bash
export DATABRICKS_TOKEN='<your-token>'
export PGPASSWORD='<your-postgres-password>'
```

The token is read for every model call and the password for every new database connection, so replacing the
value takes effect in a new process without editing anything. Do not write either into `config.yaml`.

If the token variable is not set, the application still starts. The problem shows when a call is made: see
[Troubleshooting](troubleshooting.md#the-token-variable-is-not-set).

## Check it before spending anything

```bash
python -m doc_engine preflight
```

Preflight is cheap: three small calls per model when all is well. It checks the settings file, the database,
and each configured model on the gateway. Fix whatever it reports before going further.
[Commands](commands.md#preflight) describes each line it prints, and
[Troubleshooting](troubleshooting.md#preflight-reports-a-problem) what to do about each failure.

## Start it

```bash
python -m doc_engine serve
```

It prints `Document Engine on http://localhost:8000`. The port is `server.port`; the environment variables
`DATABRICKS_APP_PORT` and `PORT` override it.

## Confirm it is working

1. Check the tables.

   ```bash
   python -m doc_engine db check
   ```

   It prints `all tables present`.

2. Ask the running application for its health.

   ```bash
   curl http://localhost:8000/api/health
   ```

   A healthy reply is `{"ok": true, "workers": 1}`. `workers` is the number of worker processes seen in the
   last 30 seconds; `0` means nothing will make calls.

3. Open `http://localhost:8000`. The **Flows** screen lists the four samples: **Medical record summary**,
   **Contract file review**, **Compare two medication lists** and **Check an invoice against its order**.

4. Open **Medical record summary**, choose **Test run**, and pick the 24-page sample file. The
   [Run screen](../guide/run-screen.md) shows the job live. Expect it to finish with no rejections.

> **Not yet confirmed:** step 4 has only been done against the fake gateway. The first run on the real gateway
> is part of the [first session on the real gateway](first-real-session.md).

## Run it with no gateway at all

To see the application work without a workspace, a token or any cost, run it against the stand-in in
`fake_gateway/` with the settings file `config.fake.yaml`. [The fake gateway](fake-gateway.md) has the
commands. Nothing seen there is evidence about the real gateway.

## After every pull

Run `python -m doc_engine db init` again after every pull. It is safe to repeat: it adds new tables and
columns, replaces the database functions with the current ones, and keeps all data. Starting the application
with `serve` does the same.

## See also

- [Settings reference](settings.md): every value in `config.yaml`.
- [Commands](commands.md): the options and output of each command used above.
- [Troubleshooting](troubleshooting.md): when a step on this page fails.
- [The fake gateway](fake-gateway.md): the same setup with no workspace.
- [Quick start](../start/quick-start.md): the first flow once the application is running.
