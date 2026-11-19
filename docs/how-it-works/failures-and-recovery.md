[Documentation](../README.md) › [How it works](README.md) › Failures and recovery

# Failures and recovery

This page lists every way a model call or a worker can fail, and for each one says what Document Engine does and what the user sees. It is for engineers who operate the engine and for anyone who wants to know what a failed or interrupted run means.

**On this page**

- [The rules in one table](#the-rules-in-one-table)
- [Rejections (HTTP 429)](#rejections-http-429)
- [Timeouts and server errors](#timeouts-and-server-errors)
- [Other request errors](#other-request-errors)
- [Refusals](#refusals)
- [Empty replies](#empty-replies)
- [Invalid schema output](#invalid-schema-output)
- [Truncation](#truncation)
- [A request that is too large](#a-request-that-is-too-large)
- [A failed warm-up](#a-failed-warm-up)
- [A worker that dies](#a-worker-that-dies)
- [Database trouble](#database-trouble)
- [A failed job](#a-failed-job)
- [A cancelled job](#a-cancelled-job)
- [Restart of the whole app](#restart-of-the-whole-app)

## The rules in one table

The gateway client never retries by itself. Every outcome comes back to the worker, which records it in the `calls` table and then applies one of these rules.

| What happened | Retried | Uses an attempt | End result if it keeps happening |
|---|---|---|---|
| Rejection, HTTP 429 | Yes | No | The task waits; the model is paused briefly each time. The job fails after `worker.max_rejections_per_call` rejections of the same call |
| Timeout, connection error, server error | Yes, after a wait | Yes | The job fails after `worker.max_transient_attempts` attempts |
| Reply does not match the output schema | Yes | Yes | The job fails after `worker.max_transient_attempts` attempts |
| Other request error | No | | The job fails |
| Refusal | No | | The job fails |
| Empty reply | No | | The job fails |
| Reply cut off at max output tokens | No | | Accepted and marked as cut off |
| Request too large | No | | The job fails before anything is sent |
| Call above the model's input limit per minute | No | | The run is refused, or the job fails, before anything is sent |
| Warm-up fails | As above, by kind | | The step runs without the cache. The job does not fail. |
| Worker dies or loses its lease | Yes | No | Another worker makes the call. The job fails once the same call has been returned to the queue more than `ledger.max_recoveries_per_call` times |

The configured default of `worker.max_transient_attempts` is 3. That is three calls in total for one task: the first and two retries. Timeouts, server errors and invalid replies share the one counter.

On the **Run** screen each of these appears as a line in the event feed, and the run's state changes when a job fails or is cancelled. The **Activity** screen lists every job with its state.

## Rejections (HTTP 429)

**What it is.** The gateway refused the call because a rate limit was exceeded.

**What the engine does.** It records the call with the limit named in the message (output, input or queries). It returns the task to the queue at its old place and raises the task's rejection count. It does not use an attempt. It adds nothing to the ledger's output level. It pauses the model, for every worker in every process. The first pause lasts `ledger.hold_on_429_s` (configured default 1 second). If a call sent after that pause is rejected too, the next pause is twice as long, and so on up to `ledger.hold_on_429_max_s` (configured default 15 seconds): 1, 2, 4, 8, 15. The first call accepted after a pause puts it back to the start. So a brief rejection costs one short pause, and a gateway that keeps rejecting is left alone for longer each time.

A call that is rejected `worker.max_rejections_per_call` times in a row (configured default 50) fails, and its job fails with it. Without this limit, a call the gateway will never accept would be sent again every second for ever, with everything behind it on that model waiting. Set the limit to 0 to turn it off.

**What the user sees.** A line in the event feed that the gateway rejected a call, with the limit and the length of the pause, and a higher rejection count for the run. The job keeps running. If the limit is reached, the run fails with the step's name, the number of rejections and the size of the call.

### A call above the model's input limit

A call that would send more input tokens than its model accepts in a minute (`models.<name>.itpm`) could never be accepted. The engine works out each call's input when it plans a step. If the first steps of a flow hold such a call, the run is refused before a job exists. If a later step does, which is known only once the earlier steps have finished, the job fails at that point. The message names the step, the size of the call and the model's limit. The usual causes are a Reduce over many items and a long file attached as a reference.

> **Not yet confirmed:** how the real gateway answers a call above the input limit. The check works from the engine's own estimate of the call's input.

[Under heavy load](heavy-load.md#what-a-429-does) explains the pause and what is not yet confirmed about it.

## Timeouts and server errors

**What it is.** The call got no usable answer for a reason that may pass: a timeout after `gateway.request_timeout_s` (configured default 600 seconds), a lost connection, or an HTTP status of 408, 409, 500, 502, 503, 504 or 529.

**What the engine does.** It records the call, adds nothing to the ledger's output level, and returns the task to the queue at its old place with one attempt used. The task is not sent again at once: it waits 2 seconds before the second attempt and 10 seconds before the third (`worker.retry_delays_s`, configured default `[2, 10, 30]`; the last value is used for any further attempt). Other tasks are not held up while it waits. When the task has used `worker.max_transient_attempts` attempts, it fails, and the job fails with it.

**What the user sees.** A line in the event feed that the step is retrying, with the error. If the attempts run out, the run fails with the step's name and "Gateway error", the HTTP status and the message.

> **Note:** with the configured defaults a call gives up about 12 seconds after its first failure, plus the length of the calls themselves. A gateway outage that lasts longer fails the jobs that are running. Lengthen `worker.retry_delays_s` or raise `worker.max_transient_attempts` to ride out longer outages, and submit failed jobs again when the gateway is back.

## Other request errors

**What it is.** Any other HTTP error, for example 400 for a request the gateway does not accept, or 401 and 403 for a token that is missing, expired or not allowed. Also any unexpected error while making the call.

**What the engine does.** It does not retry, because the same request would fail the same way. The task fails and the job fails.

**What the user sees.** The run fails with the step's name and "Request failed", the HTTP status and the gateway's message.

An error inside the worker while it prepares a request or records a result is treated the same way and is reported as a worker error.

## Refusals

**What it is.** The model answered, but declined the request.

**What the engine does.** It does not retry. The task fails and the job fails. The output tokens the gateway reported are added to the ledger and to the job's cost.

**What the user sees.** The run fails with the step's name and "The model declined this request".

A refusal must not pass as a success: its text is not the answer the step asked for. Measured in the proof of concept on Sonnet 5.5, a static prompt made of meaningless text caused every call to be refused, so the prompt of a step has to read as a real task.

## Empty replies

**What it is.** The call succeeded but the reply holds no text. The usual cause is thinking that used the whole of the step's max output tokens before any answer was written.

**What the engine does.** It does not retry. The task fails and the job fails. The output tokens are added to the ledger and to the cost: they were produced.

**What the user sees.** The run fails with the step's name and "Empty reply", with the reason the model stopped.

Raise the step's max output tokens or lower its thinking level, then run again.

## Invalid schema output

**What it is.** The step has an output schema, and the reply is not a JSON object that matches it.

**What the engine does.** The reply is read tolerantly first: a code fence or a stray sentence around the JSON object is ignored. If what remains is not valid JSON, or does not match the schema, the call is recorded as invalid and the task is retried at once, using an attempt. A retry often succeeds, because the model does not give the same reply twice. One case is not retried: a reply that was cut off at the step's max output tokens. The same call would be cut off again, so the task fails at once, and the error says to raise **Max output tokens** or use a smaller window. After `worker.max_transient_attempts` attempts the task fails and the job fails. The output tokens of each invalid reply are added to the ledger and to the cost.

**What the user sees.** A line in the event feed that the step is retrying because the reply did not match the output schema. If the attempts run out, the run fails with the step's name, "Invalid reply" and what did not match.

## Truncation

**What it is.** The reply reached the step's max output tokens and was cut off.

**What the engine does.** A cut-off reply that holds text is accepted. The call and the task are marked as truncated, the step continues, and later steps receive the cut-off text. The step's profile counts how often this happens.

**What the user sees.** The event feed marks the call as cut off at max output. On the **Results** screen the output carries a notice that it was cut off, with the advice to raise the step's max output and run again.

Two cases end differently. A cut-off reply for a step with an output schema is usually not valid JSON, so it follows the path of [invalid schema output](#invalid-schema-output). A reply cut off before any text was written is an [empty reply](#empty-replies).

## A request that is too large

**What it is.** The request body, with its pages encoded, is larger than `gateway.max_request_mb` (configured default 16 MB).

**What the engine does.** It checks the size before sending. A request over the limit is not sent. The task fails and the job fails.

**What the user sees.** The run fails with the step's name, the size of the request, the limit, and the advice to use a smaller window.

The check exists because the gateway's own answer is misleading. Measured in the proof of concept on Sonnet 5.5: a request of 18.3 MB was accepted, and one of 23.5 MB was rejected with an HTTP 400 that complained of malformed JSON.

A related check happens earlier, at submission: a source attached whole to a step as a reference may have at most `worker.max_reference_pages` pages (configured default 100). A larger one refuses the run before any job is created.

## A failed warm-up

**What it is.** The [warm-up call](prompt-caching.md) of a step failed.

**What the engine does.** A rejected warm-up returns to the queue, and a warm-up that hits a timeout or server error is retried, as for any call. If it fails for good, the engine releases the waiting calls anyway. They run without the cache, at the full input price for the static prompt. The job does not fail.

Calls of other jobs may be waiting for the same warm-up, because jobs [share one warm-up](prompt-caching.md#sharing-a-warm-up-across-jobs) per model and static prompt. They are released in the same way. If the job that owns the warm-up is cancelled or fails before the warm-up has completed, the waiting calls of the other jobs run without it.

**What the user sees.** A line in the event feed that the warm-up failed and the step is continuing without the cache.

## A worker that dies

**What it is.** A worker process was killed, crashed, lost its machine, or lost its connection to the database for too long, while it had calls in flight.

**How it is detected.** Three things are in place.

| Mechanism | What it is | Setting |
|---|---|---|
| Lease | Every admitted task records which worker has it and until when | `ledger.lease_s`, configured default 900 seconds. The engine refuses to start unless it is longer than `gateway.request_timeout_s`. |
| Heartbeat | Every worker process updates its row in the `workers` table every 5 seconds | |
| Reaper | Every worker process looks for abandoned tasks at a regular interval | `ledger.reaper_interval_s`, configured default 5 seconds |

The reaper treats a running task as abandoned when its lease has run out, when its worker has not sent a heartbeat for `ledger.dead_worker_after_s` (configured default 30 seconds), or when its worker is no longer registered.

**What the engine does.** The task returns to the queue at its old place. No attempt is used. The task's reservation in the ledger is closed, and its expected output is kept in the level, because the lost call may still complete at the gateway and be charged there. An event records the recovery. If the first call's reply does arrive later, because the worker was slow and not dead, the call is recorded, since it was paid for, and nothing else changes: the task belongs to whoever has it now, and it is counted once. Every process runs a reaper, so any surviving process recovers the work of a dead one, and a restarted process recovers its own.

**What the user sees.** A line in the event feed that a lost call was returned to the queue. The job continues after a delay of up to about `ledger.dead_worker_after_s` plus `ledger.reaper_interval_s`.

The lost call is made again. If it had already completed at the gateway, its reply is lost and its tokens were used twice.

**A call that is lost again and again.** Each task counts how often it was returned to the queue because its worker was lost or its lease ran out. When one call has been returned more than `ledger.max_recoveries_per_call` times (configured default 3), it is not sent again, and its job fails. The error names the step and says that the call was returned to the queue that many times because the worker sending it stopped each time. Without this limit, a call that brings down every worker that sends it would go round for ever. Set the limit to 0 to turn it off. A warm-up in that position does not fail its job: it is dropped, and the step's calls run without the cache. A [clean stop](#restart-of-the-whole-app) of a worker returns its calls to the queue but never fails a job this way.

> **Not yet confirmed:** the recovery of a killed worker passes on the fake gateway. It was not tested on the real gateway in the proof of concept and has not run on Databricks Apps. It is to be checked in the first deployment.

## Database trouble

**What it is.** A database connection is lost, or a transaction fails with a deadlock or a serialization error.

**What the engine does.** The operation is tried again on a fresh connection, up to three times. A new connection is attempted up to six times with growing pauses, and reads the database password again each time, so short-lived credentials keep working. If the dispatcher cannot ask for admission, it tries again after a second.

Recording the result of a call is the sensitive moment, because the reply has been paid for. If it still fails after those tries, the worker keeps the reply and tries again for about a minute, with growing pauses. If the database is still away, the worker returns the task to the queue, and if even that fails, the reaper returns it once the lease or the heartbeat runs out. The call is then made again. The job does not fail.

**What the user sees.** For a short interruption, nothing or a pause. For an interruption of more than about a minute while a call is being recorded, a line in the event feed that a lost call was returned to the queue, and the cost of that call twice. The warnings are in the process log. See [Troubleshooting](../operations/troubleshooting.md).

## A failed job

One task that fails for good fails its job. When a job fails:

- its state becomes `failed` and its error holds the step's name and the cause;
- its tasks that have not been sent are cancelled;
- its steps that are not done are marked failed;
- its calls that are already in flight finish. They are recorded, their tokens count in the ledger and in the cost, and their results are discarded.

Other jobs are not affected. A failed job is not resumed: correct the cause and submit it again.

## A cancelled job

**What it is.** A user cancelled the job, on the **Run** screen, in the **Jobs** table of the **Activity** screen, or through the API. Stopping `python -m doc_engine load` with Ctrl+C also cancels the jobs it submitted.

**What the engine does.** The same as for a failed job, with the state `cancelled`: tasks not yet sent are cancelled and unfinished steps are marked cancelled. Calls in flight are not interrupted. They finish, are recorded, count in the ledger and in the cost, and their results are discarded.

**What the user sees.** The run is shown as cancelled. The room its queued calls would have used is available to other jobs at once.

## Restart of the whole app

Everything the engine needs is in Postgres, so a restart loses no job.

**A clean stop.** When the process is asked to stop, the worker cancels its calls in flight and returns their tasks to the queue at once, without using an attempt. Their expected output is kept in the ledger's level, since the gateway may still charge for them. The worker then removes itself from the `workers` table. A clean stop never fails a job for a call that was [returned too often](#a-worker-that-dies).

**A hard stop.** When the process is killed, its tasks stay marked as running. They are recovered as described under [A worker that dies](#a-worker-that-dies), by another process or by the restarted one, after about `ledger.dead_worker_after_s`.

**The start.** The process applies the database schema, which is safe to repeat, and copies the model limits from the configuration into the `quota` table. The ledger's level is kept as last recorded and has drained by the clock in the meantime. The worker registers and starts asking for work. Jobs that were queued or running continue from the task they had reached: finished calls are not repeated, and steps are planned as before.

**The screens.** The live stream reconnects by itself. The **Run** screen asks for the events after the last one it received, and the server reads them from the `events` table, so nothing is missing after the gap.

> **Note:** the ledger knows only what it recorded. After a restart that follows a saturating run, leave at least a minute before starting another one.

## See also

- [Jobs and tasks](jobs-and-tasks.md#states): the states a job, step and task pass through.
- [The quota ledger](quota-ledger.md#completion-one-database-call-the-same-clock): how each outcome is settled in the ledger.
- [Under heavy load](heavy-load.md#what-a-429-does): the pause after a rejection.
- [Troubleshooting](../operations/troubleshooting.md): what to do about each failure.
- [Run screen](../guide/run-screen.md): the event feed where these appear.
