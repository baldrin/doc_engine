[Documentation](../README.md) › [User guide](README.md) › Start a test run

# Start a test run

A test run runs the flow you are building once, on files you choose, and shows it working live. This page
describes the **Test run** dialog and every field in it, how to test a single step, and what happens when
something is missing. It is for anyone building a flow in the [builder](builder.md).

**On this page**

- [What a test run is](#what-a-test-run-is)
- [Open the dialog](#open-the-dialog)
- [The fields of the dialog](#the-fields-of-the-dialog)
- [Start the run](#start-the-run)
- [Test a single step](#test-a-single-step)
- [When something is missing](#when-something-is-missing)
- [Where the run goes next](#where-the-run-goes-next)

## What a test run is

A test run is an ordinary [job](../glossary.md#job). It goes through the same scheduler as every other job,
shares the same quota, and makes real model calls that are paid for. What makes it a test is only where it is
started: from the builder, on the flow exactly as it is on your canvas at that moment, saved version or not.

To start several jobs at once, use the **Submit jobs** form on the [Activity screen](activity-screen.md)
instead.

## Open the dialog

Select **Test run** in the builder's top bar.

The button is greyed out in two cases, and its tooltip says which:

| Tooltip | What to do |
|---|---|
| **Fix the problems first** | The flow has errors. Open the list of problems in the builder and fix them. |
| **Choose a file for every source first** | At least one source block has no file. Choose one on the block. |

> **Screenshot to add:** `images/test-runs-dialog.png`. The Test run dialog for the sample flow "Check an invoice against its order": three file fields named after the sources, the Values section with Price tolerance and Accept delivery charges, Priority on Interactive, and the estimate line filled in.

## The fields of the dialog

From top to bottom:

| Field | What it is |
|---|---|
| One file field per source | The file each source reads in this run. |
| **Upload file** | Beside each file field: adds a file of your own and chooses it. |
| **Values** | One field per value input the flow declares. Not shown when the flow declares none. |
| **Priority** | **Interactive** or **Bulk**. |
| **This run:** | The estimate: calls, output tokens and cost. |
| **Cancel** and **Start** | Close the dialog, or start the run. |

The line under the title says what will happen: the whole flow runs through the scheduler, with live progress,
on one file, or on one file for each source when the flow has several.

### The file for each source

A flow with one source shows one field, labelled **File**. A flow with [several sources](several-files.md)
shows one field per source, each labelled with the source's name, in the order the sources are drawn from top
to bottom.

Each field starts with the file already chosen on the source block. To use another, open the list. Every entry
shows the file's name and its size, such as **12 pages**, **4 pages of text** or **image**, and the sample
files are marked **sample**. A field with nothing chosen reads **Choose a file**.

Changing a file here changes it on the source block too: the dialog and the block show the same choice, so the
builder's estimate follows.

Files that callers of the public endpoint sent are not in these lists. See
[the API tag](files-screen.md#the-sample-and-api-tags).

### Upload file

**Upload file** takes one file from your computer: a PDF, an image or a text file. While it is sent the button
reads **Uploading…**. When it is done, a message such as **Report.pdf uploaded (12 pages)** appears, the file
joins the list, and it is chosen for that source. If the upload is refused, the message gives the reason and
the field keeps its earlier choice.

The uploaded file also appears on the [Files screen](files-screen.md), where it can be removed later.
[File types](file-types.md) says what is accepted.

### Values

When the flow declares [value inputs](value-inputs.md), the **Values** section has one field for each. Beside
the input's name is either **Default:** and the default value, or **Required** when the input has no default.
If the flow's author wrote a description for the input, it appears under the field.

| Type of input | The field |
|---|---|
| Text | A text box. When there is a default, it is shown in grey until you type. |
| Number | A number box, with the default in grey. |
| Choice | A list of the allowed choices. The first entry reads **Default (value)** when there is a default, or **Choose** when there is none. |
| Yes / no | Two buttons, **Yes** and **No**. Neither is pressed until you choose. |
| JSON | A larger box for JSON. While its content is not valid JSON, a line under it reads **This is not valid JSON yet.** |

A field you leave empty is not sent, and the run uses the input's default. So you only need to fill in the
values you want to change, plus every input marked **Required**.

The values you start a run with are remembered in your browser for that flow, and filled in again the next
time you open this dialog or choose the flow in the Activity screen's **Submit jobs** form.

### Priority

| Choice | Meaning |
|---|---|
| **Interactive** | The default. Interactive jobs go ahead of bulk jobs when the quota is busy. |
| **Bulk** | The run waits behind interactive work. Use it to see how the flow behaves as background work, or to keep out of the way of others. |

Priority only matters when there is more work than the quota allows at once.
[Queue and priority](../how-it-works/queue-and-priority.md) explains the order in full.

### The estimate

The line that starts **This run:** shows three figures for the files chosen in the dialog:

- the number of model **calls** the run will make,
- the approximate number of **output tokens**, shown with **~**,
- the approximate **cost**, shown with **about**. A cost below one cent reads **under $0.01**.

The figures are recalculated whenever you choose a different file. They show **…** while they are being worked
out, and stay at **…** while a source has no file. The estimate does not change with the values or the
priority.

It is an estimate, not a quote. A filter's share of pages is not known before the run, and the output of a
step is predicted from what the step is set to expect or has produced before.
[Estimates](../how-it-works/estimates.md) explains how each figure is reached.

Under the estimate, the dialog names the gateway the calls go to and reminds you that they **cost real money**.

## Start the run

1. Check the file for each source.
2. Fill in the values you want to change, and every value marked **Required**.
3. Choose the priority.
4. Read the estimate.
5. Select **Start**. The button reads **Starting…**.

When you select **Start**, Document Engine does three things in order:

1. It saves the flow as it is on the canvas, with its name. A test run therefore also saves your work. It does
   not create a new version; see [Publishing](publishing.md) for versions.
2. It checks the flow, the files and the values, and creates one job labelled **Test run**.
3. It opens the [Run screen](run-screen.md) for that job.

**Cancel**, the close button, the Escape key and a click outside the dialog all close it without starting
anything.

## Test a single step

You can run the flow only as far as one step, to see that step's output without paying for the steps after it.

Open the step test in any of these ways:

- Select the step, then select **Test this step** at the bottom of its panel.
- Right-click the step and choose **Test this step**.
- Select the step and press **T**.

The dialog is the same, with these differences:

| | In a step test |
|---|---|
| Title | **Test "step name"** |
| What runs | The flow up to and including this step, then it stops. That is the step itself, every step before it, and everything its [references](several-files.md) need. Steps after it, and branches it does not depend on, do not run. |
| File fields | Only the sources this step depends on. |
| **Values** | Only the value inputs that this part of the flow uses. |
| Estimate | For this part of the flow only. |
| The job's label | **Step test: step name** |

Because the steps after the tested step do not run, the flow's own outputs are not produced. Instead the run
ends in one output named after the step, **step name output**, which holds what the step returned: as a table
when the step returns a schema, as text otherwise. Open it from the Run screen like any other result.

> **Tip:** after a step has run, right-click it and choose **View last outputs** to see what it returned in the
> latest run without leaving the builder.

## When something is missing

Document Engine refuses a run before any job is created, so a mistake costs nothing.

### A file is missing

**Start** stays greyed out until every source in the dialog has a file.

### A required value is missing

**Start** stays greyed out while an input marked **Required** is empty. Hover over the button to read which:
**Give a value for** followed by the names of the inputs that still need one.

### A value is wrong

Values are checked when you select **Start**. If one is not acceptable, no job is created, the dialog stays
open, and a message at the bottom of the screen names the input and says what is wrong. The cases are:

- a value of the wrong type, such as text where a number is expected;
- a choice that is not on the input's list;
- a JSON value that is not valid JSON;
- a text or JSON value longer than the limit (20,000 characters unless your administrator changed
  `worker.max_value_chars`; see [Settings](../operations/settings.md)). Longer content belongs in a file.

Correct the value and select **Start** again.

### The flow cannot run

If the flow has errors, the message starts **this flow cannot run yet:** and lists them. A file used as a
reference that has more pages than the limit for references is refused with a message naming the file, the
step and the limit; [Several files in one flow](several-files.md) explains that limit.

## Where the run goes next

Starting a run takes you to its [Run screen](run-screen.md), where the flow is drawn as it executes. From
there:

- when the run is complete, **View results** opens the [Results screen](results-screen.md);
- the run is listed on the [Activity screen](activity-screen.md) with every other job, under its label
  (**Test run** or **Step test: step name**), and can be reopened from there at any time;
- the browser's Back button returns to the builder, where the flow is as you left it.

## See also

- [The Run screen](run-screen.md): watching the run you just started.
- [Value inputs](value-inputs.md): declaring the values this dialog asks for.
- [Several files in one flow](several-files.md): sources, references and their limits.
- [The Activity screen](activity-screen.md): starting several jobs at once.
- [Estimates](../how-it-works/estimates.md): how the calls, tokens and cost are predicted.
