[Documentation](../README.md) › [User guide](README.md) › The Results screen

# The Results screen

The Results screen shows what a job produced: each output of the flow, as text or as a table, with page
references that open the page they point at beside the result. This page explains how to read the outputs,
how to check them against the files, and how to take them away. It is for anyone who reads or reviews results.

**On this page**

- [Open the results](#open-the-results)
- [The top bar](#the-top-bar)
- [Ran with: the values of the run](#ran-with-the-values-of-the-run)
- [Outputs](#outputs)
- [Text outputs](#text-outputs)
- [Table outputs](#table-outputs)
- [Page references](#page-references)
- [The page viewer](#the-page-viewer)
- [Truncated output](#truncated-output)
- [Download an output](#download-an-output)

> **Screenshot to add:** `images/results-screen-overview.png`. Results of "Medical record summary": the output tabs, the "Summary with citations" output as text with several page references, one reference selected, and the page viewer open at the right showing that PDF page.

## Open the results

On the [Run screen](run-screen.md) of a complete run, select **View results** in the top bar, or **Results**
on the card that appears when the run ends. To reach an older run, find it on the
[Activity screen](activity-screen.md), select its row, and go on from its Run screen.

While the page loads it reads **Loading results…**.

Results are offered for complete runs. If the screen is opened for a run that is not complete, a notice at the
top says so, for example **This run is failed. Results shown here may be incomplete.**, and whatever outputs
had finished are shown.

## The top bar

| Part | Meaning |
|---|---|
| The trail above the title | **Activity** (a link to the [Activity screen](activity-screen.md)), then the job's label, such as **Test run** (a link to its [Run screen](run-screen.md)), then **Results**. |
| The title | The name of the file the job read. For a job on several files, the names of the flow's inputs, such as **Purchase order, Delivery note, Invoice**; hover to read the file names. |
| The tag beside the title | The flow's name and the version the job was started from, for example **Medical record summary · v1**. |
| **Back to the run** | Opens the [Run screen](run-screen.md) of this job, wherever you came from. |

## Ran with: the values of the run

When the flow declares [value inputs](value-inputs.md), a line that starts **Ran with** lists every input and
the value this job used, for example **Price tolerance: 10** and **Accept delivery charges: yes**.

The line shows all the flow's inputs, not only those that were filled in: an input that was left empty appears
with its default, because that is the value the job ran with. Yes / no values read **yes** or **no**. A long
value is cut short on screen; hover over it to read it in full.

These values were fixed when the job was submitted. Two jobs on the same files can differ only in this line,
so read it before comparing their results. A flow without value inputs has no **Ran with** line.

## Outputs

A flow has one or more output blocks, and each is one output here.

- With one output, it is shown directly.
- With several, a row of tabs appears, one per output, named after the output blocks and in the order the
  blocks are drawn in the flow from top to bottom. Select a tab to read that output.

Under the tabs is the output's name as a heading and, at the right, its
[download buttons](#download-an-output). The output then appears in one of two forms, which is set on the
output block in the [builder](builder.md): text or table.

An output that received nothing reads **This output is empty. No items reached it.** This happens, for
instance, when a [Filter](instructions.md) before it kept no pages.

A run started with **Test this step** has a single output, named after the tested step followed by **output**.
See [Test a single step](test-runs.md#test-a-single-step).

## Text outputs

A text output shows what the step feeding it wrote, laid out for reading: headings, bulleted and numbered
lists, paragraphs and bold text. A short line that stands alone as a title is shown as a heading too.

### One item or several

What you see depends on the step that feeds the output.

- A step that makes one call, such as a [Reduce](instructions.md) that merges everything into a summary,
  gives one item. It is shown as one continuous text.
- A step that makes many calls, such as a [Map](instructions.md) over [windows](../glossary.md#window) of
  pages, gives one item per call. The items are shown one after another, in the order of the pages. Each
  starts with a line saying which pages it covers, such as **Pages 1 to 4**, or **Pages 3, 7** for pages that
  do not follow on.

When a flow has [several sources](several-files.md), that line also names the input the pages belong to, such
as **Invoice · pages 2**.

### Items without text

If a step returns a schema and its output is set to the text form, each item is shown as the data the step
returned, in JSON, exactly as stored.

## Table outputs

A table output gathers the data of every item into one table. It is the natural form for a step that returns
a schema, such as the sample **Lab results table**.

> **Screenshot to add:** `images/results-screen-table.png`. The "Lab results table" output of "Medical record summary" in table form, with the page column of reference buttons at the left and the CSV button above.

### Columns

| Column | Content |
|---|---|
| **page** | Always first. The page or pages the row came from, as a [page reference](#page-references) you can select. |
| The columns of a table field | When the step's schema has a field of type table, each of its columns becomes a column here. |
| The other fields | Each remaining field of the schema becomes a column, in the order of the schema. |

Underscores in field names are shown as spaces: a field named `unit_price` is headed **unit price**.

### Rows

- When the step returns a table field, every row of that table is a row here. The step's other fields are
  repeated on each of those rows. In **Lab results table**, for example, each test result is a row, and the
  collection date of its page is repeated beside it.
- When the step returns no table field, each item is one row.

Rows are in the order of the pages. An empty cell means the step returned nothing for that field.

If a table output has no rows to show because the step returned text, not data, the items are shown in the
text form instead.

## Page references

A page reference is a small button in the result, such as **p. 12**, that points at the page a statement came
from. Select it to open that page in the [page viewer](#the-page-viewer). The reference you last selected
stays highlighted. Hovering over a reference shows what it will open, including the file's name.

As the line under each output says: **Select a page reference to see that page of the file beside the text.**

### Where references come from

- In text, the model writes them. A step that tracks pages is told to cite its pages, and Document Engine
  turns each citation it recognizes into a button. It recognizes square brackets holding a page or a range:
  `[p. 12]`, `[pp. 12-14]`, `[page 3]`, and several pages in one bracket such as `[pp. 3, 7]`.
- In a table, the **page** column is filled in by Document Engine from the pages each call was given. It does
  not depend on what the model wrote.

A reference to a range, such as **p. 12–14**, opens the first page of the range. Use **Next** in the viewer to
read on.

### Input names, when a flow has several sources

When a flow reads several files, a page number alone does not say which file is meant. References then carry
the name of the input, which is the name on the source block: **Invoice p. 2**, **Purchase order p. 1**.
Selecting one opens that page of the file that was given to that input.

- In text, the model writes the name inside the brackets, as in `[Invoice p. 2]`. Document Engine matches it
  to an input by the input's name or by the file's name, without regard to capitals.
- If a reference names no input, or a name Document Engine does not recognize, it is taken to mean the input
  that the item itself was working through, and is shown with that input's name.
- In a table, the **page** cell shows the input's name before the page.

In a flow with one source, references show the page only.

> **Not yet confirmed:** references written in text depend on the model writing them in a recognized form,
> with the right input name. This codebase has run only against the fake gateway, which is not a real model.
> Whether a real model does so reliably, in particular with several sources, will be checked in the first
> session against the real gateway. A citation in another form stays in the text as
> the model wrote it and cannot be selected.

A page reference shows where the model says a statement came from. It is an aid to checking, not a proof: open
the page and read it.

## The page viewer

Selecting a page reference opens the viewer at the right of the results, so the page and the statement can be
read side by side.

| Part | Meaning |
|---|---|
| The heading | The file's name and the page number. With several sources, the input's name comes first: **Invoice · Invoice.pdf · page 2**. |
| **Previous** | Shows the page before. Greyed out on page 1. |
| **Next** | Shows the page after. Greyed out on the file's last page. |
| The close button | Closes the viewer. |

**Previous** and **Next** stay within the file being shown. To look at another file of the same job, select a
reference to that file.

What the viewer shows depends on the [type of the file](file-types.md):

| File | What is shown |
|---|---|
| PDF | That page of the PDF, fitted to the width of the viewer. |
| Image | The image. An image has one page. |
| Text | That page of the text, in a fixed-width typeface with its line breaks kept. It reads **Loading…** while the page is fetched. |

For a text file, a page is the unit the file was divided into when it was uploaded, so page numbers here match
the page numbers the steps worked with.

If the file was [removed](files-screen.md#remove-a-file) after the run, the results remain but the viewer can
no longer show its pages. For a text file it reads **This page could not be loaded.**

## Truncated output

Every step has a maximum output, set in the builder. A reply that reaches it is cut off there. Document Engine
keeps what was written and marks the item, in a text output, with this notice above it:

**This output was cut off at the step's max output. Raise it and run again for the full text.**

Treat a marked item as incomplete: the end of the text is missing, and with it possibly findings and page
references. To get the whole text, open the step in the [builder](builder.md), raise its maximum output (see
[Steps](steps.md)), and run the flow again. The same event is reported on the Run screen while the job runs,
as a **cut off at max output** line in the [Live events](run-screen.md#live-events) feed.

A table output has its own notice, above the table, when a reply behind it was cut off:

**At least one reply behind this table was cut off at the step's max output tokens, so rows may be missing. Raise it and run again.**

The rows themselves carry no mark.

## Download an output

Two buttons at the right of the output's heading save the output you are looking at to your computer. Which
ones appear depends on what the output holds.

| Button | Shown when | What you get |
|---|---|---|
| **CSV** | The output is shown in table form. | A file named after the output, ending in `.csv`. The first line holds the column names as the step's schema spells them, **page** first. Every value is in double quotes. With several sources, the page value includes the input's name. |
| **Text** | At least one item of the output has text. | A file named after the output, ending in `.md`. It holds the text of every item, one after another with a blank line between, exactly as the model wrote it, so page references appear in their bracketed form. |

Each button saves one output. For a flow with several outputs, open each tab and download it in turn.

There is no button that copies an output to the clipboard. To copy part of a result, select the text on the
page and copy it in the usual way.

## See also

- [The Run screen](run-screen.md): where the results are opened from, and the run's record.
- [Several files in one flow](several-files.md): inputs, references, and why page references carry names.
- [Value inputs](value-inputs.md): the values shown under **Ran with**.
- [Steps](steps.md): the output type, page tracking and maximum output of a step.
- [The Files screen](files-screen.md): what removing a file does to the page viewer.
