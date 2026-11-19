[Documentation](../README.md) › [How it works](README.md) › Under heavy load

# Under heavy load

This page answers one question: what happens when many jobs are waiting and each makes many model calls? It walks through ten large jobs submitted at once, then covers what limits throughput, why the gateway does not reject calls in normal running, what happens when it does, how an interactive job overtakes bulk work, and what adding processes does and does not change. It is for engineers and technical managers who need to judge whether the engine will cope with their workload.

**On this page**

- [The short answer](#the-short-answer)
- [Ten large jobs, step by step](#ten-large-jobs-step-by-step)
- [What limits throughput](#what-limits-throughput)
- [Why there are no rejections in normal running](#why-there-are-no-rejections-in-normal-running)
- [What a 429 does](#what-a-429-does)
- [How an interactive job overtakes bulk work](#how-an-interactive-job-overtakes-bulk-work)
- [Several worker processes or app instances](#several-worker-processes-or-app-instances)
- [What scales and what is the ceiling](#what-scales-and-what-is-the-ceiling)
- [The saturation confirmation](#the-saturation-confirmation)
- [Measured facts and expectations](#measured-facts-and-expectations)

## The short answer

Waiting work costs almost nothing. A waiting call is a row in a table. The engine sends calls at the rate the model's quota refills, no faster, however many are waiting. A batch takes about as long as its total output tokens divided by the model's output limit per minute. Its jobs finish roughly in the order they were submitted, and a person who starts an interactive job in the middle is served first. The ceiling is the model quota, not the application.

## Ten large jobs, step by step

### The example

Ten bulk jobs are submitted together. Each runs the same flow on a 150-page PDF:

- a **Map** step with a window of 4 pages and an overlap of 1, which is 50 calls, each expected to produce 900 output tokens;
- a **Reduce** step, one call over the 50 outputs, expected to produce 4,000 output tokens.

Both steps use the same model, with the configured defaults for Sonnet: an output limit of 100,000 tokens per minute, which refills 1,667 tokens per second, and an output cap of 42,750 (45,000 less the 5% safety margin, in `fixed` mode). The Map step's static prompt is long enough to be cached. Calls are assumed to take about 9 seconds and to produce what was expected.

In total: 500 map calls, 10 reduce calls, 490,000 output tokens.

> **Note:** the times and counts in this walk-through are arithmetic from the configured defaults and from the rules in the code. They are not measurements. What was measured is listed at the [end of the page](#measured-facts-and-expectations).

### 1. Submission

Ten jobs at once is at or above `server.saturating_jobs`, so the engine asks for [confirmation](#the-saturation-confirmation) first.

Each job is then stored in its own transaction, with its own copy of the flow. For each job the Map step is planned. Job 1 gets one warm-up task in state `ready` and 50 calls in state `waiting`. Jobs 2 to 10 have the same static prompt on the same model and find job 1's warm-up ahead of them in the queue, so each gets 50 calls in state `waiting` and no warm-up of its own. The Reduce steps are not planned yet. See [Jobs and tasks](jobs-and-tasks.md#why-tasks-are-planned-one-step-at-a-time).

Right after submission the queue holds 1 task. Another 500 exist and are waiting for that warm-up.

### 2. The warm-up

A warm-up counts for one output token, so it is admitted at once. The ten jobs share it: one warm-up is sent per model and static prompt. See [Prompt caching](prompt-caching.md#sharing-a-warm-up-across-jobs).

When the warm-up completes, the 50 calls of every job become `ready`. The queue then holds 500 tasks, ordered job by job: all of job 1's calls, then job 2's, and so on, because within one priority the earlier job goes first.

### 3. The first burst

The level is near zero and nothing is in flight. The ledger admits the head again and again until the next call would not fit: 47 calls (47 x 900 = 42,300; a 48th would make 43,200, above 42,750). These are mostly job 1's calls.

Then the queue is blocked. 453 calls wait. The process has 47 calls in flight and one dispatcher sleeping; nothing is polling.

### 4. The steady rhythm

For about 9 seconds little changes: the calls in flight are still counted and the level is already near zero. Then the first calls complete. Each completion moves about 900 tokens from "in flight" to the level, and the level drains at 1,667 tokens per second. From here on, room for one more 900-token call appears a little under twice per second.

The engine now sends about 1.85 calls per second, about 111 per minute, which is 100,000 output tokens per minute: the model's limit. About 17 calls are in flight at any moment (1.85 per second, 9 seconds each), far below the first burst of 47 and far below `worker.concurrency`.

### 5. Job 1 reaches its Reduce step

When job 1's 50th map call completes, the same transaction marks the Map step done and plans the Reduce step: one task. It carries job 1's submission time, so it sorts ahead of every task of jobs 2 to 10 and becomes the head.

It is expected to produce 4,000 tokens, more than four times a map call. The ledger does not let the smaller calls behind it pass. The queue stands still while 4,000 tokens of room drain free, which takes up to about two and a half seconds at 1,667 tokens per second. Then the Reduce call is sent, and the rhythm continues with job 2's map calls. See [The strict head](queue-and-priority.md#the-strict-head).

When the Reduce call completes, job 1 is done. Its results are complete while nine jobs are still running.

### 6. Jobs 2 to 10

The same happens for each job in turn. A later job's calls are sent when the jobs before it have nothing ready, and each job's Reduce call goes to the head as soon as its Map step finishes. The jobs complete one after another, in the order they were submitted.

### 7. The end

490,000 output tokens at 100,000 per minute is a little under five minutes of refill. The first burst used room that was already there, which saves most of half a minute. The ten jobs should therefore take about four and a half minutes, plus the length of the last Reduce call.

A single job of this kind, alone, would fit almost entirely in the first burst and be limited by the length of its calls, not by the quota. The scheduler does not make a batch finish sooner than the quota allows. Its value is that the batch runs at the quota with no rejections, and that other work can still get in.

## What limits throughput

In the order they usually bind:

| Limit | Where it comes from | When it binds |
|---|---|---|
| The model's output tokens per minute | `models.<name>.otpm`, the gateway's limit | Almost always. In steady running the engine sends output at this rate. |
| The model's input tokens per minute | `models.<name>.itpm` | When calls carry much more input than output: with the configured limits, more than ten times as much counted input as output. Large references on steps with many calls are the usual cause. Cached prompt tokens that are read do not count. |
| Queries per hour | `models.<name>.qph` | Only with very many very small calls |
| Calls in flight per process | `worker.concurrency`, configured default 128 | When many calls fit in the bucket at once: calls with a small expected output, or very long calls. A step whose calls produce 40 tokens could have over a thousand in flight by the quota alone, so the process limit binds first. |
| Gateway connections | `gateway.max_connections`, configured default 512 | Never before `worker.concurrency`: the engine refuses to start unless it is larger. |
| Database connections per process | `postgres.pool_size`, configured default 16 | Each completed call needs a connection for a moment to record its result. Not measured under load. |
| One admission per database round trip | The dispatcher admits one call per call to the database | When the round trip is slow. Each process reports its admission times. |

> **Not yet confirmed:** the last three rows have been exercised on a local Postgres with the fake gateway only. The latency of Lakebase was not measured in the proof of concept, which could not reach it. It is to be measured in the first deployment to Databricks Apps.

## Why there are no rejections in normal running

A gateway rejects a call when its bucket is overdrawn. The gateway reserves nothing when a call starts, so it accepts whatever is sent and discovers the overdraft only when the calls complete. A client that sends everything at once is accepted first and rejected afterwards.

The engine does not send everything at once. Before each call it asks the [quota ledger](quota-ledger.md) whether the output already charged, plus the expected output of every call in flight, plus this call, stays under the cap. The calls that would have been rejected are simply not sent yet. They wait as rows in the queue, which costs nothing, instead of going out and coming back as 429s, which costs a round trip each and provokes a period of rejections.

Measured in the proof of concept on Sonnet 5.5:

- Six runs with the scheduler made 1,956 calls and received no rejections.
- Five runs without it, sending calls as fast as the workers could, received 8,399 rejections.
- Without a scheduler, the gateway accepted a burst blindly for about one call duration, at about 2.6 times the output limit, and then rejected for about 10 seconds.
- The scheduler held 90 to 98% of the output limit. The limit is a bucket and not a per-minute count, so this figure depends on how utilization is defined.
- The runs without the scheduler finished a batch 2 to 13% sooner, by overrunning the limit. The cost was equal.

"Normal running" has conditions. Rejections can still happen when:

- another application uses the same model quota, which the engine cannot see;
- calls produce much more than their expected output, beyond what the safety margin covers;
- the configured bucket does not match the model. The Haiku and Opus values are placeholders;
- calls are much longer or shorter than the 9 seconds the `fixed` cap was tuned for.

> **Not yet confirmed:** this codebase has not called the real gateway. The zero-rejection result belongs to the proof of concept's scheduler, whose ledger rule this code re-implements. A ten-job run is planned for the first session against the real gateway.

## What a 429 does

When the gateway rejects a call with HTTP 429, the engine treats it as information about the quota, not as a failure of the task.

1. **The call is recorded** with outcome `429` and the limit the message names: output, input or queries.
2. **The task returns to the queue**, at its old place. Its rejection count goes up. **No attempt is used.** Only a call rejected `worker.max_rejections_per_call` times in a row (configured default 50) fails, so that a call the gateway will never accept cannot block the model for ever.
3. **Nothing is added to the ledger's output level**, because a rejected call produced no output. Its input estimate is removed.
4. **The model is paused for every worker.** The pause is written on the model's quota row. The first pause lasts `ledger.hold_on_429_s` (configured default 1 second). If a call sent after that pause is rejected too, the next pause is twice as long, and so on up to `ledger.hold_on_429_max_s` (configured default 15 seconds): 1, 2, 4, 8, 15. The first call accepted after a pause puts it back to the start. Every dispatcher in every process gets the answer "held" for that model until the pause ends. Other models are not affected, and calls already in flight continue.
5. **After the pause**, admission resumes with the head of the queue, under the usual test.

On the **Run** screen the event feed shows the rejection, the limit and the pause, and the rejection count of the run goes up. A job is not marked failed.

The pause is the engine's answer to being wrong about the quota. One rejection means the bucket is overdrawn, so every further call sent in the next moment would be rejected too. Stopping all workers at once, through the shared quota row, avoids that.

> **Not yet confirmed:** the pause has not been exercised on the real gateway. All six scheduler runs in the proof of concept had no rejections, so there was nothing to pause for. The gateway was measured to reject for about 10 seconds after an overrun, which is why the pause grows while rejections continue; how the two interact, in particular when another application shares the quota, is not known. No date is set for this check.

## How an interactive job overtakes bulk work

Suppose that two minutes into the ten bulk jobs, someone starts a **Test run** as **Interactive**.

1. **Its tasks go to the front.** Interactive sorts before bulk, so its first task is the head of the queue as soon as it is ready. If its static prompt is already warm from another job, its calls are ready at once; otherwise its calls wait for a warm-up of the same prompt that has already been sent, or its own warm-up goes first.
2. **Bulk calls in flight are left alone.** Nothing is cancelled. They complete and are charged as usual.
3. **Bulk tasks stop being admitted** on that model while the interactive job has ready tasks, because the head is always an interactive task.
4. **The interactive job receives the whole refill.** It does not get an empty bucket: when it arrives, the bucket is full of bulk work. Its calls are admitted at the refill rate as room drains free.
5. **Bulk work continues** in the gaps, when the interactive job has nothing ready, and fully once it is done.

So the interactive job waits only for room to drain, not for the bulk jobs to finish, and the delay it suffers is the difference between starting on a full bucket and starting on an empty one.

Measured in the proof of concept on Sonnet 5.5: interactive jobs took 64 to 74 seconds under bulk load, against 60 to 67 seconds with nothing else running. Without the scheduler they took 142 to 254 seconds. Each configuration was run once.

Bulk jobs on a different model are not involved at all: each model has its own queue and its own quota.

## Several worker processes or app instances

Several processes can work the same queue: more than one app instance, or extra processes started with `python -m doc_engine worker`.

- **One ledger.** Admission locks the model's quota row in the database. Two processes cannot admit into the same room, so the quota is respected however many processes there are.
- **One queue.** Every dispatcher is offered the same head. Whichever asks first sends it.
- **More calls in flight.** Each process may have `worker.concurrency` calls in flight. The total is the sum.
- **Prompt wake-ups.** A completion in one process wakes the dispatchers of the others through a database notification.
- **One pause.** A 429 received by one process pauses the model for all.
- **Mutual recovery.** Every process looks for calls whose worker has stopped and returns them to the queue. See [Failures and recovery](failures-and-recovery.md#a-worker-that-dies).

What more processes do not do is raise throughput beyond the quota. In the ten-job example about 17 calls are in flight in steady running; one process with a limit of 128 has room to spare, and a second process would send the same calls at the same rate.

More processes help when one process is at its limit on calls in flight, when the work of building requests and recording results needs more than one process can give, and when the service must survive the loss of a process.

> **Not yet confirmed:** several worker processes, and the recovery of a killed worker, pass on the fake gateway. They were not tested on the real gateway in the proof of concept and have not run on Databricks Apps. They are to be checked in the first deployment.

## What scales and what is the ceiling

| Grows without much effect | Why |
|---|---|
| Jobs waiting | A waiting job is rows in the database. Nothing in a process grows with it. |
| Tasks waiting | The ledger looks only at the head of each model's queue, found through an index. |
| Calls per job | Tasks are planned step by step, and sent as the quota allows. |
| Processes | They share the ledger through the database. |

| The ceiling | What raises it |
|---|---|
| The model's output and input limits at the gateway | A higher limit on the endpoint. Then change `models.<name>.itpm` and `models.<name>.otpm` and run the bucket probe again. |
| | Using more than one model. Each model has its own quota and its own queue, so steps on different models do not compete. |

The time a batch takes is therefore close to its total output tokens divided by the model's output limit per minute. The [estimate](estimates.md) in the builder gives the output tokens of one job; `python -m doc_engine load --dry-run` gives the total for a number of jobs without sending anything.

What does not shorten a batch: more processes, a higher `worker.concurrency`, or submitting it as interactive.

## The saturation confirmation

A large submission can use a model's whole quota for minutes. Every other application in the workspace that uses the same model is slowed for that time, and the engine cannot see them. So the engine asks before it starts.

- Submitting `server.saturating_jobs` jobs or more at once (configured default 4) is refused until it is confirmed.
- On the **Activity** screen a dialog, **Start a saturating run?**, names the number of jobs and the endpoint. Confirming submits them.
- The public endpoint starts one job per request and asks for no confirmation. A program that sends many requests is trusted to have that agreement already; send large sets as `bulk`. See [Examples](../api/examples.md#running-a-flow-on-many-files).
- On the command line, `python -m doc_engine load` and `python -m doc_engine probe bucket` need `--confirm-saturation`.
- A single **Test run** from the builder is never asked, whatever `server.saturating_jobs` is.
- At most 50 jobs can be submitted in one request from the screen, or in one `load` command.

The confirmation counts the jobs of one submission. It does not look at what is already queued or running, and jobs submitted one at a time are not counted together.

## Measured facts and expectations

| Statement | Status |
|---|---|
| The gateway reserves nothing at the start of a call and charges actual output at completion | Measured in the proof of concept on Sonnet 5.5 |
| The gateway behaves like a bucket of about 40,000 output tokens refilling at 1,667 per second | Measured in the proof of concept on Sonnet 5.5. The capacity is inferred from two probe runs. |
| A cap of 45,000 less 5% gives no rejections with calls of about 9 seconds | Measured in the proof of concept on Sonnet 5.5: six runs, 1,956 calls |
| Without a scheduler the gateway rejects heavily | Measured in the proof of concept on Sonnet 5.5: five runs, 8,399 rejections |
| Interactive jobs stay close to their idle time under bulk load | Measured in the proof of concept on Sonnet 5.5: 64 to 74 seconds against 60 to 67 |
| The ordering, the strict head, the single dispatcher, admission in one database call | What this code does. Run on the fake gateway only. |
| The times and counts of the ten-job walk-through | Arithmetic from the configured defaults. Not measured. |
| The pause after a 429 | What this code does. Never exercised on the real gateway. |
| Learned expected output, the `duration` capacity mode | What this code does. Not run on the real gateway. |
| Several processes, a killed worker, Lakebase, Databricks Apps | Pass on the fake gateway where they apply. Not run on the real platform. |
| Haiku 5.5 and Opus 5.5 buckets | Placeholders until the bucket probe has been run for each |
| Another application sharing the quota, overload lasting many minutes | Not tested anywhere |

## See also

- [The quota ledger](quota-ledger.md): the admission test used throughout this page.
- [The queue and priority](queue-and-priority.md): the ordering rule and the strict head.
- [Failures and recovery](failures-and-recovery.md): everything else that can go wrong with a call.
- [Monitoring](../operations/monitoring.md): the figures to watch during a heavy run.
- [Limits](../operations/limits.md): the hard limits in one place.
