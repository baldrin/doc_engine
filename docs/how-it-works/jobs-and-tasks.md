[Documentation](../README.md) › [How it works](README.md) › Jobs and tasks

# Jobs and tasks

This page follows one job from the moment it is submitted to the moment its results are complete: how a flow becomes model calls, when those calls are created, and what is recorded about each. It is for readers who want to understand what the queue contains before reading how the queue is ordered.

**On this page**

- [From submission to results in brief](#from-submission-to-results-in-brief)
- [Submission](#submission)
- [Steps become tasks](#steps-become-tasks)
- [Why tasks are planned one step at a time](#why-tasks-are-planned-one-step-at-a-time)
- [Windows](#windows)
- [References](#references)
- [Warm-up tasks](#warm-up-tasks)
- [States](#states)
- [What each call records](#what-each-call-records)

## From submission to results in brief

1. A job is submitted: a flow, one file for each source, and any value inputs.
2. The job gets its own copy of the flow. The tasks of the first steps are created and put in the queue.
3. Workers send the tasks as the [quota ledger](quota-ledger.md) admits them.
4. When the last task of a step finishes, the step is done, and the tasks of the steps that depend on it are created.
5. When every step and output is done, the job is done. The **Results** screen shows each output.

A [task](../glossary.md#task) is one model call within a job. It is the thing the scheduler schedules. A job with 50 windows and one final summary is 51 tasks, plus one warm-up task where [prompt caching](prompt-caching.md) applies.

## Submission

Submitting a job does all of the following in one database transaction, so a job either exists completely or not at all.

1. **The flow is checked.** A flow with errors cannot run, and the message lists them.
2. **Value inputs are filled in.** Each `{{Name}}` in a prompt or a filter rule is replaced by its value. A missing or wrong value refuses the run before any job is created. See [Value inputs](../guide/value-inputs.md).
3. **References are checked for size.** A source that is attached whole to a step as a reference may have at most `worker.max_reference_pages` pages (configured default 100).
4. **The job is stored with its own copy of the flow.** Later edits to the flow do not change a job that is already running, and the copy already holds the values, so nothing later sees a placeholder.
5. **One row is created for each source, step and output.** Sources are done at once: a source offers one [unit](../glossary.md#unit) per page of its file.
6. **The first steps are planned**: their tasks are created.
7. **The workers are woken**, in this process and in every other one.

The job also records its priority, **Interactive** or **Bulk**, and the time it was submitted. Every task of the job carries both. They are what the [ordering rule](queue-and-priority.md#the-ordering-rule) uses.

A test of a single step is an ordinary job that runs only the part of the flow that step needs. See [Test runs](../guide/test-runs.md).

## Steps become tasks

A step works through its input by its [instruction](../guide/instructions.md). The instruction decides how many tasks the step has.

| Instruction | Tasks created | What each call receives |
|---|---|---|
| Map | One per [window](../glossary.md#window) of the items arriving | The pages or earlier outputs in that window |
| Reduce | One | All the items arriving |
| Filter | One per item whose earlier output matches the rule | The pages of that item |

An [item](../glossary.md#item) is anything a step can work on: a page of a file, or the output of one call of an earlier step. A step connected to a source receives pages. A step connected to another step receives that step's outputs, and a Filter step receives the pages its kept items cover.

When a step has nothing to do, for example because a filter kept no items, it is marked done at once with no tasks, and the steps after it are planned over an empty input. The job still finishes normally.

Each task records the model, the step's **Max output tokens**, the step's **Expected output tokens per call**, an estimate of its input tokens, and its number in the job's creation order. The expected output and the input estimate are what the [quota ledger](quota-ledger.md) counts when it decides whether the call fits.

A step with one or two calls is sent as a streamed call, so that the **Run** screen can show a long single call, such as a final summary, making progress. This is the behaviour of `gateway.streaming: auto`, the configured default.

## Why tasks are planned one step at a time

The tasks of a step are created only when the step it works through, and every step it references, are done. They are not all created at submission.

The reason is that the number of calls is not always known in advance. A Filter keeps the items whose earlier output matches a rule, and that output does not exist until the earlier step has run. A step that follows a filter may have 3 calls or 300. The same holds for a reference: the text of an earlier step's output is part of every call that references it, so those calls cannot be built before it exists.

Planning happens in the same database transaction that records the last call of the previous step, with the job's row locked. Two calls of one job that finish at the same moment therefore cannot plan the same step twice.

For the queue this means that a job's later steps join the queue while the job is running, not at the start. [Under heavy load](heavy-load.md) shows what that looks like with ten jobs.

## Windows

A Map step groups consecutive items into windows of a given size, with a given overlap between neighbours. Each window is one call.

- A window of 1 with no overlap gives one call per item.
- 150 pages at a window of 4 with an overlap of 1 gives 50 windows: each window starts 3 pages after the one before, and shares 1 page with it.
- The overlap is always smaller than the window. A larger value is reduced to one less than the window.
- The last window may be shorter than the others.

A window of pages is sent in the form of its file: a small PDF holding those pages, the image, or the text with each page marked by its number. See [File types](../guide/file-types.md).

## References

A step has exactly one input, which it works through, and any number of [references](../glossary.md#reference). A reference is handed to the step whole, on every call.

- A reference from another step is that step's complete output.
- A reference from a source is the complete file.

A step waits for its references: its tasks are created only when its input and every reference are done. In the request, references come after the step's static prompt and before the window or the earlier outputs. They are part of the input estimate of every call of the step, and they are not cached, so a large reference on a step with many calls is paid for on every call. See [Several files in one flow](../guide/several-files.md).

## Warm-up tasks

When a step's static prompt is long enough to be cached and the step has at least `worker.warmup_min_tasks` calls (configured default 3), the planner creates one extra task before the step's calls: the warm-up. It sends the static prompt with a one-word message so that the prompt is written to the model's cache.

The step's calls are created in state `waiting` and become `ready` when the warm-up finishes. If another job warmed the same prompt on the same model recently, no warm-up is created and the calls are `ready` at once. If another job's warm-up for the same prompt is already sent, or sits ahead of this job in the queue, no second warm-up is created and the calls wait for that one. If the warm-up fails, or the job that owns it is cancelled or fails, the calls are released anyway and run without the cache.

A warm-up is a task like any other: it waits in the same queue, is admitted by the same ledger, and has a row in `calls`. It is not counted in a step's progress. [Prompt caching](prompt-caching.md) has the details.

## States

### Job

| State | Meaning |
|---|---|
| `queued` | Submitted. No call has been admitted yet. |
| `running` | At least one call has been admitted. |
| `done` | Every step and output is done. |
| `failed` | A call failed in a way that cannot be retried, ran out of attempts, or was returned to the queue too often after lost workers. The job's error names the step and the cause. |
| `cancelled` | A user cancelled the job. |

### Step

| State | Meaning |
|---|---|
| `waiting` | None of its tasks has been admitted yet. Its tasks may not exist yet. |
| `running` | At least one of its tasks, or its warm-up, has been admitted. |
| `done` | All its tasks are done. Its output items are fixed. |
| `failed` | The job failed before this step was done. |
| `cancelled` | The job was cancelled before this step was done. |

Sources and outputs have rows too. A source is done from the start. An output is done as soon as the step it shows is done.

### Task

| State | Meaning |
|---|---|
| `waiting` | Created, but held back until the warm-up it waits for finishes. Not in the queue. |
| `ready` | In the queue. |
| `running` | Admitted by the ledger. A worker holds a lease on it and the call is in flight. |
| `lost` | Returned to the queue more than `ledger.max_recoveries_per_call` times after a lost worker or lease. Not sent again. A worker then marks it failed and fails its job. |
| `done` | The call succeeded and its output is stored. |
| `failed` | The call failed for good. |
| `cancelled` | The job failed or was cancelled before this task finished. |

A task goes from `running` back to `ready` when the gateway rejects the call with a 429, when a transient error or an invalid reply is retried, and when its worker is lost. [Failures and recovery](failures-and-recovery.md) covers each case.

Each task counts two things separately: **attempts** (transient errors and invalid replies, which are limited) and **rejections** (429s, which never use an attempt).

## What each call records

Every model call writes one row to the `calls` table, whether it succeeded or not.

| Recorded | Notes |
|---|---|
| Job, step, task, model | Which call this was |
| Kind | A step's call or a warm-up |
| Thinking level | As sent for this call |
| Sent and finished times | Also the time of the first token, for streamed calls |
| Request size in bytes | Checked against `gateway.max_request_mb` before sending |
| HTTP status and outcome | `ok`, `429`, `transient`, `permanent`, `refusal`, `empty` or `invalid` |
| Limit named by a 429 | Output, input or queries, read from the message text |
| Stop reason, and whether the reply was cut off | A reply that stops at max output tokens is marked truncated |
| Input tokens, output tokens, cache read, cache write | As the gateway reported them |
| Gateway request id and error body | For following up a failed call |

The task keeps the reply itself: the text, and for a step with an output schema the parsed and validated data.

Every state change also writes a row to the `events` table: job submitted, step planned, filter applied, call admitted, call done, call rejected, retry, failure, recovery, step done, job done. The **Run** screen and the replay of a finished run are built from these rows. `python -m doc_engine export --job ID --out DIR` writes a job's rows to CSV files; see [Commands](../operations/commands.md).

A successful call of a step also updates the step's profile: a running average of the output tokens, the counted input tokens and the duration of its calls. The ledger and the [estimate](estimates.md) both use it.

## See also

- [The queue and priority](queue-and-priority.md): the order in which ready tasks are sent.
- [The quota ledger](quota-ledger.md): how a task's expected output decides whether it is admitted.
- [Prompt caching](prompt-caching.md): the warm-up task in full.
- [Steps](../guide/steps.md): the step settings that become task settings.
- [Run screen](../guide/run-screen.md): where these states and events are shown.
