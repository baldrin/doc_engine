[Documentation](../README.md) › [How it works](README.md) › The quota ledger

# The quota ledger

The quota ledger is the part of Document Engine that decides whether a model call may be sent now. It keeps, in the database, a model of what the gateway's rate limiter is doing, and admits a call only when the model says it fits. This page describes what the gateway was measured to do, how the ledger mirrors it, and walks through an example with round numbers. It is for readers who want to know why the engine does not overrun its quota.

**On this page**

- [What the gateway does](#what-the-gateway-does)
- [The ledger's model of it](#the-ledgers-model-of-it)
- [Admission: one database call](#admission-one-database-call)
- [Completion: one database call, the same clock](#completion-one-database-call-the-same-clock)
- [Learned expected output and duration](#learned-expected-output-and-duration)
- [The two capacity modes](#the-two-capacity-modes)
- [What max output tokens is and is not](#what-max-output-tokens-is-and-is-not)
- [A worked example](#a-worked-example)
- [What the ledger cannot see](#what-the-ledger-cannot-see)

## What the gateway does

The facts in this section were measured in the proof of concept on Sonnet 5.5, on the Databricks AI Gateway, at limits of 1,000,000 input tokens per minute, 100,000 output tokens per minute and 360,000 queries per hour. They differ from what the proof of concept first assumed.

| Topic | Measured in the proof of concept on Sonnet 5.5 |
|---|---|
| Start of a call | Nothing is reserved. The gateway does not set aside the call's max output tokens. |
| End of a call | The actual output is charged when the call completes. |
| Shape of the limiter | A token bucket that refills continuously at the output limit divided by 60 per second: 1,667 tokens per second at 100,000 per minute. Its capacity is about 40,000 tokens. The capacity was inferred from two probe runs, not read from the gateway. |
| A burst | The gateway accepts calls blindly for about one call duration, because none of them has been charged yet. When they complete and are charged, it rejects for about 10 seconds. |
| A rejection (HTTP 429) | The body holds only an error code and a message. There is no retry time and no retry header. The limit that was hit can be read only from the message text. |
| Cache reads | Do not count against the input limit. Cache writes do. |
| Quota headers | None. The use of the quota by other applications is invisible. |

The consequence of the first two rows is that the gateway cannot protect a caller from itself. A client that sends everything at once is accepted, then punished a call duration later. The protection has to be on the client's side, and it has to look ahead: it must count calls that are in flight but not yet charged.

> **Not yet confirmed:** these facts are for Sonnet 5.5. For Haiku 5.5 and Opus 5.5 the bucket has not been measured, and the configured values for those models are placeholders copied from Sonnet. They are to be measured with `python -m doc_engine probe bucket --model NAME` in the first session against the real gateway.

## The ledger's model of it

The `quota` table has one row per model. That row is the single authority on what may be sent for the model, for every worker process and every app instance.

### The output bucket

The ledger keeps three things for output:

| Quantity | What it is |
|---|---|
| **Level** | Output already charged: the actual output of completed calls. It drains continuously at the model's output limit divided by 60 per second, and never goes below zero. |
| **In flight** | Every call that has been admitted and has not completed, each counted at its *expected* output. |
| **Cap** | The most that level and in flight together may reach. The safety margin is already taken off. |

A call fits when:

```text
level (drained to now) + in flight + this call's expected output  <=  cap
```

The level mirrors what the gateway has charged. The in-flight sum is the look-ahead the gateway does not provide: output that will be charged soon. When a call completes, its expected output leaves the in-flight sum and its actual output joins the level.

### The safety margin

`ledger.safety_margin_fraction` is the share of each cap that is left unused. The configured default is 0.05, so the ledger works with 95% of each cap. The margin is the defence against what the ledger cannot know exactly: replies that run longer than expected, and other applications that use the same quota.

### The input bucket

Input is modelled the same way, with one difference: a call's estimated input is added to the input level when the call is admitted, and corrected when it completes.

- The cap is the model's input limit per minute, less the safety margin. With the configured defaults that is 950,000.
- The level drains at the input limit divided by 60 per second.
- At completion, the estimate is replaced by the counted input: input tokens plus cache writes. Cache reads are not counted, as measured. A call that failed or was rejected has its estimate removed.

The input estimate of a task is made when the task is planned: the pages of its window at the file's tokens per page, the output of earlier steps it receives, its references, and its static prompt when that is not cached.

### Queries per hour

When a model has a queries-per-hour limit (`models.<name>.qph`), a call is admitted only if the calls admitted in the last hour, plus this one, stay within it. The configured default is 360,000.

The three tests are made in that order: output, input, queries. Which one binds depends on the flow. With the configured limits, input is ten times output, so output binds unless calls carry more than ten times as much counted input as they produce output.

## Admission: one database call

A worker's dispatcher asks for work by calling one database function, `de_admit`. Everything below happens inside that one call, in one round trip.

1. Lock the quota rows of the models that have ready tasks.
2. For each such model, take the head of its queue. See [The queue and priority](queue-and-priority.md).
3. If the model is paused after a 429, answer "held" with the time left.
4. Drain the output and input levels to the present moment.
5. Add up the calls in flight for the model.
6. Work out what this call counts: its learned expected output if the step has one, otherwise the step's configured expected output. Never more than its max output tokens.
7. Test output, input and queries. If one fails, answer "blocked" with the reason and how long until the head could fit.
8. If all pass: open a reservation for the call, mark the task running with a lease for this worker, update the levels, mark the job and step as started if they were not, write the event, and return the task.

Because the quota row is locked while this happens, two processes cannot both admit a call into the same room. Because it is one round trip, the lock is held only for the time of the function. The time each admission takes is recorded per process and shown on the **Activity** screen and in the summary of `python -m doc_engine load`.

One exception to the test: a call that is larger than the whole cap is still admitted when nothing else is in flight on the model and the level is zero. Otherwise it could never run.

## Completion: one database call, the same clock

When a call finishes, the worker records the result and, last in the same transaction, calls `de_release`. It:

1. Locks the reservation and the model's quota row.
2. Drains the levels to the present moment.
3. Adds the actual output to the output level, and corrects the input level.
4. Closes the reservation, so the call is no longer counted in flight.
5. If the call was rejected with a 429, sets the pause for the model.
6. Sends the notification that wakes every dispatcher.

Two details matter.

**The same clock.** Admission and completion both read the time from the database, and both use the same drain arithmetic. Worker processes on different machines, with clocks that disagree, still agree about the level.

**Drain first, then add.** The level is brought up to date before the new output is added. If the output were added to a level last updated some time ago, and the drain applied afterwards, the drain of an idle period would be taken from the new output as well, and the ledger would under-count.

What is added at completion depends on how the call ended:

| How the call ended | Added to the output level |
|---|---|
| Success, including a reply cut off at max output tokens | The actual output tokens |
| Invalid, empty or refused reply | The actual output tokens the gateway reported |
| Rejected with a 429, transient error, permanent error | Nothing. The call produced no output. |
| Lost: the worker stopped or died while the call was in flight | The call's expected output. The call may still complete at the gateway and be charged there. |

## Learned expected output and duration

The ledger is only as good as its idea of what a call will produce. That idea starts as a setting and becomes a measurement.

- **Before a step has run**, a call counts at the step's configured expected output. If the step has none, 60% of its max output tokens is used.
- **Every successful call** updates the step's profile: the mean output tokens, the mean counted input and the mean duration. The profile belongs to one flow, step, model and thinking level together. Changing the model or the thinking level of a step starts a new profile.
- **Once a step has three samples**, its calls count at the learned mean output. This is `ledger.learn_estimates`, on by default.
- The mean is a plain average over the first ten samples and after that a moving average in which each new call weighs one tenth, so a step whose behaviour changes is followed.

The learned duration is used by the `duration` capacity mode, below. The learned output is also what the builder's [estimate](estimates.md) uses.

The ledger counts the mean, not the worst case. A step whose replies vary a great deal will sometimes produce more than was counted; the safety margin absorbs that up to a point. Measured in the proof of concept on Sonnet 5.5, the output of a final summary varied by a factor of 3.7 on identical input, and with thinking set to high the configured expectations were too low (1,400 expected against 1,609 actual for a map step, 6,000 against 10,304 for a reduce step).

> **Not yet confirmed:** learning was switched off in the proof of concept, which used configured expectations throughout. Counting in-flight calls at the learned mean has run only on the fake gateway. It is to be checked in the first session against the real gateway.

## The two capacity modes

`ledger.capacity_mode` chooses how the output cap is set.

| Mode | The cap | Status |
|---|---|---|
| `fixed` (configured default) | `models.<name>.bucket_capacity_output`, less the safety margin. With the configured defaults: 45,000 x 0.95 = 42,750. | The value 45,000 x 0.95 was validated in the proof of concept on Sonnet 5.5: six scheduler runs, 1,956 calls, no rejections. |
| `duration` | (`models.<name>.bucket_measured` + refill during half a call), less the safety margin. Half a call is half the step's learned call duration, or half of `ledger.default_call_s` (configured default 9 seconds) until the step has three samples. | Not run on the real gateway. |

**Why the cap can be larger than the gateway's bucket.** The gateway's own bucket was measured at about 40,000 tokens, yet 45,000 worked. Calls in flight are not charged now. They are charged when they complete, on average half a call duration from now, and the bucket refills in the meantime. So the ledger can allow the bucket plus about half a call of refill.

**Why there are two modes.** The fixed value was tuned by hand for calls of about 9 seconds. Longer calls, such as calls with thinking, allow more refill before they complete, and shorter calls allow less. The `duration` mode computes the allowance from the step's learned call duration instead of assuming 9 seconds. With the configured defaults and a 9-second call it gives (40,000 + 1,667 x 4.5) x 0.95 = 45,125. In this mode the cap is worked out at each admission from the step of the task at the head of the queue.

> **Not yet confirmed:** the `duration` mode has not run on the real gateway. The fixed value of 45,000 holds for Sonnet 5.5 with calls of about 9 seconds, and has not been checked for much longer or much shorter calls. No date is set for either check.

When the endpoint's limits change, change `models.<name>.itpm` and `models.<name>.otpm` and run the bucket probe again. Do not scale the bucket by hand. See [Settings](../operations/settings.md).

## What max output tokens is and is not

Each step has a max output tokens setting. It is sent with every call of the step as the hard limit on the reply.

| It is | It is not |
|---|---|
| A guard against a runaway reply. A reply that reaches it is cut off and marked truncated. | A reservation. The gateway sets nothing aside for it, as measured. |
| The upper bound on what the ledger counts for a call | What the ledger counts for a call. That is the expected output. |
| A limit that includes thinking: with thinking on, thinking tokens use it up too | A cost. A high value costs nothing unless the reply really is long. |

In practice: set max output tokens comfortably above what the step should produce, and set the expected output to what it usually produces. A generous max output tokens does not slow the queue. An expected output that is far too high does, because every call in flight then counts for more than it will produce. An expected output that is far too low admits too much at once, until the step has three samples and the learned value takes over.

## A worked example

The numbers here are round and chosen for the arithmetic. They are not the configured defaults and not measurements.

Suppose a model with an output limit of 60,000 tokens per minute, so the level drains at 1,000 tokens per second. The cap, after the safety margin, is 40,000. Every call of a step is expected to produce 1,000 tokens and takes 10 seconds. To keep it simple, every call produces exactly what was expected, and calls admitted together complete together.

| Time | What happens | Level | In flight | Level + in flight |
|---|---|---|---|---|
| 0 s | 100 tasks are ready. The level is 0 and nothing is in flight. The ledger admits the head again and again: 40 calls. | 0 | 40,000 | 40,000 |
| 0 s | The 41st would make 41,000. It does not fit. The queue is blocked. | 0 | 40,000 | 40,000 |
| 0 to 10 s | Nothing changes. The level is already 0, so there is nothing to drain, and the calls in flight keep their place. | 0 | 40,000 | 40,000 |
| 10 s | The 40 calls complete. Each moves 1,000 from in flight to the level. | 40,000 | 0 | 40,000 |
| 10 s | The head would make 41,000. Still blocked: it needs 1,000 of room, which takes 1 second to drain. | 40,000 | 0 | 40,000 |
| 11 s | 1,000 has drained. The head fits and is admitted. | 39,000 | 1,000 | 40,000 |
| 12 s, 13 s, ... | Each second another 1,000 drains and one more call is admitted. | falling | rising | 40,000 |
| 21 s onwards | The call admitted at 11 s completes: 1,000 moves from in flight to the level. One call completes and one is admitted every second. | about 30,000 | about 10,000 | 40,000 |

Three things to take from it.

**The first burst is the size of the cap.** With an empty bucket, the engine sends 40 calls at once and then stops by its own decision. The gateway has charged nothing yet and would have accepted more; those extra calls are the ones it would later reject.

**The steady rate is the refill rate.** After the burst, one 1,000-token call is admitted per second: 60,000 tokens per minute, which is the model's limit. The engine runs at the quota, not above it, and about 10 calls are in flight at any moment (one per second, 10 seconds each).

**A large call waits for its room and nothing passes it.** Suppose a final summary expected to produce 5,000 tokens reaches the head at 30 s, when level and in flight together are 40,000. It needs them to fall to 35,000. Completions do not change the sum; only the drain does, at 1,000 per second. With nothing else admitted, that takes 5 seconds. Then the summary is sent and the one-per-second rhythm continues. If smaller calls were allowed past it, the sum would never fall and the summary would never go.

When calls produce less than expected, each completion lowers the sum and room appears sooner. When they produce more, the sum goes above the cap for a while and admission pauses until the drain has brought it back. That is the case the safety margin exists for.

## What the ledger cannot see

- **Other applications on the same quota.** The gateway sends no quota headers, as measured, so their use is invisible. The only defences are the safety margin and the pause after a 429. How large the margin should be depends on who else uses the workspace.
- **Calls it has lost.** A call whose worker died may still complete at the gateway. The ledger keeps its expected output in the level to cover this.
- **The gateway's real bucket.** The ledger's level is a model. It starts from what was last recorded and drains by the clock. After a run that saturated the model, leave at least a minute before the next one.

When the ledger is wrong, the gateway answers with a 429. The engine then pauses the model for every worker, for `ledger.hold_on_429_s` at first and longer while rejections continue, and puts the task back without using an attempt. See [Under heavy load](heavy-load.md#what-a-429-does).

## See also

- [The queue and priority](queue-and-priority.md): which task the ledger is asked about.
- [Under heavy load](heavy-load.md): the ledger at work with ten jobs.
- [Failures and recovery](failures-and-recovery.md): how each kind of failed call is settled in the ledger.
- [Settings](../operations/settings.md): the `models` and `ledger` settings named on this page.
- [Fake gateway](../operations/fake-gateway.md): why the fake gateway's numbers say nothing about the real one.
