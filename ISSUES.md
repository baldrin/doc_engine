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

## Review of 2026-11-20

An independent review by reading the code: seven reviewers (Claude Opus 5.5), one area each, and a second
reviewer per area who tried to refute every finding. Nobody ran code. The branch reviewed was `fix-open-issues`.
The missing sign-in (issues 15 and 26) was excluded on purpose.

- **Confirmed** means the second reviewer traced the scenario in the code and it holds.
- **Plausible** means the reasoning holds but depends on something that reading cannot settle, such as timing or the behaviour of the real gateway.
- The severity is the second reviewer's. Findings reported twice are listed once.
- 43 of the 62 were fixed on 2026-11-20 and are listed under [Fixed](#fixed) with the same R numbers. What follows is what remains open.
- The table counts all 62 as reported.

| Severity | Confirmed | Plausible |
|---|---:|---:|
| High | 1 | 0 |
| Medium | 18 | 5 |
| Low | 26 | 11 |

### High

None open.

### Medium

- **R21** (plausible, functional; fake gateway and tests) `doc_engine/worker.py:445`  
  A reply where thinking used up max_tokens and left no text fails the job at once with no retry. The fake makes this impossible: its thinking is at most ~900 tokens, and zero for between_tools or disabled.  
  *How it shows:* A user sets a step to thinking 'high' and keeps the default max_tokens of 1500 (flows.step_data). On a dense 4-page window, real adaptive thinking at high effort uses about 1,500 tokens. The reply ends with stop_reason max_tokens and holds only a thinking block. gateway._finish sets the outcome to 'empty', which falls through to the else branch here and calls fail_job; nothing warns that the limit is too low for thinking. Opus 'off' is sent as adaptive with low effort, so a 300-token classify step on Opus can fail the same way. The fake's make_reply (server.py:173-178) gives at most uniform(250,900) thinking tokens, and every sample flow uses thinking 'off', so the e2e never sends a thinking-on request.  
  *Suggested fix:* Treat an empty reply with stop_reason max_tokens like a truncated reply and fail it with advice to raise Max output tokens. Warn at validation when thinking is on and max_tokens is small. Let the fake's thinking length reach or exceed max_tokens, and add a thinking-on sample step to the e2e.
- **R22** (plausible, functional; fake gateway and tests) `doc_engine/planner.py:101`  
  There is no limit on PDF pages or on context tokens for a single request, only a 100-page limit for each reference and the per-minute ITPM. The fake accepts requests of any size, so a call the real API must refuse passes every check.  
  *How it shows:* A two-source flow attaches a 100-page reference PDF (allowed: pages > 100 is the only check) to a step that reads 4-page windows. Each call sends 104 PDF pages, about 180K tokens plus the window. The real Messages API caps PDF pages per request (100 on 200K-context models) and the total tokens at the context window, so the first call gets a 400. That outcome is 'permanent', and the job fails after its earlier steps have already been paid for. Two 60-page references go over 200K tokens in the same way. The fake's measure() (server.py:91-126) counts pages only to size the reply and never refuses anything, so the e2e and the planner tests pass.  
  *Suggested fix:* Before submitting, check that the PDF pages summed over references plus the window, and the estimated input tokens plus max_tokens, fit the model's per-request limits (add both to the per-model config). Have the fake return 400 above those limits.

### Low

- **R25** (plausible, functional; scheduler in the database) `doc_engine/worker.py:382`  
  A call that ends 'transient' (client timeout, connection reset in mid-stream, 5xx) is released with actual output 0 and counted input 0, although the gateway may have processed it and charged it. This contradicts de_reap and _return_to_queue, which keep the expected output because a lost call 'may still complete and be charged'.  
  *How it shows:* The gateway is slow. Twenty non-streaming calls, each with expected_output 4,000, reach gateway.request_timeout_s, and the gateway finishes them and charges about 80,000 output tokens. de_release adds 0 to out_level and drops their 80,000 from open_output, so after the 2 s retry delay the ledger readmits the 20 retries plus other work into a bucket the gateway has already emptied, and a run of 429s follows. A streaming call cut off after 6,000 generated tokens (APIConnectionError) is also charged 0 output.  
  *Suggested fix:* For transient outcomes, release with the reservation's counted_output and counted_input (as de_reap does), or with res.output_tokens when the stream reported usage.
- **R28** (confirmed, functional; scheduler in the database) `sql/001_schema.sql:124`  
  apply_schema runs the whole file as one implicit transaction on every `serve` start. ALTER TABLE ... ADD COLUMN IF NOT EXISTS takes an ACCESS EXCLUSIVE lock even when the column exists, so the script holds documents/jobs/job_steps exclusively while waiting for tasks/quota, the opposite order to de_admit (quota, then tasks, then jobs).  
  *How it shows:* Separate `python -m doc_engine worker` processes (a supported setup) keep admitting while `serve` restarts. apply_schema holds ACCESS EXCLUSIVE on jobs (line 66) and waits for tasks (line 124). A worker's de_admit already holds the quota rows and a tasks row lock and reaches `UPDATE jobs` (line 426), which waits on apply_schema. Postgres detects the deadlock. If it aborts apply_schema, the lifespan raises and `serve` fails to start. Either way, every worker query on jobs, job_steps or documents is blocked while the script runs. Two `serve` instances starting together can also fail with 'tuple concurrently updated' on CREATE OR REPLACE FUNCTION.  
  *Suggested fix:* Take a pg_advisory_xact_lock at the top of the script, and skip the ALTERs when information_schema shows the columns already exist (a DO block), or run the migration once at deploy time rather than on every start.
- **R30** (confirmed, functional; scheduler in the database) `sql/001_schema.sql:426`  
  SKIP LOCKED covers only the order where a cancel locks the task first. If de_admit locks a queued job's first task and then runs UPDATE jobs ... WHERE started_at IS NULL while cancel_job holds the job row and waits on that task, they still deadlock.  
  *How it shows:* A user presses Cancel on a queued job just as its first call is being admitted. de_admit holds all quota rows plus task T (FOR UPDATE SKIP LOCKED succeeded). cancel_job holds jobs(J) FOR UPDATE, and fail_job's UPDATE tasks waits on T. de_admit's UPDATE jobs sees started_at NULL in its snapshot and waits on J. Deadlock, with all quota rows held (every admission and release stalled) until Postgres aborts one side. The case listed in issue 35 as 'removed' is still there in this order.  
  *Suggested fix:* In cancel_job/fail_job, lock the job's ready tasks with SKIP LOCKED-compatible ordering before the job row is updated, or move de_admit's jobs update behind a NOWAIT/SKIP LOCKED check.
- **R31** (plausible, functional; scheduler in the database) `doc_engine/db.py:97`  
  Db.run retries `SELECT de_admit(...)` after an OperationalError, even though de_admit is not idempotent. If the connection drops after the server committed the admission, the task is left 'running' under a live worker that never sends it.  
  *How it shows:* The connection resets just after de_admit commits task T, before the reply reaches the worker. Db.run retries and admits task U. T's owner is this worker, which keeps heartbeating, so de_reap does not touch T until lease_s (900 s) runs out. For 15 minutes T's job is held up, T's expected output stays in open_output, and open_calls > 0 blocks the oversized-call exemption for that model. Afterwards T's recoveries is incremented as if a worker had died.  
  *Suggested fix:* Do not retry de_admit on connection loss (call it with retries=1), or have the dispatcher, after a lost connection, return any tasks it owns that are not in _inflight.
- **R32** (plausible, functional; internal api, settings and commands) `doc_engine/api.py:106`  
  The live event stream permanently loses events that commit out of id order. The hub only looks back 300 ids, and a new Run-screen stream replays strictly `event_id > after`, so an event whose id was taken early in a long transaction is never delivered to a live viewer.  
  *How it shows:* A Run screen is open for job J. The last call of J's step 1 finishes. The worker transaction emits task_done (id N) and step_done (id N+1) and then calls after_task_done -> plan_from, which builds and inserts a few thousand step-2 tasks. That takes several seconds. Meanwhile other jobs' de_admit and record transactions commit more than 300 events, so hub.last_id goes past N+301. When J's transaction commits, the hub query `event_id > last_id-300` never returns N or N+1. The Run screen keeps showing step 1 as running with one call in flight while step 2 is already working. The same loss happens without the 300-id gap if GET /api/jobs/{id} returns lastId from a later committed event of J (for example a task_admitted), the earlier id commits and the hub marks it seen before the EventSource subscribes, and the replay `event_id > after` then skips it.  
  *Suggested fix:* Replay with a lookback (`event_id > after - K`; the client and the `sent` set already dedupe). In the hub, track gaps or read by commit order (for example a time-based lookback, or holding last_id back while lower ids are still missing) instead of a fixed 300-id window.
- **R35** (confirmed, functional; internal api, settings and commands) `doc_engine/cli.py:91`  
  `python -m doc_engine samples` (run by scripts/dev_up.sh on every container recreation) re-inserts any deleted sample flow as published version 1 without the publish name-uniqueness check. Deleted samples come back, and a user's published flow with the same name becomes ambiguous on the public endpoint.  
  *How it shows:* The user deletes the sample 'Contract file review', builds their own flow, and publishes it under the name 'Contract file review'. publish allows this because no other published flow has that name. Later they run `bash scripts/dev_up.sh` (line 45 calls `samples`). install_samples finds no row for flow_sample_contract and inserts it with version 1 and published_version 1. From then on every caller of POST /api/v1/flows/contract-file-review/... gets 409 flow_name_ambiguous, and the deleted sample is back in the list. This contradicts the fixed item 'Sample flows no longer come back after being deleted'.  
  *Suggested fix:* Install sample flows only on an empty database (as the lifespan does), or skip any sample whose published name collides with an existing published flow and insert it unpublished. Do not run `samples` unconditionally from dev_up.sh.
- **R38** (confirmed, functional; internal api, settings and commands) `doc_engine/api.py:535`  
  Job events are truncated at 30,000 rows in GET /api/jobs/{id}, and the stream replay is capped at another 30,000. For a large job the Run screen never receives the tail of its history, including job_done.  
  *How it shows:* A 3,000-page file runs through two map steps with several hundred 429 rejections and streamed reduce progress, giving more than 60,000 events for the job. Opening its Run screen after it finished: get_job returns the first 30,000 events, and the stream with after=lastId replays only the next 30,000. step_done for the last steps and job_done never arrive, so the screen shows the job as still running, the end-of-run card and final cost never appear, and replay stops early. The same truncation applies when an EventSource reconnects with its original `after` once more than 30,000 events have accumulated.  
  *Suggested fix:* Page the replay in a loop until exhausted, or send a summarised state for finished jobs instead of the full event log.
- **R41** (plausible, functional; public endpoint and files) `doc_engine/public_api.py:259`  
  When a request is refused, the cleanup deletes every document this request inserted. But store_document de-duplicates by (sha256, name), so in the same moment a concurrent request (API or builder) can have been handed that same row as 'reused' and built a job on it. The cleanup then deletes a file that the other job uses.  
  *How it shows:* A caller sends the same new 150-page contract.pdf at the same time to flow A, which uses the file as a reference with max_reference_pages=100, and to flow B. Request A inserts doc_X and then fails in submit_job ('... the limit is 100 pages'). Before A's DELETE runs, request B's store_document finds doc_X by sha and name, returns it as reused (so B does not record it as its own), and B's job is created on doc_X. A's except branch then runs DELETE FROM documents WHERE document_id = doc_X. B's job reaches its first call, DocumentCache raises KeyError ('document doc_X not found'), and B's job fails although B's request was accepted with 202.  
  *Suggested fix:* Delete only if no job references the document (e.g. DELETE ... WHERE document_id = %s AND NOT EXISTS (SELECT 1 FROM jobs j, jsonb_each(j.documents) e WHERE e.value->>'document_id' = %s)), or do the insert and the job creation in one transaction.
- **R48** (confirmed, functional; flows, values and estimates) `doc_engine/flows.py:755`  
  For an edge that consumes pages ('pages' or 'both') from an earlier step, the estimate counts one page per upstream item. The planner sends the union of each item's pages, so the estimate is too low for step-fed windows and too high for a reduce after a filter.  
  *How it shows:* The sample 'Summarize window' (map, window 4, overlap 1) feeds a new step through Map window 1 with consume 'both'. The planner attaches 4 pages to each of its 50 calls (planner.py:307/313). The estimate counts min(window, n_in) = 1 page per call, about 3 x 1728 x 50 = 260k input tokens too few, so the cost shown is too low. In the other direction, a Reduce with consume 'pages' after a filter-fed step is charged doc_pages (all 150 pages), although the planner sends only the kept pages.  
  *Suggested fix:* Track pages per item through the estimate (for example per_node[...]['pages_per_item'] = pages_per_call for map, all of doc_pages for reduce, the upstream value for filter), and use n_items x pages_per_item, capped at doc_pages, for page-consuming edges.
- **R49** (confirmed, functional; flows, values and estimates) `doc_engine/flows.py:657`  
  prune_to keeps only the sources a step depends on, so testing one step of a multi-source flow runs it as a single-source flow, with a different system prompt and different citations than the real run.  
  *How it shows:* In 'Check an invoice against its order', the user tests 'Read the order'. prune_to keeps only src_po, so multi_source(pruned) is False. The worker uses CITE_RULE ([p. 1]) and no input name, where the full flow uses CITE_RULE_MULTI ([Purchase order p. 1]). The test output's citations differ from what the real run gives, and its cache prefix and hash differ too, so the test does not show how the step behaves in the flow. Learned profiles under the same node id mix both forms.  
  *Suggested fix:* Keep the original multi-source status in the pruned graph (for example a 'multi_source': true flag that flows.multi_source honours), or keep every source node in the pruned graph.
- **R52** (plausible, functional; screens) `frontend/src/Run.tsx:314`  
  The Run screen joins the history and the live stream at the highest event id it received (after=s.lastId) and never looks back. Event ids are taken before commit, so an event with a lower id that commits after the snapshot is lost for that page view.  
  *How it shows:* worker._record inserts task_done (id 500), then waits for the quota row lock in de_release while de_admit, which holds that lock, inserts task_admitted (id 501) and commits. The person opens the Run page at that moment, and GET /api/jobs/{id} returns events up to 501 without 500. Event 500 commits a few ms later, and the hub, which is polling because an Activity tab is open, marks it seen. The Run page's EventSource then connects with after=501: the DB catch-up skips 500 and the hub does not push it again. For the rest of the run, 'Calls done' is one short, the step shows '199 / 200' and then '199 done', and the done card reports one call fewer.  
  *Suggested fix:* Open the stream with after=lastId-300 (the hub's own look-back) and rely on the existing event_id de-duplication, or compute after from the lowest id not yet seen.
- **R53** (plausible, functional; screens) `frontend/src/Run.tsx:314`  
  The stream sends no 'id:' lines and the EventSource URL is fixed at the after value from page load. Every automatic reconnect therefore replays all events since the page opened. Because the catch-up is capped at 30000 rows, after a long session a reconnect returns only already-seen events, and the events between the drop and the reconnect are lost.  
  *How it shows:* A person watches a large bulk job from its start. Once more than 30000 events have been written since the page opened, the hub drops the subscriber (queue full) or the proxy resets the connection. The browser reconnects to /api/stream?after=<id at page load>. The server sends the 30000 oldest rows, all duplicates that the client skips with an O(n) .some() each (about 9e8 comparisons), and then only new live events. Everything written during the drop is never delivered. If job_done falls in that gap, the screen stays 'Running' with a Cancel button and no Results button.  
  *Suggested fix:* Emit 'id: <event_id>' in each frame and honour the Last-Event-ID header on the server, or recreate the EventSource with the current lastId on error. Keep a Set of seen ids instead of a .some() scan.
- **R54** (plausible, functional; screens) `frontend/src/Run.tsx:98`  
  apply() copies the whole rates array on every task_done, and replay rebuilds the state from all events on every 50 ms tick. Replaying a large job is therefore quadratic per tick and freezes the tab.  
  *How it shows:* A person opens a finished 3000-page map job (about 3000 task_done events) and presses Replay. Every 50 ms the useMemo at line 345 re-runs apply over all events up to the replay clock, and each task_done does [...s.rates, x]. That is about 4.5M element copies per tick near the end, so a tick takes longer than 50 ms. The main thread saturates, the replay stutters and the page stops responding to Pause or Exit replay.  
  *Suggested fix:* Keep rates in a mutable array (or only the last 60 s window) instead of copying, and replay incrementally from the previous clock instead of from scratch.
- **R55** (plausible, functional; screens) `frontend/src/Builder.tsx:652`  
  Estimate and validate requests are never cancelled or sequenced, so a slower earlier response can overwrite a newer one. The header then shows the cost of a file or graph that is no longer selected, and the problem list (which enables or disables Test run) can be stale.  
  *How it shows:* The person picks a 2000-page PDF in the 'Estimate for' select. The /api/estimate request is slow because it loads page_tokens and profiles. More than 350 ms later they switch to a 3-page sample, whose request returns first. Then the 2000-page response arrives and setEstimate shows '2,000 calls · about $40' beside the 3-page file. The same race on /api/validate can leave Test run enabled with an error that the newest graph has.  
  *Suggested fix:* Track a request sequence number or an AbortController in the effect and ignore responses that are not from the latest run of the effect.
- **R56** (plausible, functional; screens) `frontend/src/lib.ts:238`  
  api() treats any 2xx response whose body is not JSON as success and returns null. Requests that never reached the application can then appear to have succeeded.  
  *How it shows:* In front of the app (Databricks Apps / Entra ID, the planned set-up), an expired session makes the proxy answer PUT /api/flows/{id} with a redirect that fetch follows to a same-origin 200 HTML sign-in page. res.ok is true and res.json() throws, so body is null and api resolves. The builder's autosave sets 'saved', so the 'Saving…' and 'Not saved' hints disappear, although nothing was stored. The person leaves, and their edits are gone. Other callers crash on null instead (RunDialog's r.job_ids[0] shows 'Cannot read properties of null').  
  *Suggested fix:* When res.ok but the content type is not application/json (and the status is not 204), throw an ApiError saying the response was not from the application.
- **R57** (plausible, functional; fake gateway and tests) `doc_engine/planner.py:311`  
  A system prompt that is only marked for caching is counted as free input in the admission estimate. The fake gateway caches any prefix of 1,024 tokens or more for every model, so it hides the case where Haiku or Opus (minimum 4,096) never cache it.  
  *How it shows:* Take a Haiku step whose system text is about 3,500 estimated tokens. is_cacheable marks it, because its threshold is 0.75 x 4096 = 3072. The planner then leaves the system prompt out of input_estimate (`0.0 if cacheable`) and schedules a warm-up. The real API ignores a cache marker below 4,096 tokens, so each call counts the full ~3,500 system tokens against ITPM and reports no cache read. On a 150-page classify step against Haiku's 200K ITPM (config.example.yaml), the ledger thinks each call costs ~1.9K input when it really costs ~5.4K. It admits close to 3x the input the endpoint allows, which brings input-limit 429s and pauses, and the warm-up is resent for every job because cache_warm is never refreshed by reads. The e2e starts the fake without --cache-min-tokens, so it uses 1,024 for every model (server.py:257, 383), reports cache hits, and the estimate looks right.  
  *Suggested fix:* Count the system tokens in input_estimate unless they are above the model's real minimum, not 0.75 of it. Let the fake take a minimum per model, matching the config (haiku/opus 4096), and have e2e pass it.

### Refuted

- **R62** `frontend/src/ApiPanel.tsx:58` The API panel builds the submit URL from an ASCII-only slug of the flow name and ignores the submit_url (by flow id) that the contract returns. For names without ASCII letters, or names that clash after stripping punctuation, the command to copy does not work. *Why not:* Publish (api.py:313-321) refuses a flow whose public_api.flow_key(name) is empty ('Give the flow a name before publishing') and one whose flow_key equals another published flow's. flow_key (public_api.py:37-39) and flowSlug (ApiPanel.tsx:14-16) both keep only [0-9a-z] after lowercasing. So '請求書チェック' cannot be published, because its key is empty. 'Invoice-check' and 'Invoice check' cannot both be published, because their keys are equal. The panel shows a URL only for a published flow whose contract loaded. For such a flow the slug is never empty and is never ambiguous with another published flow, and published() resolves it by flow_key (public_api.py:87). Not using submit_url is a style choice, not a defect in the stated scenarios.

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
number 10 down in this table were also run through `python tests/e2e.py`, which makes 50 checks against the fake gateway.
Rows numbered R are findings of the [review of 2026-11-20](#review-of-2026-11-20), fixed that day. They were checked by the unit tests and
the end-to-end run where a row does not say otherwise; the screen changes among them were built but not viewed in a browser.

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
| R1 | A failure part-way through a streamed reply failed the whole job. | An error reported inside a stream is read by its type: overload and server errors are sent again, a rate limit counts as a rejection and starts the pause. A connection lost while a reply is being read is sent again. The fake gateway can now break replies part-way (`--stream-faults`), and the end-to-end run checks it. |
| R2 | Input quota was over-released when a long call ended. | Only the part of a call's estimate that has not yet drained is taken out of the input level, and the actual figure goes in less the same drain. Not exercised by a test. |
| R3 | Calls of a cancelled or failed job could be sent again after a restart. | A call returned to the queue whose job has ended is set to `cancelled`, by the worker and by the reaper. A warm-up is still returned, because other jobs may be waiting for it. |
| R4 | An interactive job could wait behind bulk work through a shared warm-up. | When a job attaches to a warm-up that is already sent and ranks behind it, the warm-up takes that job's place in the queue, so it does not requeue behind bulk work. |
| R5 | The wait for a database interruption never ran. | The database layer raises its own error (`DatabaseUnavailable`), and recording a reply waits on it for about a minute as intended. A call that could not be prepared because the database was away goes back to the queue; its job does not fail. Not exercised by a test. |
| R6 | A stream that ended early was accepted as a complete reply. | A streamed reply with no stop reason counts as a gateway error and is sent again. Checked by the end-to-end run. |
| R7 | A burst of calls on one file could each load their own copy of it. | One load per file at a time in each process. |
| R8 | A new Databricks client and token request for every call and connection. | One client is kept, so the SDK reuses its token. A failed token fetch is sent again like a gateway error, not treated as a failed call. Not exercised outside Databricks. |
| R9 | Form uploads on the public endpoint had no size limit. | A form upload is refused by its declared length before any of it is read (413), and one without a declared length is refused (411, `length_required`). |
| R10 | JSON bodies had no size limit. | The public submit reads at most 2 MB of JSON (413, `request_too_large`). Every other non-upload request is refused above 20 MB by its declared length. |
| R11 | Very large images were decoded at full size. | An image above 60 million pixels is refused from its header, before it is decoded. |
| R12 | Names in non-Latin scripts collapsed to one key. | Letters and digits of every script count when names are matched. Accented letters are now significant: `cafe` no longer matches `café`. The API panel builds its address the same way. |
| R13 | Values were checked twice, so a JSON value that is text was decoded twice. | Callers that have checked the values say so, and they are not checked again. |
| R14 | A filter rule `in {{list}}` never matched a JSON list. | A JSON list written into an `in` rule is read as a list. |
| R15 | A decimal comma in a number was dropped silently. | Commas are accepted only as thousands separators (`1,250`). `1,5` is refused with a message asking for a decimal point. |
| R16 | The schema editor could write old text into the wrong field. | The step panel and the two free-text boxes are rebuilt when the step or the field changes. |
| R17 | Backspace or Delete removed the selected step from a button in the side panel. | The keys remove a block only while the canvas has the focus. |
| R18 | Edits made just before leaving the builder could be lost; a failed save was never retried. | The pending save is sent when the builder closes or the tab is hidden, and a failed save is tried again every 5 seconds. |
| R19 | Page links opened the wrong file for an input name ending in a number. | The input's name is matched first, longest first. |
| R20 | The Run screen kept showing calls in flight after a cancel or failure. | In-flight counts are cleared when a run ends, and reduced when a lost call is returned. |
| R23 | The cancel check looked for a state that does not exist. | It counts calls left waiting, ready, running or lost. |
| R24 | The priority check passed on submission order alone. | Bulk jobs are submitted first and an interactive job after them; the check counts bulk calls that were already waiting and were sent after the interactive job's calls. |
| R26 | The pause calculation could overflow after about a thousand rejected rounds. | The exponent and the stored count are capped. |
| R27 | With a first wave set, calls gated on the first call of a wave could wait for ever if it failed. | Calls waiting on any call that fails, is cancelled or is lost are released. |
| R29 | The reaper locked quota rows in no fixed order. | It works through calls in model order, as admission does. |
| R33 | The event hub pushed its whole backlog to the first viewer after an idle period. | It starts from the newest events when a viewer connects after nobody was listening. |
| R34 | `worker` and `load` could delete quota rows of models missing from their own settings file. | Only the application removes a model's quota row. |
| R36 | Settings accepted in any case were compared exactly later. | `capacity_mode`, `token_source` and `password_source` are compared without regard to case. |
| R37 | The safety margin was not range-checked. | `ledger.safety_margin_fraction` must be 0 or more and below 1. |
| R39 | Page 0 or a negative page returned the wrong page. | It answers 404. |
| R40 | A malformed graph could be stored and break the flow list for everyone. | A graph is checked for its shape before it is stored. |
| R42 | Callers saw the draft's description. | The description is stored with each version; callers see the published one. Versions saved before this fall back to the flow's current description. |
| R43 | A very large number in a value input answered 500. | It is refused as not a number (400). |
| R44 | A text file that mentions a PDF header was taken for a broken PDF. | A PDF is recognised by its marker at the start, or anywhere in the first kilobyte when the file is named `.pdf`. |
| R45 | An output block feeding a step passed validation and the job never finished. | Validation refuses it, and refuses block types it does not know. |
| R46 | Two sources could differ only in punctuation and one could never be filled by a caller. | Source names are compared the way the public endpoint matches them. |
| R47 | A rule left on a connection that is no longer a filter asked for value inputs. | Only filter connections are read for `{{Name}}`. |
| R50 | A max output of Infinity answered 500. | It counts as 0 and is reported like any other missing value. |
| R51 | CSV cells could be read as formulas by a spreadsheet. | A cell that starts with `=`, `+`, `-` or `@` and is not a plain number gets a leading apostrophe. |
| R58 | A reply cut off at the model's context limit was stored as complete. | The stop reason `model_context_window_exceeded` counts as cut off. |
| R59 | The killed-worker check could pass without any recovery. | It waits until the extra worker is sending a call and checks that calls were returned to the queue. |
| R60 | The outputs check counted blocks, not content. | An output counts only when it holds text or data. |
| R61 | The early-results check accepted 200. | It requires 409 unless the job had already finished. |
