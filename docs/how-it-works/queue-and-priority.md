[Documentation](../README.md) › [How it works](README.md) › The queue and priority

# The queue and priority

This page explains which model call goes next: how the queue is ordered, why only the first task in it is ever considered, how workers wait without polling constantly, and what **Interactive** and **Bulk** mean to someone who submits a job. It is for readers who want to predict how their job will behave when others are running.

**On this page**

- [One queue per model](#one-queue-per-model)
- [The ordering rule](#the-ordering-rule)
- [What the rule means for jobs](#what-the-rule-means-for-jobs)
- [The strict head](#the-strict-head)
- [Several models at once](#several-models-at-once)
- [How workers wait](#how-workers-wait)
- [Interactive and bulk for a user](#interactive-and-bulk-for-a-user)

## One queue per model

Each model has its own quota at the gateway, so each model has its own queue. The queue of a model is all the [tasks](jobs-and-tasks.md) for that model that are in state `ready`, from every job.

The queue is not a separate structure that could be lost or fall out of step. It is the `tasks` table, read in a fixed order. A task enters the queue when it becomes `ready` and leaves it when the [quota ledger](quota-ledger.md) admits it. Tasks that are still waiting for a warm-up, or that have not been planned yet, are not in the queue.

The engine never shares a budget between models. A full Sonnet queue does not delay a Haiku task.

## The ordering rule

Within a model's queue, tasks are ordered by:

1. **Priority.** Tasks of interactive jobs come before tasks of bulk jobs.
2. **Job submission time.** Within the same priority, the job submitted earlier comes first.
3. **Task order.** Within a job, tasks come in the order they were created.

The task at the front after this ordering is the **head**. It is the only task the ledger considers.

A task keeps its place when it returns to the queue. A call that the gateway rejected, a call being retried, and a call recovered from a lost worker all go back to where the rule puts them, which is normally the front of their job, not the end of the queue.

## What the rule means for jobs

**Within a priority, jobs are served first come, first served, not in turns.** While the earliest job has ready tasks, they all sort before the tasks of a later job. A later job advances when the earlier one has nothing ready: while it waits for a warm-up, or when all its remaining calls are already in flight. Ten bulk jobs submitted together therefore tend to finish one after another, not all together at the end. [Under heavy load](heavy-load.md) walks through this.

**A job's later steps overtake younger jobs.** The tasks of a job's second step are created when its first step finishes. They carry the job's submission time, so they sort before every task of every job submitted later, in the same priority.

**Interactive always sorts before bulk.** There is no ageing: a bulk task does not move forward because it has waited long. If interactive tasks for a model keep arriving without a gap, bulk tasks for that model keep waiting. Bulk work continues as soon as no interactive task for that model is ready.

**Calls in flight are never interrupted.** Priority decides what is sent next. It does not cancel or pause what has been sent.

## The strict head

If the head does not fit in the quota, nothing behind it on that model is sent, even a small task that would fit.

The reason is fairness to large calls and to priority. If small calls were allowed past a large one, a steady stream of them would keep using the room as it appeared, and a large call, such as a final summary with a long expected output, could wait indefinitely. An interactive task waiting for room could likewise be overtaken by bulk tasks that happen to be smaller. With a strict head, the room that drains free goes to the head, and the head is always the task that the ordering rule says is most deserving.

The cost is that the queue stands still while the head's room appears. The ledger's level drains continuously, so room keeps appearing. The [worked example](quota-ledger.md#a-worked-example) shows the arithmetic.

One exception keeps a very large call from blocking the queue for ever. A call whose expected output is larger than the whole cap is still sent, once nothing else is in flight on that model and the level has drained to zero.

## Several models at once

Queues of different models do not block each other: when the head of one model does not fit, the tasks of another model can still be admitted.

Two things are shared across models within one process:

- **The number of calls in flight.** `worker.concurrency` (configured default 128) is a limit per process, over all models.
- **The order in which models are looked at.** One request for admission looks at the head task of each model that has ready tasks, in the same order as within a queue: interactive before bulk, then job submission time. It admits the first head that fits. The dispatcher then asks again at once.

Neither matters while a process has free slots, which is the usual case when the quota is what limits the work. They matter when a process reaches its `worker.concurrency` limit. That happens with steps whose calls have a small expected output, because many such calls fit in the quota at once. Each slot that frees then goes to the model whose head task has the highest priority and fits, so an interactive call on one model goes before a bulk call on another.

## How workers wait

Each process has one dispatcher loop. It is the only thing in the process that asks the ledger for a task. Each time it asks, the ledger answers with one of four things:

| Answer | Meaning | What the dispatcher does |
|---|---|---|
| Admitted | The head fits. Here is the task. | Starts the call and asks again at once |
| Blocked | The head does not fit yet | Sleeps for the time the ledger says the head could fit, between 0.05 and 1 second |
| Held | The model is paused after a 429 | Sleeps until the pause ends |
| Empty | No task is ready | Sleeps for up to 1 second |

The dispatcher does not sleep through anything that could change the answer. It is woken early when:

- a call in its own process finishes;
- any process completes a call, submits a job, or returns a lost call to the queue. Each of these sends a Postgres notification that every dispatcher listens for.

So a blocked queue costs one check per completion or per short interval, from one waiter per process, instead of a check from every idle slot. When a process already has `worker.concurrency` calls in flight, the dispatcher does not ask at all until one finishes.

If the notification channel is lost or not available, the dispatcher logs it, carries on with the timed checks alone (never longer than 1 second), and tries to listen again every 5 seconds.

> **Note:** the single dispatcher replaces the design of the proof of concept, where every idle worker checked a blocked queue about every 0.25 seconds. Measured in the proof of concept on Sonnet 5.5, that made 108,000 to 178,000 blocked checks in one saturated run.

The number of blocked checks and admissions per model is counted in the `quota` table, and each process reports its admission round-trip times. See [Monitoring](../operations/monitoring.md).

## Interactive and bulk for a user

Every job is submitted as **Interactive** or **Bulk**.

| Where | How the priority is chosen |
|---|---|
| **Test run** in the flow builder | The **Priority** choice, **Interactive** or **Bulk** |
| **Activity** | The numbers of **Interactive jobs** and **Bulk jobs** to submit |
| The API | The `priority` field, `interactive` or `bulk`. Left out, a job is interactive. |

What the choice means:

- **When the quota is free, nothing.** Both kinds are sent at once.
- **When the quota is busy, interactive calls go first.** An interactive job submitted while bulk jobs are running does not wait for them to finish. Its calls go to the front of the queue and are sent as room appears.
- **Bulk does not cost less** and does not use a different quota. It is the same calls on the same model, sent later when there is competition.
- **Bulk is the polite choice for work nobody is waiting on.** A batch submitted as interactive competes with every person who is testing a flow.

On the **Run** screen, the **Interactive lane** tile shows a bulk job when interactive work is going ahead of it.

Measured in the proof of concept on Sonnet 5.5: interactive jobs submitted while bulk load was running took 64 to 74 seconds, against 60 to 67 seconds with nothing else running. Without the scheduler, the same jobs took 142 to 254 seconds. Each configuration was run once, so small differences between runs are not significant.

> **Not yet confirmed:** this codebase has shown the same ordering on the fake gateway only. The interactive timings above are from the proof of concept's scheduler, not from this code. They are to be repeated in the first session against the real gateway.

## See also

- [The quota ledger](quota-ledger.md): what "fits" means for the head.
- [Under heavy load](heavy-load.md): the ordering rule at work with ten jobs, and an interactive job overtaking them.
- [Failures and recovery](failures-and-recovery.md): what returns a task to the queue.
- [Activity screen](../guide/activity-screen.md): submitting several interactive and bulk jobs.
- [Settings](../operations/settings.md): `worker.concurrency` and the other settings named here.
