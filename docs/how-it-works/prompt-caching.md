[Documentation](../README.md) › [How it works](README.md) › Prompt caching

# Prompt caching

Every call of a step begins with the same text: the step's prompt and instructions. Document Engine has the model cache that text, so that all calls after the first read it at a fraction of the price and without using input quota. This page explains the warm-up call that makes this work, when it is and is not sent, what is cached, and what it saves. It is for readers who want to understand the extra call they see at the start of a step, or who are tuning cost.

**On this page**

- [What is cached and what is not](#what-is-cached-and-what-is-not)
- [The warm-up call](#the-warm-up-call)
- [Why a step's calls wait for it](#why-a-steps-calls-wait-for-it)
- [When a warm-up is sent](#when-a-warm-up-is-sent)
- [Sharing a warm-up across jobs](#sharing-a-warm-up-across-jobs)
- [The minimum cacheable size](#the-minimum-cacheable-size)
- [Optional first-wave settings](#optional-first-wave-settings)
- [What this saves](#what-this-saves)

## What is cached and what is not

A request for a step has two parts.

| Part | Contents | Cached |
|---|---|---|
| The static prompt | The step's system prompt, its instructions, and the output contract (the schema the reply must match) or the rule for citing pages | Yes, when long enough. The cache marker sits at its end. |
| The rest | The step's references, then the window of pages or the earlier outputs, then a short closing text that says which pages these are | No |

The static prompt is identical for every call of the step, and for its warm-up, so they all share one cache entry.

**References are not cached.** A [reference](../glossary.md#reference) is sent whole with every call of the step, at the full input price, and counts against the input limit every time. A large reference on a step with many calls is paid for on every call. The builder shows the reference tokens per call. Where that is too expensive, summarize the reference in a step first and reference that step. See [Several files in one flow](../guide/several-files.md).

**Value inputs are part of the prompt.** A job's copy of the flow has every `{{Name}}` already replaced by its value. Two jobs that run the same step with different values therefore have different static prompts and separate cache entries.

## The warm-up call

The warm-up is one small model call that writes a step's static prompt to the cache before the step's real calls are sent.

- It carries the step's static prompt, with the cache marker, and a one-word message.
- It asks for at most `worker.warmup_max_tokens` output tokens (configured default 1), with thinking off.
- It is a [task](jobs-and-tasks.md#warm-up-tasks) like any other. It has its job's priority and submission time and comes before the step's calls, it is admitted by the [quota ledger](quota-ledger.md) (counted as one output token and the size of the static prompt as input), and it has its own row in the record of calls.
- It is not counted in the step's progress. On the **Run** screen the event feed reports that the cache is warm when it completes.

## Why a step's calls wait for it

The calls of a step are created in state `waiting` and become `ready` only when the warm-up has completed.

Measured in the proof of concept on Sonnet 5.5: the warm-up is required, and it must complete before the burst of calls. A step's calls are released together and many are sent in the same moment. Calls sent before the cache entry exists do not read it, and each pays the full input price for the static prompt.

The wait is the length of one very short call, once per step. If the warm-up fails, the engine does not hold the step back: the calls are released and run without the cache. Caching is a saving, not a requirement. See [Failures and recovery](failures-and-recovery.md#a-failed-warm-up).

## When a warm-up is sent

A warm-up task is created for a step when all of these hold:

| Condition | Setting |
|---|---|
| Warm-ups are switched on | `worker.cache_warmup`, on by default |
| The static prompt is long enough to be cached on the step's model | `models.<name>.cache_min_tokens` |
| The step has enough calls for it to pay off | `worker.warmup_min_tasks`, configured default 3 |
| No other job has warmed the same prompt on the same model recently | `worker.warmup_ttl_s`, configured default 240 seconds |

A step with fewer calls than `worker.warmup_min_tasks`, such as a Reduce step with its single call, gets no warm-up. Its static prompt still carries the cache marker if it is long enough, so its first call writes the entry and a later call could read it.

## Sharing a warm-up across jobs

Jobs that run the same step on the same model have the same static prompt, so one warm entry serves them all.

The engine keeps a record of warm entries, by model and by a fingerprint of the static prompt:

- When a warm-up succeeds, the entry is recorded as warm.
- Each time a call of a step reports that it read from or wrote to the cache, the entry's time is refreshed (at most once every 20 seconds). A prompt that is in steady use stays warm.
- When a step is planned and its entry is newer than `worker.warmup_ttl_s`, no warm-up is created and the step's calls are `ready` at once.

The entry is recorded when a warm-up *completes*. Jobs that are submitted in the same moment are all planned before any warm-up has finished, so each of them sends its own. Ten jobs submitted together send ten warm-ups for their first step. Their later steps, and any job submitted after the first warm-up has completed, share.

## The minimum cacheable size

A model caches a prompt only above a minimum length. `models.<name>.cache_min_tokens` holds it for each model. The configured values are 1,024 tokens for Sonnet and 4,096 for Haiku and Opus.

The engine does not count tokens exactly before a call. It estimates the static prompt at one token per 3.6 characters and marks the prompt for caching when the estimate reaches three quarters of the model's minimum. It leans towards marking on purpose: a marker on a prompt that turns out to be too short is ignored, while a missing marker on a long prompt loses the saving.

A static prompt under that size is not marked and gets no warm-up. Its tokens are then part of every call's input, and the planner includes them in each call's input estimate.

## Optional first-wave settings

Measured in the proof of concept on Sonnet 5.5: in two of four single-job runs, the first 19 to 29 calls after the warm-up did not read the cache, although the warm-up had completed. That cost about one dollar per job. The cause is not known.

Two settings exist as possible remedies. Both are off by default.

| Setting | What it does |
|---|---|
| `worker.warmup_settle_s` | Waits this many seconds after the warm-up has returned before the step's calls are released |
| `worker.first_wave_size` | Releases only this many calls when the warm-up completes. The rest are released when the first of them completes. 0 means no limit. |

Both apply only to a step that sent its own warm-up, not to one that found the prompt already warm.

> **Not yet confirmed:** neither setting has been tried on the real gateway, so it is not known whether either one prevents the first-wave misses. No date is set for this check. To see whether misses occur, compare the cache reads and cache writes of a step's first calls in the job's exported rows.

## What this saves

**Money.** A cache read is priced far below ordinary input. With the configured prices for Sonnet, per million tokens: input 3.00, cache read 0.30, cache write 3.75. The write costs a quarter more than plain input, once; every read costs a tenth.

An example with round numbers, at those configured prices: a step with a static prompt of 2,000 tokens and 50 calls.

| | Static prompt tokens | Cost of the static prompt |
|---|---|---|
| Without caching | 50 x 2,000 as input | $0.30 |
| With caching | 2,000 written once by the warm-up, 50 x 2,000 read | $0.0075 + $0.03 = $0.0375 |

The pages, references and outputs of each call cost the same either way.

**Input quota.** Measured in the proof of concept on Sonnet 5.5: cache reads do not count against the input tokens per minute limit; cache writes do. The ledger counts the same way: the counted input of a call is its input tokens plus its cache writes. With caching, the static prompt uses input quota once instead of on every call.

Caching does not save output tokens or output quota, which is what usually limits throughput. It makes a heavy run cheaper, not faster.

The record of every call holds its cache reads and cache writes, and the summary printed by `python -m doc_engine load` totals them. See [Commands](../operations/commands.md).

> **Not yet confirmed:** this codebase has not called the real gateway, so its warm-up, the shared warm entries and the 240-second lifetime have been exercised on the fake gateway only. They are to be checked with the single-job runs of the first session against the real gateway.

## See also

- [Jobs and tasks](jobs-and-tasks.md): where the warm-up task sits among a step's tasks.
- [Estimates](estimates.md): how the builder's cost figure accounts for caching.
- [Under heavy load](heavy-load.md): the warm-ups of ten jobs submitted together.
- [Steps](../guide/steps.md): writing the prompt and instructions that make up the static prompt.
- [Settings](../operations/settings.md): the `worker` and `models` settings named on this page.
