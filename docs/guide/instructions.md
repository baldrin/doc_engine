[Documentation](../README.md) › [User guide](README.md) › Instructions

# Instructions

An instruction says how a step is applied to what arrives on its connection. This page explains the three instructions that are built, Map, Reduce and Filter, with worked examples, and Fold, which is shown in the library but not built. It is for anyone who designs flows.

**On this page**

- [Items, and where instructions live](#items-and-where-instructions-live)
- [Map](#map)
- [Reduce](#reduce)
- [Filter](#filter)
- [What each call receives](#what-each-call-receives)
- [Fold](#fold)
- [Choosing an instruction](#choosing-an-instruction)

## Items, and where instructions live

A step does not receive a file. It receives **items**. An [item](../glossary.md#item) is anything a step can consume:

- from a source, each page of the file is one item (a page of a file is also called a [unit](../glossary.md#unit));
- from another step, each output of that step is one item. An item made by a step remembers which pages of the file it covers.

The instruction decides how the items are grouped into calls. Every call is one request to the model, and every call produces one new item.

| Instruction | Calls | Items out |
|---|---|---|
| **Map** | One per window of consecutive items | One per window |
| **Reduce** | One, over all the items | Exactly one |
| **Filter** | One per item that matches the rule | One per kept item |

An instruction belongs to the connection into a step, not to the step. To set it, select the step or the connection and use the **Instruction** control on the step's **Input** tab, or click the instruction in the library. A new connection from a source starts as Map; a new connection from a step starts as Reduce. Only the connection a step works through has an instruction: a [reference](several-files.md#references) has none.

> **Screenshot to add:** `images/builder-instruction-labels.png`. The canvas of the sample flow "Medical record summary" showing all three instruction labels on its connections: "Map 4 / 1", "Reduce", "Map 1 / 0" and the dashed "Filter" connection with its rule value.

## Map

Map makes one call per **window** of consecutive items. Use it to do the same work on every part of a file: note what each group of pages says, classify each page, extract from each page.

Map has two settings, on the step's **Input** tab:

| Setting | Meaning | Allowed values |
|---|---|---|
| **Window size** | How many consecutive items each call receives. | 1 or more |
| **Overlap** | How many items at the end of one window are repeated at the start of the next. | 0 or more, and smaller than the window size |

The label on the connection shows both, as **Map 4 / 1**: window size 4, overlap 1.

### How windows are formed

The first window starts at the first item. Each following window starts *window size minus overlap* items after the one before. The last window ends at the last item and may be shorter than the others.

**Example 1: 24 pages, window 4, overlap 1.** Each window starts 3 pages after the one before.

| Call | Pages |
|---|---|
| 1 | 1 to 4 |
| 2 | 4 to 7 |
| 3 | 7 to 10 |
| 4 | 10 to 13 |
| 5 | 13 to 16 |
| 6 | 16 to 19 |
| 7 | 19 to 22 |
| 8 | 22 to 24 |

Eight calls. Pages 4, 7, 10 and so on are read twice, once at the end of a window and once at the start of the next.

**Example 2: the same settings on other files.**

| Pages | Window / overlap | Calls | Last window |
|---|---|---|---|
| 150 | 4 / 1 | 50 | 148 to 150 |
| 60 | 3 / 1 | 30 | 59 to 60 |
| 10 | 4 / 0 | 3 | 9 to 10 |
| 24 | 1 / 0 | 24 | 24 |
| 3 | 4 / 1 | 1 | 1 to 3 |

For a file with more items than the window size, the number of calls is 1, plus the remaining items (items minus window size) divided by the distance between windows (window size minus overlap), rounded up. For 150 pages at 4 / 1: 146 divided by 3 is 48.7, rounded up to 49, plus 1 is 50.

### Why overlap

With no overlap, something that runs across the boundary between two windows, such as a table that continues on the next page, is seen by no call in one piece. With an overlap of 1, the boundary page is in both windows. The price is that the overlapping pages are sent, and paid for, twice.

### What a short file does

A file with no more items than the window size fits in one window, so Map makes one call. A one-page file, such as an image, always makes exactly one call, whatever the window size and overlap.

The builder takes this into account:

- When you connect a source whose chosen file has one page, the connection starts as **Map 1 / 0**. Otherwise it starts as **Map 4 / 1**.
- When the chosen file fits in one window and the window size is above 1, the **Input** tab says so: the two settings change nothing for this file, and apply when the flow runs on a longer file.

Keep the second point in mind when you test on a short file a flow that is meant for long ones.

### Map over the outputs of a step

Map works the same way when the items come from a step. A window is then a group of consecutive outputs. With 50 sets of notes and Map 10 / 0, a step makes 5 calls, each receiving 10 sets of notes. Each new item covers all the pages its window's items covered.

## Reduce

Reduce makes exactly one call, which receives every item at once, and produces exactly one item. Use it to combine: turn all the notes into one summary, or all the page checks into one verdict.

Reduce has no settings. The label on the connection reads **Reduce**, with the number of items going in, for example `8 → 1 item`.

**Example: a summary of a 150-page file.** The sample flow **Medical record summary** uses Map then Reduce:

| Step | Instruction | Items in | Calls | Items out |
|---|---|---|---|---|
| Summarize window | Map 4 / 1 | 150 pages | 50 | 50 sets of notes |
| Final summary | Reduce | 50 sets of notes | 1 | 1 summary |

The single Reduce call is told how many earlier outputs it was given and to use all of them. Each earlier output arrives marked with the pages it covers, so the combined result can still cite pages.

Three things to know:

- **Reduce straight from a source** sends every page of the file in one call. That is how the sample flow **Compare two medication lists** reads a two-page list. It suits short files only: a request larger than the configured limit (`gateway.max_request_mb`, 16 MB by default) is not sent, and the job fails with a message that gives the size and says to use a smaller window. See [Limits](../operations/limits.md).
- **The one call must hold everything.** All the items go into one request, so the more items and the longer each one, the larger the call. Keeping the earlier step's outputs short keeps the Reduce call small.
- **Nothing in, nothing out.** If no items arrive, for example because a Filter earlier in the flow kept nothing, Reduce makes no call and passes nothing on.

## Filter

Filter keeps the items whose earlier output matches a rule, then makes one call per kept item. Use it to spend calls only where they are needed: classify every page with a small, cheap step, then run the careful step only on the pages of one type.

A Filter reads a field from the output of the step before it. So:

- a Filter is only possible on a connection that comes from a step, not from a source;
- that step must have a [schema output](steps.md#output-contract), because a rule needs a named field to read.

The label on the connection reads **Filter**, and the line is dashed.

### The rule

Set the rule on the step's **Input** tab, under **Keep items where**. A rule has three parts:

| Part | What to choose |
|---|---|
| Field | One of the fields of the earlier step's schema output. |
| Comparison | One of the eight comparisons below. |
| Value | What to compare the field with. When the field is a `one of` field, the value is chosen from its allowed values. Not needed for `is true` and `is false`. |

The value can also be a [value input](value-inputs.md), so that it is set for each run: use the buttons under **Or compare with a flow input:**, or choose an entry under **Sent with each run** in the list of values. The value then reads `{{Name}}`.

### The comparisons

| Comparison | Keeps the item when |
|---|---|
| `equals` | The field has a value and it is the same as the rule's value. |
| `not equals` | The field is different from the rule's value, or has no value. |
| `in` | The field equals one of several values. Write the values separated by commas. |
| `contains` | For a list field: one of its entries equals the value. For any other field: the value appears somewhere in the field's text. |
| `is true` | The field is true. |
| `is false` | The field is false. |
| `greater than` | The field, read as a number, is above the value. |
| `less than` | The field, read as a number, is below the value. |

Text is compared without regard to upper and lower case, and without spaces at the start and end. `yes` and `true` count as the same, as do `no` and `false`, on either side. `greater than` and `less than` keep nothing when either side is not a number. An item whose earlier output has no fields at all is never kept.

### What is passed on

Each kept item becomes one call. There are no windows: a Filter never groups items.

What the call receives is set by **What each call receives**. For a Filter it starts as **Their pages**: the step receives the pages that the kept item covers, not the earlier output. This fits the usual pattern, in which the earlier step only decides *whether* a page is of interest, and the filtered step then reads the page itself. Choose **Earlier outputs** or **Both** to change that; see [What each call receives](#what-each-call-receives).

If no item matches, the step makes no call and finishes at once with nothing to pass on. The job carries on, and anything after the step receives no items.

### Worked example

The sample flow **Medical record summary** has this branch, here on the 150-page sample:

| Step | Instruction | Items in | Calls | Items out |
|---|---|---|---|---|
| Classify page | Map 1 / 0 | 150 pages | 150 | 150 classifications, each with a `page_type` |
| Extract lab values | Filter: `page_type` equals `lab report` | 150 classifications | one per page classified as a lab report | one per call |

Suppose the classifier answers `lab report` for 21 of the 150 pages. The Filter keeps those 21 items, and **Extract lab values** makes 21 calls, each receiving one of those pages. The other 129 pages cost one small classification call each and nothing more.

### The estimate for a Filter

How many items a Filter keeps is only known once the earlier step has answered. Until the flow has run once, the estimate assumes a quarter of the items are kept (at least one), and marks the number with `~`: for 150 items, `150 → ~38`. The flow panel then shows **A filter's share is assumed to be 25% until the flow has run once.** After a run, the estimate uses the share that was kept in the most recent run of that flow.

> **Screenshot to add:** `images/builder-filter-input-tab.png`. The step "Extract lab values" of the sample flow selected, with the Input tab showing Instruction set to Filter, the rule "page_type equals lab report" under Keep items where, and What each call receives set to Their pages.

## What each call receives

When a step's input comes from another step, its **Input** tab has the control **What each call receives**:

| Choice | The call receives | Starts as the choice for |
|---|---|---|
| **Earlier outputs** | What the earlier step produced for the items in this call, each marked with the pages it covers. | Map and Reduce |
| **Their pages** | The pages of the file that those items cover, and not the earlier outputs. | Filter |
| **Both** | The pages and the earlier outputs. | |

Changing the instruction sets the control back to the instruction's starting choice.

When a step's input is a source, there is no choice to make: the step reads pages straight from the file.

**Example.** A step classifies windows of 4 pages, and the next step uses Reduce with **Their pages**. The Reduce call receives every page that the classified items cover, which is the whole file, in one request. With **Earlier outputs** it would receive only the classifications. Pages are much larger than notes about them, so choose **Their pages** or **Both** only when the step really needs to see the pages again.

The step's **Prompt** tab shows the result of this choice in the line that begins **Inserted from**: **pages**, **outputs**, or both.

## Fold

Fold appears in the library with the description **Each call gets the last output** and the mark **Soon**. It is designed but not built: it cannot be selected, and a flow cannot use it. Use Map or Reduce.

## Choosing an instruction

| You want to | Use |
|---|---|
| Do the same thing to every page, or every few pages | Map |
| Classify or extract from single pages | Map with window 1 and overlap 0 |
| Combine many results into one | Reduce |
| Read a short file whole in one call | Reduce straight from the source |
| Run a step only on pages of a certain kind | A classifying step with a schema output, then Filter |
| Summarize a long file | Map to take notes, then Reduce to combine them |

## See also

- [Steps](steps.md): the settings of the step an instruction feeds, including the schema output a Filter reads.
- [Flow builder](builder.md#the-input-tab): where the instruction and its settings are on the screen.
- [Several files in one flow](several-files.md): references, the connections that have no instruction.
- [Value inputs](value-inputs.md): using a value sent with each run as a Filter's value.
- [Jobs and tasks](../how-it-works/jobs-and-tasks.md): how the engine turns instructions into calls while a job runs.
