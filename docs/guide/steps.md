[Documentation](../README.md) › [User guide](README.md) › Steps

# Steps

A step is a template for model calls: a prompt, a model, limits and a description of the reply it must give. This page explains every setting of a step, what the engine adds to your prompt, and the two actions for trying a step out. It is for anyone who writes or tunes steps in the [flow builder](builder.md).

**On this page**

- [Where the settings are](#where-the-settings-are)
- [Prompt blocks](#prompt-blocks)
- [What the engine adds](#what-the-engine-adds)
- [Inserting flow inputs](#inserting-flow-inputs)
- [Model](#model)
- [Max output tokens](#max-output-tokens)
- [Expected output tokens per call](#expected-output-tokens-per-call)
- [Thinking](#thinking)
- [Output contract](#output-contract)
- [Track source pages](#track-source-pages)
- [Test this step](#test-this-step)
- [View last outputs](#view-last-outputs)

## Where the settings are

Select a step on the canvas. The right-hand panel shows its name and four tabs:

| Tab | Settings |
|---|---|
| **Prompt** | **System**, **Instructions**, inserting flow inputs; and, for convenience, **Model**, **Max output tokens**, **Output contract** and **Track source pages**. |
| **Model** | **Model**, **Max output tokens**, **Thinking**, **Expected output tokens per call**. |
| **Input** | The [instruction](instructions.md) and the step's [references](several-files.md#references). These belong to the connections into the step, and are explained on those pages. |
| **Output** | **Output contract**, the schema **Fields**, **Track source pages**. |

Some settings appear on two tabs. They are the same setting; change it in either place.

A step makes one call for each window, item or set of items its instruction gives it. Every call of a step uses the same settings. What differs between calls is only the material: which pages, or which earlier outputs.

> **Screenshot to add:** `images/builder-step-model-tab.png`. A step selected with the right-hand panel on the Model tab: Model, Max output tokens, the Thinking control with Off, Low, Medium and High, Expected output tokens per call with its hint, and the line giving the model's limits and prices.

## Prompt blocks

The prompt has two blocks, both on the **Prompt** tab.

| Block | What to write | Placeholder shown |
|---|---|---|
| **System** | Who the model is and how it should work: its role, its reader, the rules it must keep. | Who the model is and how it should work |
| **Instructions** | What to do with each input: the task itself, usually one or two sentences. | What to do with each input |

Both blocks are marked **Static**: they are the same for every call of the step. The engine sends them together, the system text first and the instructions after it, as one fixed opening for every call. A step needs something in at least one of the two blocks; a step with neither is reported as **needs a prompt**.

You do not paste the pages or the earlier outputs into the prompt. The engine attaches them to each call. The line under the blocks that begins **Inserted from** says what is attached: **pages**, **outputs** or both, as set by [What each call receives](instructions.md#what-each-call-receives). If the step has references, a second line lists them under **References, whole on every call:**.

Write the prompt so that it is true for every call. A Map step with a window of 4 receives "a small group of consecutive pages", not "the whole file"; say so, and tell the model that other calls handle the neighbouring pages. The ready-made step **Summarize window** in the library is an example.

### The cache tag

Beside **Prompt blocks**, a tag reads **Cache ready** or **Too short to cache**. Because the static part of the prompt is identical for every call of a step, the model endpoint can store it after the first call and read it back cheaply for the rest. Only prompts above a minimum length can be stored. **Too short to cache** is not an error: the calls work, without that saving.

> **Note:** The tag uses the engine's own rule: the whole static prompt, including what the engine adds, measured against the minimum of the step's model, which is higher for some models. It updates a moment after you stop typing. A step whose prompt is long enough is still not cached when it makes too few calls to be worth it. See [Prompt caching](../how-it-works/prompt-caching.md).

## What the engine adds

Each call is built from your prompt and from material the engine supplies. Knowing the order helps you write prompts that fit.

**The fixed opening**, identical for every call of the step:

1. Your **System** text.
2. Your **Instructions** text.
3. One of the following:
   - for a schema output, the output contract: an instruction to reply with one JSON object and nothing else, followed by the schema built from your fields;
   - for a text output with **Track source pages** on, the citation rule: an instruction to cite the page or pages behind each statement in square brackets;
   - for a text output with **Track source pages** off, nothing.

**The material**, different for each call, in this order:

1. The step's references, whole. A reference from a step arrives under that step's name; a reference from a source arrives as the complete file, introduced by its input name.
2. The pages for this call, in the form of their file: a small PDF holding just those pages, an image, or text with each page marked by its number. See [File types](file-types.md).
3. The earlier outputs for this call, each marked with the pages it covers and, in a flow with several sources, with the name of the source those pages come from.
4. A short closing text written by the engine. It says which pages of which file the call was given and how to cite them, says how many earlier outputs a Reduce call was given and to use all of them, and ends by telling the model to follow its instructions.

Which of points 2 and 3 are present depends on [What each call receives](instructions.md#what-each-call-receives).

Two consequences:

- You do not need to explain page numbering or the citation format in your prompt. The engine does.
- In your prompt, refer to a reference by the name of the block it comes from, because that is the name it arrives under.

## Inserting flow inputs

A [value input](value-inputs.md) is a value sent with each run. To use one in a prompt, write its name in double braces, `{{Name}}`, in **System** or **Instructions**.

Under the two blocks, the row **Insert a flow input:** has a button for each input the flow declares. Clicking a button inserts `{{Name}}` at the cursor of the block you last worked in. If you have not clicked into a block yet, it is added at the end of **Instructions**.

- **Manage inputs** shows the flow panel, where inputs are declared.
- When the flow has no inputs, the row reads **No flow inputs yet.** and offers **Add one**, which also shows the flow panel.

When a job is submitted, every `{{Name}}` is replaced by the value for that run before anything is sent to the model. A `{{Name}}` that does not match a declared input is reported as a problem.

## Model

**Model** chooses which model makes this step's calls. The list holds the models configured for this installation. Each step has its own model, so one flow can use a small model for a simple step, such as classifying pages, and a larger one for a demanding step, such as a final summary.

The **Model** tab shows, under the settings, the chosen model's limits (output and input tokens per minute) and its prices per million tokens. Every model has its own quota, shared by all the jobs that use it; see [Queue and priority](../how-it-works/queue-and-priority.md).

## Max output tokens

**Max output tokens** is the most the model may write in one call. A new step has 1500. An empty field or 0 is treated as 1500, and a value below zero is reported as a problem.

- If a reply reaches the limit, it is cut off there. A cut-off text reply is kept and marked as cut off (**cut off at max output** in [View last outputs](#view-last-outputs)). A cut-off schema reply is usually incomplete JSON, so it fails the [schema check](#when-a-reply-does-not-match).
- [Thinking](#thinking) counts against this limit. A step that thinks needs room for the thinking and the reply. If thinking uses the whole limit and no reply text is left, the call counts as an empty reply and the job fails.

Set the limit comfortably above the longest reply you expect. It is a guard against a cut-off reply, not what the scheduler plans with: for planning it uses the expected output, below.

## Expected output tokens per call

**Expected output tokens per call**, on the **Model** tab, is your estimate of how much a typical call of this step writes. Leave it empty to use 60% of **Max output tokens**; the field shows that figure as a placeholder.

It is used in two places:

- the [estimate](../how-it-works/estimates.md) of output tokens and cost in the builder;
- the scheduler, which counts each call that is under way at this size when deciding whether another call fits in the model's quota. See [Quota ledger](../how-it-works/quota-ledger.md).

It only matters at the start. Once the step has made three real calls, the measured average replaces the setting, for the estimate and for the scheduler. The hint under the field then shows **Learned so far:** with the measured figure. What has been learned is kept per step, model and thinking level, so changing the model or the thinking level starts again from the setting.

A realistic first value helps the first run: set too low, the engine may start more calls at once than the quota can take; set too high, it starts fewer than it could.

## Thinking

**Thinking**, on the **Model** tab, sets how much the model reasons before it replies.

| Level | What is requested |
|---|---|
| **Off** | No thinking, in the form the model accepts. This is the setting of a new step. |
| **Low**, **Medium**, **High** | Thinking, with that level of effort. |

Thinking counts against **Max output tokens** and against the model's output quota. Raise **Max output tokens** when you switch it on.

Some models cannot turn thinking off. For such a model, the tab says **This model always thinks. Off sends the lowest effort.** How "off" is expressed for each model is part of the installation's [settings](../operations/settings.md).

A step with thinking on shows the chip **Thinking low**, **Thinking medium** or **Thinking high** on its block.

## Output contract

The **Output contract** says what form the reply takes. It is on the **Prompt** and **Output** tabs.

| Contract | The reply is | Use it when |
|---|---|---|
| **Text** | Plain text. | A person will read the result, or a later step will read it as text. |
| **Schema** | One JSON object with the fields you define. | A [Filter](instructions.md#filter) must read a field, or the result is to be shown as a table. |

Choosing **Schema** on the **Prompt** tab takes you to the **Output** tab, where the fields are defined. The step's block shows **Text out**, or **Schema:** followed by the name of the first field.

### Fields

Each field has a name, a type and a description. **+ Add field** adds one; the cross removes one.

| Part | Notes |
|---|---|
| Name | Spaces become underscores as you type. Field names in one step must differ. |
| Type | See the table below. |
| Description | **What this field holds.** It is passed to the model with the schema, so use it to say exactly what you want in the field. |

| Type | The model must give | Extra setting |
|---|---|---|
| `string` | Text. | |
| `number` | A number. | |
| `boolean` | True or false. | |
| `one of` | Exactly one of the values you list. | **Allowed values, comma separated**. Required. |
| `list` | A list of texts. | |
| `table` | A list of rows. Every row has every column, and each cell is text, a number or empty. | **Columns, comma separated**. Spaces in column names become underscores. |

Every field you define is required in the reply. A schema output needs at least one named field.

**Example.** A step that reads one invoice page could have these fields:

| Name | Type | Setting |
|---|---|---|
| `invoice_number` | `string` | |
| `is_credit_note` | `boolean` | |
| `currency` | `one of` | `EUR, USD, GBP` |
| `lines` | `table` | `description, quantity, unit_price, amount` |

A valid reply is then:

```json
{
  "invoice_number": "INV-2041",
  "is_credit_note": false,
  "currency": "EUR",
  "lines": [
    {"description": "Monitor arm", "quantity": 4, "unit_price": 62.5, "amount": 250}
  ]
}
```

A later Filter could keep the pages where `is_credit_note` `is false`. An output set to **Table** shows one row per line, with `invoice_number`, `is_credit_note` and `currency` repeated on each row and a first column for the page; see [Results screen](results-screen.md).

### When a reply does not match

The engine checks every reply of a schema step against the schema. It accepts a reply that wraps the JSON in a code fence or adds a stray sentence around it. If the reply holds no JSON object, lacks a field, or has a value of the wrong type or outside the allowed values, the reply is invalid and the call is made again.

A call is tried a limited number of times (`worker.max_transient_attempts`, 3 by default, counting the first). If the last try is still invalid, the job fails, and its error begins **Invalid reply** and says what did not match. A reply that was cut off at **Max output tokens** is not tried again, since it would be cut off again: the job fails at once and the error says to raise the limit. Each try is a real call and is charged. See [Failures and recovery](../how-it-works/failures-and-recovery.md).

If a step's replies are often invalid, make the field descriptions more exact, reduce the number of fields, or raise **Max output tokens** in case the JSON is being cut off.

> **Screenshot to add:** `images/builder-step-output-tab.png`. A step selected with the right-hand panel on the Output tab: Output contract set to Schema, three fields of different types including a "one of" field with its allowed values and a "table" field with its columns, the + Add field button, and the Track source pages switch.

## Track source pages

**Track source pages** is a switch on the **Prompt** and **Output** tabs, described there as **Every output knows which pages it covers**. It is on for a new step.

When it is on and the step has a **Text** output, the engine adds the citation rule to the prompt: after each finding, the model is to cite the page or pages it comes from in square brackets, such as `[p. 12]` or `[pp. 12-14]`, and never to cite a page it was not shown. In a flow with [several sources](several-files.md), the citation includes the input name, such as `[Invoice p. 2]`. On the [Results screen](results-screen.md), each citation is a link that opens that page beside the text.

Two things to know:

- The engine records which pages each call was given whether the switch is on or off. Every item carries its pages through Map, Reduce and Filter, and a table output has a page column. The switch only controls the citation rule in the prompt.
- For a step with a **Schema** output, the citation rule is not added, whatever the switch says: the reply must be the JSON object and nothing else.

Switch it off for a text step whose output should carry no bracketed citations, for example when a later step would only be confused by them.

## Test this step

**Test this step** runs the flow up to and including one step, then stops. Use it to try a prompt without paying for the steps after it.

Start it from the button at the bottom of the step's panel, from the step's right-click menu, or by pressing `T` with the step selected. A dialog titled **Test "**_step name_**"** opens. It asks for:

- a file for each source the step depends on, directly or through earlier steps and references, and no others;
- a value for each value input that this step, or a step before it, uses;
- a **Priority**, **Interactive** or **Bulk**.

It shows the estimate for this partial run. **Start** submits the job and opens the [Run screen](run-screen.md). The job is labelled **Step test:** followed by the step's name, and the tested step's results appear under an output named after the step.

A step test runs every step the tested step depends on, so testing the third step of a chain runs the first two as well. Unlike **Test run**, it does not require the rest of the flow to be free of problems: only the part being run must be valid. See [Test runs](test-runs.md).

## View last outputs

**View last outputs**, in a step's right-click menu, shows what the step produced the last time it ran, without leaving the builder. Use it to check the effect of a prompt change after a test.

The dialog **Last outputs of** _step name_ shows up to 60 outputs from the most recent run of this flow in which the step completed a call. Each is headed by the pages it covers and the number of output tokens, with **cut off at max output** when the reply hit the limit. A text output is shown as text, a schema output as JSON. **Open that run** goes to the run they come from.

If the step has not run yet, the dialog says so. Outputs belong to the step in this flow: a duplicated step, or a step in a duplicated flow, starts with none.

## See also

- [Instructions](instructions.md): how a step is applied to its input, and what each call receives.
- [Value inputs](value-inputs.md): declaring the values that `{{Name}}` stands for.
- [Several files in one flow](several-files.md): references, and citations that carry an input name.
- [Test runs](test-runs.md): running the whole flow or one step.
- [Prompt caching](../how-it-works/prompt-caching.md): why the static part of a prompt is cheap after the first call.
