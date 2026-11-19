[Documentation](../README.md) › [Setup and operations](README.md) › The fake gateway

# The fake gateway

The stand-in for the Databricks AI Gateway that ships in `fake_gateway/`: what it imitates, how to start it,
the settings file that goes with it, its speed option, and how to run the tests. For anyone who wants to run
Document Engine with no workspace, no token and no cost.

> **Note:** nothing the fake gateway shows is evidence about the real gateway. It shows that the code runs.
> A rejection count, a throughput figure, a run time or a cost seen here says nothing about what the real
> gateway will do.

**On this page**

- [What it is for](#what-it-is-for)
- [What it imitates](#what-it-imitates)
- [Starting it](#starting-it)
- [config.fake.yaml](#configfakeyaml)
- [Options](#options)
- [The speed option and capacity mode](#the-speed-option-and-capacity-mode)
- [What to expect from preflight](#what-to-expect-from-preflight)
- [Running the tests](#running-the-tests)
- [What it cannot tell you](#what-it-cannot-tell-you)

## What it is for

The fake gateway is a small web server that answers the same request the application sends to the real
gateway. It lets you start the application, build flows, run jobs, watch the Run screen, and try the
`load` and `probe bucket` commands without calling a model. Its replies are filler text, not answers.

It is the only gateway this codebase has run against so far.

## What it imitates

It imitates what was measured on the real gateway in the proof of concept on Sonnet 5.5, not the gateway's
documentation:

- Nothing is reserved when a call starts. The actual output is charged when the call completes.
- Output is a token bucket of about 40,000 tokens that refills at OTPM/60 per second. Calls are accepted
  blindly while the bucket is not empty, then rejected until the debt clears.
- A rejection comes back in about 0.3 seconds as HTTP 429 with only an error code and a message. The message
  names the limit; there is no retry timing and no header.
- Cache reads do not count against the input limit. Cache writes do.
- A cache entry can be read only after the call that wrote it has started answering.
- Models think by default. Models whose name contains `sonnet` or `opus` refuse `{"type": "disabled"}`;
  only a `sonnet` model accepts `between_tools`.
- A request body over about 20 MB gets a misleading "malformed JSON" 400.

What it makes up:

- The reply text. A text step gets filler sentences with page references in the expected form. A step with a
  schema output gets random values that fit the schema. The same request always gets the same reply.
- The timing. A call takes about 1.2 to 1.6 seconds to start answering, then writes at 150 tokens per second.
- The token counts. A PDF page and an image each count as 1,700 input tokens; text is counted by length.

It keeps one output bucket and one input bucket per model name, creates them full on first use, and checks no
token: any value is accepted.

To see how the application handles a refusal, put the word `FAKE_REFUSE` in a step's system prompt. The fake
gateway then answers that step with a refusal, and the job fails as described in
[Troubleshooting](troubleshooting.md#a-job-failed).

## Starting it

1. Have a Postgres database reachable as `config.fake.yaml` expects: host `127.0.0.1`, database `docengine`,
   user `docengine`. Export its password.

   ```bash
   export PGPASSWORD='<your-postgres-password>'
   ```

   The Postgres that `scripts/dev_up.sh` sets up matches this. The port is not set in the file: it is taken
   from `PGPORT`, and is `5432` when that is not set. If your Postgres listens elsewhere, export `PGPORT`.

2. In one terminal, start the fake gateway.

   ```bash
   python -m fake_gateway --port 8765 --speed 10
   ```

3. In another terminal, start the application with the fake settings. `FAKE_TOKEN` must be set to something;
   its value does not matter.

   ```bash
   DOC_ENGINE_CONFIG=config.fake.yaml FAKE_TOKEN=x python -m doc_engine serve
   ```

   It prints `Document Engine on http://localhost:8100`. On first start it creates the tables and the samples.

4. Open `http://localhost:8100`.

Other commands work the same way:

```bash
DOC_ENGINE_CONFIG=config.fake.yaml FAKE_TOKEN=x python -m doc_engine preflight
DOC_ENGINE_CONFIG=config.fake.yaml FAKE_TOKEN=x python -m doc_engine load --flow flow_sample_medical --document doc_sample_medical_24 --jobs 2
```

`load` and `probe bucket` still ask for `--confirm-saturation` where they would on the real gateway.

While it runs, the fake gateway answers two addresses of its own:

| Address | What it does |
|---|---|
| `GET http://127.0.0.1:8765/stats` | Counts since start or the last reset: requests, accepted calls, rejections by limit, 400 replies, output tokens, cache reads and writes, calls in flight and their peak, and the tokens left in each model's output bucket. |
| `POST http://127.0.0.1:8765/reset` | Empties the counts, the buckets and the cache. |

## config.fake.yaml

`config.fake.yaml` is `config.example.yaml` with these differences and nothing else:

| Setting | `config.example.yaml` | `config.fake.yaml` |
|---|---|---|
| `gateway.base_url` | `FILL-IN` | `http://127.0.0.1:8765` |
| `gateway.token_env_var` | `DATABRICKS_TOKEN` | `FAKE_TOKEN` |
| `ledger.capacity_mode` | `fixed` | `duration` |
| `postgres.host` | `FILL-IN` | `127.0.0.1` |
| `postgres.dbname`, `postgres.user` | `FILL-IN` | `docengine` |
| `postgres.sslmode` | `require` | `prefer` |
| `server.port` | `8000` | `8100` |

Port 8100 is also where the frontend's development server (`npm run dev` in `frontend/`) sends its API
requests.

Because the token variable has a different name, a shell set up for the fake gateway cannot reach the real
one by accident, and the other way round.

## Options

```text
python -m fake_gateway [options]
```

| Option | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Address to listen on. |
| `--port` | `8765` | Port to listen on. Must match `gateway.base_url`. |
| `--otpm` | `100000` | Output tokens per minute: the refill rate of each model's output bucket. |
| `--itpm` | `1000000` | Input tokens per minute, and the size of each model's input bucket. |
| `--bucket` | `40000` | Size of each model's output bucket. |
| `--speed` | `1.0` | Divide every delay by this. See below. |
| `--ttft-s` | `1.2` | Seconds before a call starts answering. |
| `--output-tps` | `150` | Output tokens written per second. |
| `--tokens-per-page` | `1700` | Input tokens counted for a PDF page or an image. |
| `--cache-min-tokens` | `1024` | A marked prompt shorter than this is not cached. |
| `--cache-ttl-s` | `300` | How long a cache entry lives after its last use. |
| `--max-body-mb` | `20` | Requests larger than this get the "malformed JSON" 400. |

## The speed option and capacity mode

`--speed 10` makes every call ten times shorter, so a run that would take minutes takes seconds. The bucket
does not speed up: it still refills in real time, at `--otpm` per real minute.

That changes which capacity mode fits. In `fixed` mode the output cap is `bucket_capacity_output` less the
safety margin, a figure tuned for calls of about 9 seconds. With calls ten times shorter, that cap admits too
much. In `duration` mode the cap is the bucket plus the refill during half
a call, using the call length the ledger has learned, so it adapts to the short calls. This is why
`config.fake.yaml` sets `ledger.capacity_mode: duration` while `config.example.yaml` keeps `fixed`.

Any rejections seen at `--speed 10` in `fixed` mode come from this arrangement. They are not a forecast for
the real gateway. See [The quota ledger](../how-it-works/quota-ledger.md) for the two modes.

## What to expect from preflight

Against the fake gateway, with `config.fake.yaml`, each model accepts its configured `thinking_off` form and
adaptive thinking. Two lines look different from a real run because the replies are filler text:

- The reply quoted on the `thinking off` line is filler, not the word asked for.
- The image line reads `image input: OK (reply '...', expected 742, ...)`. The fake gateway accepts the image
  but cannot read it. This does not count as a problem.

## Running the tests

```bash
python -m pytest -q
```

The tests in `tests/` are unit tests. They need neither a database nor a gateway, real or fake; they read
`config.example.yaml` for the model settings. `pytest` is installed with `requirements.txt`.

They cover, among other things, how pages are grouped into windows, flow validation, filter rules, schema
handling, estimates, the form of each request, how a rejection's message is read, value inputs, file kinds and
the public endpoint's naming rules.

Everything that involves the database, the workers and the scheduler together is exercised by the end-to-end
check:

```bash
python tests/e2e.py
```

It is not collected by `pytest`. It needs only a reachable Postgres. It starts its own fake gateway and its own
copy of the application on free ports, keeps its tables in a separate schema (`de_e2e`) of the configured
database, and takes a few minutes. It prints a list of checks and ends with `N of N checks passed`. Its
options are `--rounds`, `--speed`, `--quota-scale` and `--keep`; see
[Commands](commands.md#the-end-to-end-check). Like everything on this page, it says nothing about the real
gateway.

## What it cannot tell you

- Whether a real model follows the prompts, finds what a flow asks for, or gives correct page references.
- Whether the real gateway accepts each request form, including image input and each `thinking_off` form.
- The real bucket size of any model, the real call durations, or the real cost of a run.
- How the real gateway behaves when other applications share the endpoint.
- Anything about Lakebase or Databricks Apps.

The complete list of what has only been run here is in
[Limits and what is not confirmed](limits.md#run-only-against-the-fake-gateway).

## See also

- [Local setup](local-setup.md): the same installation against the real gateway.
- [Limits and what is not confirmed](limits.md): what the fake gateway leaves unproven.
- [Commands](commands.md): `preflight`, `load` and `probe bucket`, all usable here at no cost.
- [The quota ledger](../how-it-works/quota-ledger.md): the behaviour the fake gateway is built to exercise.
- [Under heavy load](../how-it-works/heavy-load.md): what to try with `load` against the fake gateway.
