[Documentation](../README.md) › [User guide](README.md) › Value inputs

# Value inputs

A value input is a small value that is sent with the files of a run: a number, a choice, a yes or no, a short text, or a piece of JSON. It lets one flow behave differently from run to run without being edited. This page explains how to declare inputs, how to use them in prompts and filter rules, what happens to them when a job is submitted, and when a run is refused. It is for flow builders, and for anyone who runs a flow that has inputs.

**On this page**

- [What a value input is for](#what-a-value-input-is-for)
- [Declaring an input](#declaring-an-input)
- [Types](#types)
- [Defaults and required inputs](#defaults-and-required-inputs)
- [Using an input in a prompt](#using-an-input-in-a-prompt)
- [Using an input in a filter rule](#using-an-input-in-a-filter-rule)
- [Renaming and removing](#renaming-and-removing)
- [What happens at run time](#what-happens-at-run-time)
- [When a run is refused](#when-a-run-is-refused)
- [Limits and cautions](#limits-and-cautions)

> **Not yet confirmed:** Value inputs have run only against the fake gateway. That the values reach the prompt is tested; whether a real model acts on them as intended has not been checked, and is part of the first session against the real gateway.

## What a value input is for

Suppose a flow checks invoice prices against an order. How large a price difference is acceptable is not a property of the flow; it differs by customer or by day. Declare it as an input named `Price tolerance`, write `{{Price tolerance}}` in the prompt, and each run supplies its own number.

The sample flow **Check an invoice against its order** does exactly this. It declares two inputs:

| Name | Type | Default | Description |
|---|---|---|---|
| `Price tolerance` | Number | 0.5 | Largest unit price difference that still counts as agreeing with the order |
| `Accept delivery charges` | Yes / no | no | Let a delivery charge pass when the order did not list one |

Value inputs are for small values. Content of any length belongs in a file, as a [source](several-files.md).

## Declaring an input

Inputs belong to the flow, not to a step. They are declared in the [flow builder](builder.md), in the right-hand panel when nothing is selected.

1. Click an empty part of the canvas so that nothing is selected. The right-hand panel shows the flow panel, with the section **Inputs**.
2. Choose **Add an input**. A new input appears, named **Input 1**, of type **Text**, with no default.
3. Replace the name. Press Enter or click elsewhere to confirm it.
4. Choose the **Type**.
5. For a **Choice** input, type the choices, separated by commas.
6. Set a **Default**, or leave it empty to make the input required.
7. Write a description. It is shown to the person running the flow, under the field where they give the value.

| Field | Notes |
|---|---|
| Name | How the input is referred to everywhere: in prompts as `{{Name}}`, in the **Test run** dialog, and by callers of the [API](../api/README.md). Braces are removed from a name as it is confirmed. Two inputs cannot share a name; names that differ only in upper and lower case or in spacing count as the same. |
| **Type** | See [Types](#types). Changing the type clears the default. |
| Choices | Choice inputs only. At least one is needed. |
| **Default** | See [Defaults and required inputs](#defaults-and-required-inputs). |
| Description | Placeholder: **What it is for (shown to the person running the flow)**. |

Under each input, a note says **No default: every run must supply it.** or **Used when a run does not supply it.** If no prompt or rule uses the input yet, the note adds **Not used by any step yet.**

From a step's **Prompt** tab, **Manage inputs** (or **Add one**, when the flow has none) brings you to this panel.

> **Screenshot to add:** `images/builder-inputs-two-types.png`. The sample flow "Check an invoice against its order" with nothing selected: the right-hand flow panel showing the Inputs section with "Price tolerance" (Type Number, Default 0.5) and "Accept delivery charges" (Type Yes / no, Default No), each with its description and note.

## Types

| Type | Accepts | Written into the prompt as |
|---|---|---|
| **Text** | Any text, up to 20,000 characters. | The text as sent. |
| **Number** | A number, or text that reads as one. Thousands commas are removed, so `1,250` is 1250. | The number. A whole number is written without a decimal point: `10`, not `10.0`. |
| **Choice** | One of the choices listed for the input. Upper and lower case and spacing do not matter when matching. | The choice as it is spelled in the list. |
| **Yes / no** | Yes or no. From code, `true` and `false`, `yes` and `no`, `y` and `n`, `1` and `0` are all accepted. | `yes` or `no`. |
| **JSON** | Any valid JSON, up to 20,000 characters: an object, a list, or a single value. | The JSON on one line. |

The field for a JSON input warns **This is not valid JSON yet.** while what you have typed does not parse.

## Defaults and required inputs

An input either has a default or is required.

- **With a default.** A run that does not supply the input uses the default. A run can still supply its own value.
- **Without a default.** Every run must supply the input. A run that does not is refused.

To clear a default, empty the **Default** field; for a choice or a yes/no input, choose **None**.

A default must be valid for the input's type: a number for a number input, one of the choices for a choice input. The builder reports an invalid default as a problem.

Where a value is asked for, each input is marked with its default, as **Default: 0.5**, or with **Required**.

## Using an input in a prompt

Write the input's name in double braces in a step's **System** or **Instructions** block:

```text
Treat a unit price as agreeing with the order when it differs by no more than {{Price tolerance}}.
```

The quickest way is the row **Insert a flow input:** on the step's **Prompt** tab. It has one button per input; clicking a button inserts `{{Name}}` at the cursor. See [Steps](steps.md#inserting-flow-inputs).

Rules for the placeholder:

- Upper and lower case and spacing do not matter: `{{price tolerance}}` and `{{ Price  tolerance }}` both mean the input `Price tolerance`.
- A placeholder must be on one line.
- The same input can be used any number of times, in any number of steps.
- A `{{Name}}` that matches no declared input is a problem. The builder names the step and tells you to add the input under **Inputs**.

The model sees only the value, with no label. Write the sentence around the placeholder so that it makes sense once the value is in place. For a yes/no input, the value is the word `yes` or `no`, so a sentence such as *"Accept delivery charges the order did not list: {{Accept delivery charges}}. When this is no, report any such charge; when it is yes, let it pass."* reads correctly either way.

## Using an input in a filter rule

The value of a [Filter](instructions.md#filter) rule can be an input, so that each run decides what is kept.

On the step's **Input** tab, with the instruction set to **Filter**:

- under the rule, **Or compare with a flow input:** has a button for each input; clicking one sets the rule's value to `{{Name}}`;
- when the rule's field is a `one of` field, the list of values has a group **Sent with each run**, with an entry **Input:** _name_ for each input.

**Example.** A classifying step outputs `page_type`. Declare a choice input `Page type to extract` with the same choices as the field's allowed values, and set the rule to `page_type` `equals` `{{Page type to extract}}`. One run can then extract the lab reports and another the letters, from the same flow.

Rule values are compared without regard to upper and lower case, and `yes`/`no` match `true`/`false`, so a yes/no input can be compared with a `boolean` field.

## Renaming and removing

**Renaming.** When you rename an input in the **Inputs** editor, the builder renames it everywhere it is written: in the **System** and **Instructions** blocks of every step and in filter rule values. You do not need to edit the prompts by hand. Callers of the API send values by name, so after renaming an input of a published flow and publishing again, they must use the new name.

**Removing.** The cross beside an input's name removes it. Placeholders that used it are left in the prompts, and are then reported as problems until you remove them or declare the input again.

## What happens at run time

Values are settled once, when the job is submitted.

1. For each declared input, the engine takes the value that was sent, or, if none was sent, the default. An empty value counts as not sent.
2. Each value is checked against its type.
3. If anything is wrong, the run is refused and no job is created.
4. Otherwise the job gets its own copy of the flow, in which every `{{Name}}`, in prompts and in rule values, has been replaced by its value.

From then on, the job works from that copy. Nothing later in the run sees a placeholder, and editing the flow or its defaults does not affect a job that has already been submitted. The job records the values it ran with, and the [Results screen](results-screen.md) shows them.

### Giving values in a test run

When a flow has inputs, the **Test run** dialog has a **Values** section with one field per input. Each field shows the input's name, its default or **Required**, and its description.

- Leave a field empty to use the default.
- **Start** is unavailable until every required input has a value; pointing at it shows which ones are missing.
- The values you enter are remembered in your browser for that flow, so the next test run starts with them filled in.

[Test this step](steps.md#test-this-step) asks only for the inputs used by the tested step and the steps before it. The [Activity screen](activity-screen.md) asks for values in the same way when you submit jobs from there.

From code, values are sent as one object named `values`, for example `{"Price tolerance": 10, "Accept delivery charges": true}`. See the [API](../api/README.md).

> **Screenshot to add:** `images/builder-test-run-values.png`. The Test run dialog for the sample flow "Check an invoice against its order": three file lists, then the Values section with "Price tolerance" marked "Default: 0.5" and "Accept delivery charges" as Yes and No buttons marked "Default: no", each with its description.

## When a run is refused

A run is refused, before any job exists and before anything is charged, in these cases. Every message names the input, and all the problems of one request are reported together.

| Case | Message |
|---|---|
| A required input was not supplied | `Input "Name" is required and has no default.` |
| The value is not of the input's type | `Input "Name" must be a number.` Likewise `text`, `yes or no`, `JSON`. |
| A choice is not on the list | `Input "Name" must be one of:` followed by the choices. |
| A JSON value does not parse | `Input "Name" is not valid JSON.` |
| A text or JSON value is too long | `Input "Name" is longer than 20,000 characters. Send long content as a file.` |
| A value was sent that the flow does not declare | `This flow has no input named "Name".` |

The last case catches misspelled names: a value sent under the wrong name is not silently ignored.

## Limits and cautions

| Limit | Value |
|---|---|
| Length of a text or JSON value | 20,000 characters (the setting `worker.max_value_chars`) |
| Where a placeholder works | A step's **System** and **Instructions** blocks, and the value of a filter rule. Not in block names or field descriptions. |
| Characters in a name | No braces. |
| Types | Text, Number, Choice, Yes / no, JSON. |

- **A value is written into the prompt exactly as it was sent.** Whoever can submit a run can therefore change what the step is told, within that one run. Where the possible values are known, use a **Choice** input, not **Text**; it accepts only the listed values.
- **A value changes the prompt.** Because the value is part of the step's fixed opening, runs with different values do not share a stored prompt. See [Prompt caching](../how-it-works/prompt-caching.md).
- **An unused input is a warning, not a problem.** The flow still runs; the input simply has no effect.

## See also

- [Steps](steps.md): the prompt blocks that placeholders go into.
- [Instructions](instructions.md): filter rules, where an input can be the value to compare with.
- [Test runs](test-runs.md): giving values when you run a flow from the builder.
- [API](../api/README.md): sending values from code.
- [Settings](../operations/settings.md): changing the length limit.
