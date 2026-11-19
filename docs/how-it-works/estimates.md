[Documentation](../README.md) › [How it works](README.md) › Estimates

# Estimates

The flow builder shows, in its header, how many model calls a run of the flow will make, how many tokens it will use and what it will cost. This page explains how those figures are computed, what they are based on before and after a step has really run, and how far to trust them. It is for flow authors who plan a run and for anyone who has to judge a cost figure.

**On this page**

- [What the estimate is](#what-the-estimate-is)
- [Calls](#calls)
- [Output tokens](#output-tokens)
- [Input tokens](#input-tokens)
- [Tokens per page, by file type](#tokens-per-page-by-file-type)
- [Cost](#cost)
- [Before and after a step has real runs](#before-and-after-a-step-has-real-runs)
- [What the estimate leaves out](#what-the-estimate-leaves-out)
- [How far to trust it](#how-far-to-trust-it)

## What the estimate is

The estimate is a calculation, not a trial. Nothing is sent to a model. The builder asks for it again whenever the flow changes in a way that matters: a step, a connection, a window, a model, or the file chosen for a source.

It walks through the flow in order, from the sources to the outputs. For each step it works out the number of calls, the input and output tokens of one call, and the cost. The number of items a step produces becomes the input of the next step. The header shows the totals; each step's own figures appear in the builder beside the step.

The estimate is for one job on the files chosen for the sources. See [Flow builder](../guide/builder.md).

## Calls

| Instruction | Calls |
|---|---|
| Map | The number of [windows](jobs-and-tasks.md#windows) over the items arriving, from the window size and overlap |
| Reduce | One |
| Filter | The items arriving, times the share the filter is expected to keep, and at least one |

For Map and Reduce the count is exact once the file is known, because it follows from the number of pages.

For Filter it cannot be exact: how many items the rule keeps depends on what the earlier step answers. The estimate uses the share kept in the most recent run of this flow that reached the filter. If there is none, it assumes 25%, and the builder marks the kept count as approximate. Everything after a filter inherits this uncertainty.

## Output tokens

Output per call is the step's **Expected output tokens per call**. If that is not set, 60% of the step's **Max output tokens** is used.

Once the step has at least three successful calls on record for this flow, with the same model and thinking level, the estimate uses the learned mean of those calls instead. The builder then shows the learned figure beside the setting.

Output tokens for the step are output per call times the number of calls.

## Input tokens

The input of one call is the sum of:

| Part | How it is estimated |
|---|---|
| The static prompt | The characters of the static prompt as it is sent, divided by 3.6, plus an allowance of 150 tokens. That is the step's system prompt and instructions, and the output contract (for a Schema output) or the rule for citing pages (for a Text output with **Cite pages in the text** on). |
| Pages | The pages in one call, times the tokens per page of the file. A Map call holds one window of pages, a Filter call the pages of one item of the step before it, and a Reduce step that reads pages directly holds all of them. |
| Earlier outputs | The items in one call, times the output per call of the step they come from |
| References | A source used as a reference: all its pages, times its tokens per page. A step used as a reference: all its outputs, times its output per call. |

References are added to every call of the step. The builder shows the reference tokens per call, because a large reference on a step with many calls is the commonest cause of an unexpectedly high figure. See [Prompt caching](prompt-caching.md#what-is-cached-and-what-is-not).

Token counts for text are approximate everywhere: one token per 3.6 characters.

## Tokens per page, by file type

| File | Tokens per page | Where the figure comes from |
|---|---|---|
| PDF | `models.<name>.input_tokens_per_page` for the step's model. The configured default is 1,728. | Measured in the proof of concept on Sonnet 5.5: 1,832 tokens for a one-page window and 1,623 per page in four-page windows. The configured value lies between them. |
| Image | The image's width times its height in pixels, divided by 750, after it has been scaled down to at most `documents.image_max_px` (configured default 1,568) on its long edge. An image is one page. | A formula in the code |
| Text | The average number of characters per page of the file, divided by 3.6, plus 12. Pages hold about `documents.text_page_chars` characters (configured default 3,000), which is about 845 tokens. | A formula in the code |

For images and text the figure is worked out once, when the file is uploaded, and stored with the file. The estimate and the scheduler's input estimate for each call both use it. For a PDF both use the model's figure. See [File types](../guide/file-types.md).

> **Not yet confirmed:** images and text files have not been sent to the real gateway from this codebase, so their token formulas have not been compared with what the gateway counts. The preflight check sends each model one small image to see whether image input is accepted. No date is set for comparing the token figures.

## Cost

The cost of a step is its tokens times the prices configured for its model under `models.<name>.pricing`, in US dollars per million tokens. There are four prices: input, output, cache read and cache write.

- **Output**: output tokens times the output price.
- **Input without caching**: every call pays the input price for the static prompt and for everything else.
- **Input with caching**: the static prompt is paid once at the cache-write price and on every further call at the cache-read price. Pages, earlier outputs and references are paid at the input price on every call.

The estimate assumes caching by the planner's own rule: the static prompt is marked for caching when its estimated size reaches three quarters of the model's `cache_min_tokens` (see [Prompt caching](prompt-caching.md#the-minimum-cacheable-size)), and the step has at least two calls.

**Warm-up calls.** A cached step with at least `worker.warmup_min_tasks` calls (configured default 3) gets a [warm-up call](prompt-caching.md#the-warm-up-call), unless `worker.cache_warmup` is off. The warm-up writes the static prompt to the cache, so every call of the step then reads it. The step's cost includes that: one cache write, and a cache read on every call. Without a warm-up, the first call writes the prompt and the others read it. Warm-ups are not added to the calls figure. The builder shows them apart, in a line under the per-step table: "Plus N small warm-up call(s) that store a long prompt for reuse. Skipped when another run has just done it."

The prices are configuration, not something the engine reads from the gateway. If the prices of the endpoint change, change them in the [settings](../operations/settings.md). Haiku is configured at its short-context rate.

## Before and after a step has real runs

| | Before the flow has run | After real runs |
|---|---|---|
| Output per call | The step's setting | The learned mean of real calls, once the step has three successful calls |
| Share a filter keeps | 25%, marked approximate | The share kept in the most recent run that reached the filter |
| Calls of a Map or Reduce step | From the file's pages | The same |
| Input per call | The calculation above | The same. Learned input is recorded but the estimate does not use it. |

What is learned is kept per flow, step, model and thinking level together. This has three consequences.

- A new flow, or a new step, starts from its settings, even if a similar step has run elsewhere.
- Changing a step's model or thinking level starts again from the settings.
- The learned mean follows recent calls. It is a plain average over the first ten calls and then a moving average, so the figure can shift between runs on different files.

The same learned mean is what the [quota ledger](quota-ledger.md#learned-expected-output-and-duration) counts for a call in flight. A step whose estimate has become accurate is also a step the scheduler handles well.

## What the estimate leaves out

- **A shared warm-up.** The estimate counts a warm-up for every step that would send one. A run that finds the prompt already warm, or shares another job's warm-up, sends none. See [Cost](#cost).
- **Retries and rejected calls.** A reply that fails the output schema and is retried is paid for twice.
- **First-wave cache misses.** See [Prompt caching](prompt-caching.md#optional-first-wave-settings).
- **Thinking**, until it is learned. Thinking tokens are output tokens. A step with thinking on produces more than its visible reply, and the setting has to allow for that.
- **Time.** The estimate gives tokens and cost, not duration. For the time a batch takes, see [Under heavy load](heavy-load.md#what-scales-and-what-is-the-ceiling).

The command `python -m doc_engine load --dry-run` prints the same calculation for one job and for the number of jobs asked for, and sends nothing. Like the builder, it uses the share each filter kept in the most recent run, and each file's own tokens per page.

## How far to trust it

| Figure | How good it is |
|---|---|
| Calls, without a filter | Exact for the chosen file |
| Calls, after a filter | A guess until the flow has run once on similar material |
| Input tokens | Within the spread of the tokens-per-page figure for PDFs. Rougher for long prompts and large references, which are counted by characters. |
| Output tokens | The least certain. As good as the step's setting before real runs, and as good as the step is consistent after them. |
| Cost | Follows from the others and from the configured prices |

Measured in the proof of concept on Sonnet 5.5: the output of a final summary varied by a factor of 3.7 on identical input, so the output of a Reduce step is uncertain even when it has been learned. With thinking set to high, configured expectations were too low: 1,400 expected against 1,609 actual for a map step, and 6,000 against 10,304 for a reduce step.

Use the estimate to see the order of magnitude and to compare two designs of a flow, for example a window of 4 against a window of 8. Do not use it as a quote. After a run, the real figures are on record for every call, and the job shows its actual cost.

> **Not yet confirmed:** this codebase's estimate has been compared only with runs on the fake gateway, whose token counts are invented. It has not been compared with a run on the real gateway. The first session against the real gateway is the first opportunity.

> **Tip:** run the flow once on a small file with **Test run** before estimating a large one. After that run, the steps with at least three calls use learned output, and the filter's share is real.

## See also

- [Flow builder](../guide/builder.md): where the estimate is shown.
- [Steps](../guide/steps.md): the expected output and max output settings the estimate starts from.
- [Prompt caching](prompt-caching.md): what the cached part of the cost means.
- [The quota ledger](quota-ledger.md): the other user of the learned figures.
- [Settings](../operations/settings.md): prices and tokens per page for each model.
