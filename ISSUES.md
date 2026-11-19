# Known issues, by priority

Written 2026-11-18 and updated the same night after a second round of fixes. These were found by reading the code while writing the documentation. Nothing here has
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

Two remain, both waiting on the choice of sign-in for the Databricks deployment (Databricks, Entra ID, OAuth2).

| # | Issue | What happens | Where | Suggested fix |
|---|---|---|---|---|
| 15 | **The saturation confirmation looks at one request only.** | It ignores what is already queued. The public endpoint has no such check and no limit on requests. | `POST /api/jobs`; `public_api.py` | A decision, tied to authentication and job owners. |
| 26 | **No sign-in anywhere.** | Anyone who can reach the application can run flows, read results and remove files. On Databricks Apps the platform decides who can reach it. | whole application | A decision for the Databricks sessions. |

## Priority 3

- **API panel examples always end in `.pdf`**, and the panel names `docs/api` as plain text, not a link.
- **`not_equals` keeps items whose field is missing.** Documented, but may surprise.
- **Scheduler lines in the Run feed** are made in the browser. They vanish on reload and in replay, and count waiting calls of all jobs.
- **The interactive lane tile on Run** counts interactive calls across all models, so a bulk run can show "Going first" for a model it does not use.
- **Queue positions on Activity** are worked out in the browser from the latest 80 jobs, across models, so they are approximate.
- **`/api/estimate` and some comments still say "documents".** No effect on screen.
- **Output contract and "Cite pages in the text" are on both the Prompt and Output tabs of a step.** Left in place: only the Model row was asked to go (issue 46). The same reasoning may apply.
- **A job that fails while its calls are being admitted can meet a database deadlock**, which Postgres resolves by cancelling one side; the recording is then tried again. Admission now skips locked calls, which removes the case that was found. Listed so a reviewer looks for others.

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

Fixed on 2026-11-18 and checked on the fake gateway or in the browser, except where noted. The fixes from
number 10 down in this table were also run through `python tests/e2e.py`, which makes 48 checks against the fake gateway.

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
| 10 | A task whose worker dies never uses an attempt. | Each return to the queue is counted. A call returned more than `ledger.max_recoveries_per_call` times (default 3) is set aside and its job fails with a message. Checked in the end-to-end run. |
| 11 | The queries-per-hour check counted an hour of calls on every admission. | Admissions are counted per model and minute; the check adds up at most 61 rows. |
| 13 | Jobs submitted together did not share a warm-up. | A job waits for another job's warm-up for the same model and prompt when that one is already sent or ahead of it in the queue. If the owner is cancelled, the waiting calls run without it. Checked: ten jobs at once send one warm-up per prompt, in six rounds running. |
| 14 | `duration` capacity mode had two faults. | The learned call length is used only when `ledger.learn_estimates` is true. The quota panels and `/api/quota` show the cap admission last used. |
| 21 | `load` differed from the application. | The 50-job limit applies. A dry run changes nothing in the database. A malformed `--value` or `--document` is refused. |
| 22 | `export` with an unknown job id wrote empty files. | It prints "job not found" and exits 1. |
| 23 | Some commands did not check for missing tables. | `samples`, `jobs`, `export` and `worker` say to run `db init` first. |
| 25 | Uploads were read fully into memory before the size check. | Reading stops at 200 MB. Not exercised with a file that large. |
| 29 | Save version did not validate, and always made a new version. | A flow with errors is not saved as a version. Save version and Publish make no new version when nothing changed. |
| 32 | The estimate and the planner disagreed in small ways. | The estimate uses the planner's caching rule and prompt text, sizes a filter-fed call by its upstream item, and shows warm-up calls apart. They are still two pieces of code. |
| 35 | "Track source pages" did nothing on schema steps. | Renamed "Cite pages in the text", with a subtitle that says what it does, and hidden on schema steps. |
| 36 | Max output tokens of 0 or empty silently became 1,500. | It is reported as a problem. |
| 39 | Activity ignored the files chosen in the builder. | Activity starts from the file remembered for each source. Not viewed in a browser. |
| 41 | The Files screen did not refresh. | It refreshes every few seconds and when the window regains focus. Not viewed in a browser. |
| 42 | Deleting a flow showed nothing on failure. | It shows the error, or a confirmation. Not viewed in a browser. |
| 44 | Zip files got the office-file message. | A zip archive has its own message. |
| 45 | Re-uploading a file said "uploaded". | It says "already here", and a file first sent through the endpoint then shows in the builder's pickers. |
| 46 | Model and Max output tokens appeared on two tabs of a step. | The row is on the Model tab only. Checked in the browser. |
| 47 | No way to stop a job from the Activity list. | Each queued or running job has a Cancel button, with a confirmation. Cancel on the Run screen asks too. Checked in the browser. |
| - | Smaller items from the priority 3 list. | Flow cards count every block. The "only references" message matches the controls. A connection keeps its settings when switched to a reference and back. The shortcut hint shows the Mac key on a Mac. "View last outputs" is on the Output tab. "Back to the run" goes to the run. A table output says when a reply was cut off; the end-of-run card no longer claims every finding is linked. The CSV button shows only for table outputs. One test run is never asked to confirm. Sample flows no longer come back after being deleted. A model removed from the settings leaves the quota panels. The worker command closes the database. Python older than 3.11 is refused. `load --dry-run` uses keep ratios and page sizes. |
| - | Found while fixing: the first form of the shared warm-up could leave a job waiting for ever. | A warm-up could finish in the moment between a planner choosing it and storing the calls that wait for it. A lock per model and prompt now covers both sides. Found by the end-to-end run. |
