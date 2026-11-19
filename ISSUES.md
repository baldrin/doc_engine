# Known issues, by priority

Written 2026-11-18. These were found by reading the code while writing the documentation. Nothing here has
been seen on the real gateway: the code has only run against the fake gateway. Fixed issues are listed at
the end; the numbers of the others are unchanged.

- **Checked** means the code was read a second time for this list and the issue is confirmed there.
- Items without that mark were reported once, from reading the code, and not re-checked.
- Priority 1: could spoil a session or the demo, lose work, or charge twice.
- Priority 2: wrong or misleading behaviour that a user or operator will meet.
- Priority 3: small, cosmetic, or unlikely.

## Priority 1

None open. Issues 1 to 7 were fixed on 2026-11-18; see [Fixed](#fixed) at the end.

## Priority 2

### Scheduler and worker

| # | Issue | What happens | Where | Suggested fix |
|---|---|---|---|---|
| 10 | **A task whose worker dies never uses an attempt.** | A call that reliably kills its worker would be returned to the queue without end. | `de_reap` | Count recoveries and fail the task after a few. |
| 11 | **The queries-per-hour check counts the last hour's calls on every admission**, with the model's quota row locked. | Admission gets slower as hourly volume grows. The check is always on, since `qph` is set for every model. | `de_admit` | Keep a running counter per minute instead of counting rows. |
| 13 | **Jobs submitted together do not share a warm-up.** | The shared entry is written when a warm-up completes, so ten jobs submitted at once each send their own. Later jobs do share. | `planner.py`, `cache_warm` | Record a warm-up as "in progress" when it is planned and let other jobs wait on it. |
| 14 | **`duration` capacity mode has two faults.** | It uses the learned call length even when `ledger.learn_estimates` is false. The screens and `/api/quota` show the `fixed` cap, not the one admission uses. | `de_admit`; `quota_snapshot` in `api.py` | Honour the setting; report the cap admission used. |
| 15 | **The saturation confirmation looks at one request only.** | It ignores what is already queued. The public endpoint has no such check and no limit on requests. | `POST /api/jobs`; `public_api.py` | A decision, tied to authentication and job owners. |

### Setup and commands

| # | Issue | What happens | Where | Suggested fix |
|---|---|---|---|---|
| 21 | **`load` differs from the application.** | No 50-job limit. `--dry-run` still needs the database and rewrites the quota limits. A `--value` without `=` is dropped silently. | `cli.py` | Apply the same limit; make dry run read-only; refuse a malformed value. |
| 22 | **`export` with an unknown job id** writes six empty files and reports success. | | `cli.py` | Exit with "job not found". |
| 23 | **`samples`, `jobs`, `export` and `worker` do not check for missing tables.** | They fail with a raw Postgres error before `db init`. | `cli.py` | Use the check the other commands use. |
| 25 | **Uploads are read fully into memory** before the 200 MB check. | A very large upload uses that much memory first. | `api.py`, `public_api.py` | Stop reading at the limit. |
| 26 | **No sign-in anywhere.** | Anyone who can reach the application can run flows, read results and remove files. On Databricks Apps the platform decides who can reach it. | whole application | A decision for the Databricks sessions. |

### Screens

| # | Issue | What happens | Where | Suggested fix |
|---|---|---|---|---|
| 29 | **Save version does not validate.** | A flow with errors gets a version number. Save version and Publish always create a new version, even with no change. | `save_version` in `api.py` | Validate; skip when nothing changed. |
| 32 | **The estimate and the planner disagree in small ways.** | Different caching rules; the estimate leaves out the output contract and citation rule; a Filter call is always estimated at 1 page; warm-up calls are not counted. | `planner.py` | One shared calculation. |
| 35 | **"Track source pages" does nothing on schema steps**, but can be switched there. Its subtitle describes something that happens regardless. | | `prompts.py`, `Builder.tsx` | Hide it on schema steps; reword. |
| 36 | **Max output tokens of 0 or empty silently becomes 1,500.** | The "above zero" check only fires for negative values. | `step_data` in `flows.py` | Report it. |
| 39 | **Activity ignores the files chosen in the builder.** | The builder remembers them in the browser; Activity prefills only sample defaults or a file named like the source. | `Activity.tsx` | Read the same remembered choice. |
| 41 | **The Files screen does not refresh.** | A Remove button stays disabled after the run using the file has finished, until reload. | `Files.tsx` | Refresh on a timer or on focus. |
| 42 | **Deleting a flow shows nothing on failure.** | | `Flows.tsx` | Show the error, as create and duplicate do. |
| 44 | **Zip files get the office-file message** ("Save it as a PDF"). | | `documents.py` | Tell a plain zip from an office file. |
| 45 | **Re-uploading a file says "uploaded".** | Same content and name returns the existing file. If that file came through the API it stays hidden from the builder's pickers. | `Files.tsx`, `documents.py` | Say "already here"; show the file in pickers once uploaded from the screen. |
| 46 | **Model and Max output tokens appear on two tabs of a step.** | The same row is on the Prompt tab and the Model tab. It is one setting shown twice, which reads as two. Noted by the owner on 2026-11-18. | `Builder.tsx` (`modelRow`) | Remove the row from the Prompt tab; keep it on the Model tab. Update `docs/guide/steps.md`. |

## Priority 3

- **Flow card "blocks" count** is nodes minus one, so extra sources count as blocks.
- **Validation wording** ("Set one connection to Input") does not match the controls ("Make input", "Use as a reference").
- **Switching a connection between input and reference** resets its instruction, window and rule.
- **API panel examples always end in `.pdf`**, and the panel names `docs/api` as plain text, not a link.
- **Shortcut hints say "Ctrl D" only**; Cmd+D also works.
- **"View last outputs"** is only in the right-click menu, not in the step panel.
- **`not_equals` keeps items whose field is missing.** Documented, but may surprise.
- **Cancel on the Run screen has no confirmation.**
- **"Back to the run" on Results** uses browser history, so from a direct link it does not go to the run.
- **No truncation marker in table form**; the Run screen card always says "every finding linked to its pages".
- **The CSV button** shows whenever any item has structured data, even for a text output.
- **Scheduler lines in the Run feed** are made in the browser. They vanish on reload and in replay, and count waiting calls of all jobs.
- **The interactive lane tile on Run** counts interactive calls across all models, so a bulk run can show "Going first" for a model it does not use.
- **Queue positions on Activity** are worked out in the browser from the latest 80 jobs, across models, so they are approximate.
- **`saturating_jobs: 1` would block test runs**, since the Test run dialog has no confirmation step.
- **Sample flows come back** on the next start if every flow is deleted.
- **A model removed from the settings keeps its quota row** and still shows in the quota panels.
- **`cmd_worker` does not close the database** on exit.
- **No Python version is declared.** Developed on 3.12; the installed packages need 3.11 or newer.
- **`/api/estimate` and some comments still say "documents".** No effect on screen.
- **`load --dry-run`** passes neither keep ratios nor per-file page sizes to the estimate.

## Feature ideas, not started

Not issues. Kept here so they are not lost. None is to be started until the engine works end to end on the
real gateway and on Databricks Apps.

### A flow used as a step in another flow

Raised by the owner on 2026-11-18. A small flow such as "extract text from image" could be used inside other
flows, so its prompt, model, input and output settings are set up once.

- **Why it is worth doing:** one definition to maintain, and a fix reaches every flow that uses it.
- **Questions to settle first:**
  - Which version runs: the one published when the outer flow was saved, or whatever is published at run time.
  - How the inner flow's files and value inputs are filled from the outer flow.
  - Which of the inner flow's outputs becomes the block's output, and how page references pass through.
  - Refusing loops (a flow that reaches itself).
  - The cost estimate and the Run screen for a flow inside a flow.
- **The scheduler is not affected:** the inner flow's calls are tasks in the same queue under the same quota.
- **A smaller alternative:** saved steps (a step with its settings kept in the library and dropped into any
  flow). It covers "do not set this up again" with much less work, but it copies: a later fix does not reach
  flows already using it.

### A top priority level, set on the flow

Raised by the owner on 2026-11-18. Certain flows should go ahead of everything else that is waiting.

- **Today:** two levels per job, interactive and bulk. The queue sorts by a priority number, so a third level
  is a small change.
- **What to add:** a priority setting on the flow (Top, Interactive, Bulk) that its jobs inherit, and a rule
  that a caller of the endpoint cannot ask for more than the flow allows.
- **It jumps the line; it does not interrupt.** Calls already sent finish; the top job gets the next free
  capacity.
- **Questions to settle first:**
  - Starvation: a large top-priority load stops everything else. Keep the level for small jobs, or cap the
    share of the quota it may take.
  - Who may set it. This depends on sign-in and job owners (issues 15 and 26).
- **Not needed:** a way to lower a job's priority. Marking it bulk already does that.

### One day: a smart advisor agent

Raised by the owner on 2026-11-18 as a far-off idea. An agent that reads the stored record of flows, jobs and
calls and suggests improvements. A person accepts or ignores each suggestion.

- **Examples:** a large reference sent with many calls that could be summarized first; a step on an expensive
  model whose outputs a cheaper model could produce; the same step repeated across flows; a weekly report in
  plain language of what ran, what it cost and what failed.
- **It advises; it does not schedule.** Admission stays exact arithmetic in the database, so it is fast and
  every decision can be explained.
- **Do first, without an agent:** warnings from plain counts, such as "this step was cut off in 30% of calls,
  raise Max output tokens" and "this step uses a fifth of its Max output tokens".

## Fixed

Fixed on 2026-11-18 and checked on the fake gateway or in the browser, except where noted.

| # | Issue | What changed |
|---|---|---|
| 1 | Priority was not applied across models. | Admission tries the models' head tasks in priority order (interactive before bulk, then submission time), not in name order. Checked: with a bulk Haiku job and an interactive Sonnet job waiting, the Sonnet call is admitted first. |
| 2 | A late reply was recorded as well as its re-sent copy. | A reply counts only if its call still owns the task. A late reply keeps its call row, since it was paid for, and changes nothing else. Checked: 18 calls returned to the queue mid-run, 18 late replies, every step counted exactly once. |
| 3 | No wait between retries. | A timeout or server error waits before the next attempt: `worker.retry_delays_s`, default 2, 10, 30 seconds. Other calls are not held up. Checked with an unreachable gateway. |
| 4 | A call above a model's input limit could retry for ever. | Such a call is refused when its step is planned: before a job exists for a flow's first steps, or by failing the job for later steps. A call rejected `worker.max_rejections_per_call` times in a row (default 50) also fails. Checked both. How the real gateway answers such a call is still not known. |
| 5 | Activity ran the draft under a version label. | Activity and `load` run the published version, else the latest saved version, else the draft, and say which. A builder test run shows a version number only when the canvas is exactly that version. |
| 6 | Preflight failed on Databricks from the example settings file. | A `FILL-IN` Postgres setting counts as filled when its `PG*` variable is set. Checked without Databricks. |
| 7 | `PGPORT` and `PGSSLMODE` were ignored with the example settings file. | Both are empty in the example file, so the variables are used, then 5432 and `require`. |
| 16 | `probe bucket` crashed when no call succeeded. | It prints the first failure, writes the results file and exits 1. Checked with an unreachable gateway. |
| 17 | `databricks-sdk` and `pytest` were not in `requirements.txt`. | Both added. Not installed or exercised here; session 2 confirms the Databricks side. |
| 8 | A database failure while recording a good reply fails the job. | A reply that cannot be recorded because the database is away is kept and tried again for about a minute; after that the call returns to the queue. The job no longer fails. Not exercised: it needs a database interruption. |
| 18 | Several settings are not checked. | Start-up now refuses unknown values of `ledger.capacity_mode`, `gateway.streaming`, `gateway.token_source`, `worker.send_images_as` and `postgres.password_source`, and missing or non-numeric prices. |
| 19 | `/api/health` always says ok. | `/api/health` answers 503 with `ok: false` when no worker is alive, and uses `ledger.dead_worker_after_s`. |
| 20 | Preflight details. | The image check uses a "thinking off" form the model accepted, and is skipped with a message when none was. A refused image counts as a problem unless `send_images_as` is `pdf`. The summary line is always printed. Missing LISTEN/NOTIFY stays a note. Checked on the fake gateway for the passing case only. |
| 27 | A flow card shows "Published" beside the latest version. | The card reads "v3 · Published" only when v3 is the published version; otherwise "v3 · v2 is published". |
| 28 | "Draft" is lost on reload. | The server reports whether the draft differs from the latest version, ignoring block positions, so "Draft" survives a reload. The badge also names the published version when it is an older one. |
| 30 | Figures shown for a file nobody chose. | No estimate is requested or shown until every source has a file. |
| 31 | The "Cache ready" tag disagrees with the engine. | The tag comes from the server, by the planner's rule and the step's model. |
| 33 | Warnings are nearly invisible. | With warnings only, the bar reads "This flow can run." with the number of warnings, and opens the list. |
| 34 | Window 1 with overlap 1 raises an error. | Lowering the window lowers the overlap with it; the overlap field cannot exceed window minus one. |
| 37 | A single job from Activity is labelled "Test run". | A single job from Activity is labelled "Interactive" or "Bulk". |
| 38 | The admission timing line on Activity never shows. | The live stream carries the worker figures, so the line shows. |
| 40 | The page viewer can show the wrong page number. | The viewer prints the page it shows, and says so when the text cites a page past the end. Not viewed in a browser. |
| 43 | A refusal reads twice. | The refusal message reads once, followed by the model's explanation when it gives one. |
| 9 | The 429 hold is 1 second. | The pause now doubles while rejections continue: 1, 2, 4, 8, then 15 seconds (`ledger.hold_on_429_max_s`), and returns to 1 second after an accepted call. Checked on a fake gateway with a tiny bucket. The real gateway's behaviour after an overrun is still to be seen in session 1. |
| 12 | An invalid schema reply gets two retries, not one. | Kept at two retries by decision: a retry often succeeds. A reply cut off at max output tokens is no longer retried; the job fails at once with advice to raise the limit. Checked. |
| 24 | `config.fake.yaml` expected Postgres on port 54329; `scripts/dev_up.sh` sets no port. | The fake settings file leaves the port empty, so it uses `PGPORT`, then 5432, as the setup script does. Checked with `PGPORT` set. |
