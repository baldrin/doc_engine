[Documentation](../README.md) › [User guide](README.md) › Build a flow

# Build a flow

This tutorial takes you from **New flow** and an empty canvas to a flow that works and has been tested. It is for someone who has not used the [flow builder](builder.md) before. It uses only the sample files that are installed with Document Engine, so you need nothing of your own.

The flow you will build reads a 24-page sample record, writes notes on small groups of pages, and combines the notes into one summary. Two optional parts at the end add a [value input](value-inputs.md) and a [Filter](instructions.md#filter).

> **Note:** A test run sends real calls to the model endpoint and costs money. The builder shows the estimated number of calls and the estimated cost before you start.

**On this page**

- [Before you start](#before-you-start)
- [Part 1: Create the flow](#part-1-create-the-flow)
- [Part 2: Add a file source](#part-2-add-a-file-source)
- [Part 3: Add a step and write its prompt](#part-3-add-a-step-and-write-its-prompt)
- [Part 4: Connect the source to the step (Map)](#part-4-connect-the-source-to-the-step-map)
- [Part 5: Add a second step that combines the notes (Reduce)](#part-5-add-a-second-step-that-combines-the-notes-reduce)
- [Part 6: Add an Output](#part-6-add-an-output)
- [Part 7: Validate](#part-7-validate)
- [Part 8: Test run](#part-8-test-run)
- [Part 9: Save a version](#part-9-save-a-version)
- [Optional: add a value input](#optional-add-a-value-input)
- [Optional: add a Filter](#optional-add-a-filter)
- [What you built](#what-you-built)

## Before you start

You need Document Engine open in a browser, with the sample material installed. The sample file used here is **Patient record (short, 24 pages).pdf**. It is fictional: every page says so in its footer.

Four words are used throughout. A **source** is a block that stands for one file. A **step** is a block that makes model calls. An **instruction** (Map, Reduce or Filter) sits on the connection into a step and says how the step is applied to what arrives. An **output** is a block that collects what a step produces. [Concepts](../start/concepts.md) explains them in full.

## Part 1: Create the flow

1. Open the [Flows screen](flows-screen.md) and choose **New flow**.

   The builder opens. The flow is called **Untitled flow**, the badge beside the name reads **New · Draft**, and the canvas shows the message **This flow is empty**.

2. Click the flow name in the top bar and type a name, for example `Record summary tutorial`.

   The builder saves your work by itself a moment after every change. You do not need a save button to keep a draft.

> **Screenshot to add:** `images/builder-empty-canvas.png`. The builder just after **New flow**: the library on the left, the empty canvas with the message "This flow is empty", the right-hand panel showing the flow panel, and the badge "New · Draft" beside the flow name.

## Part 2: Add a file source

1. In the library on the left, under **Sources**, click **File: PDF, image or text**. You can also drag it onto the canvas.

   A block labelled **SOURCE** appears and is selected. It shows the chip **No file**, because a new source starts with no file chosen. The right-hand panel shows the source.

2. In the right-hand panel, open the **File** list and choose **Patient record (short, 24 pages).pdf**. Sample files are marked **sample** in the list.

   The block now shows the file name and the chips **24 pages** and **PDF**. The top bar shows the same file after **Estimate for**.

The file you choose here is used for the estimate and for test runs only. When the flow is published, it can be run on any file.

> **Screenshot to add:** `images/builder-source-file-chosen.png`. A source block selected on the canvas, showing the file name and the chips "24 pages" and "PDF"; the right-hand panel shows the Source panel with the File list set to "Patient record (short, 24 pages).pdf" and the **Upload file** button beside it.

## Part 3: Add a step and write its prompt

1. In the library, under **Steps**, click **Blank step**.

   A block labelled **STEP · SELECTED** appears below the source. The right-hand panel shows the step, on the **Prompt** tab.

2. At the top of the right-hand panel, replace the name **New step** with `Note the pages`.

3. In the **System** block, write who the model is and how it should work. For example:

   ```text
   You are given a small group of consecutive pages from a longer patient record. A later step
   combines your notes with the notes on the other pages, so your notes must stand on their own.
   Report what the pages say in short plain statements, one fact per statement. Keep numbers and
   dates exact. Do not add anything the pages do not say.
   ```

4. In the **Instructions** block, write what to do with each input. For example:

   ```text
   Write notes on the pages you were given.
   ```

5. Leave the other settings as they are: **Output contract** on **Text** and **Cite pages in the text** switched on. On the **Model** tab, **Model** stays on Claude Sonnet and **Max output tokens** at 1500.

**Cite pages in the text** makes the engine add a rule to the prompt that asks the model to cite the page behind each statement, in the form `[p. 12]`. Those page references become links on the [Results screen](results-screen.md). [Steps](steps.md) explains every setting on this panel.

Until the step is connected, its block shows a warning and the bar under the canvas reports problems. That is expected at this stage.

> **Screenshot to add:** `images/builder-step-prompt-tab.png`. A step named "Note the pages" selected, with the right-hand panel on the Prompt tab: the System and Instructions blocks filled in, the Output contract set to Text, and Cite pages in the text switched on.

## Part 4: Connect the source to the step (Map)

1. Put the pointer on the dot at the right edge of the source block. Drag from that dot to the dot at the left edge of **Note the pages**, and release.

   A connection appears with a label on it: **Map 4 / 1**, and under it **24 → 8 items**. The right-hand panel switches to the step's **Input** tab.

2. Read the **Input** tab. **Instruction** is set to **Map**, **Window size** is 4 and **Overlap** is 1.

This is what the label means. [Map](instructions.md#map) makes one call for each window of consecutive pages. With a window of 4 pages and an overlap of 1, each window starts 3 pages after the one before, so neighbouring windows share one page:

| Call | Pages |
|---|---|
| 1 | 1 to 4 |
| 2 | 4 to 7 |
| 3 | 7 to 10 |
| … | … |
| 8 | 22 to 24 |

The 24 pages become 8 calls, and each call produces one [item](../glossary.md#item): its notes. The overlap means that something that runs across a page break is seen whole by at least one call.

> **Screenshot to add:** `images/builder-map-connection.png`. The source connected to the step "Note the pages" by a solid blue connection labelled "Map 4 / 1" and "24 → 8 items"; the right-hand panel on the Input tab showing Instruction set to Map, Window size 4 and Overlap 1.

## Part 5: Add a second step that combines the notes (Reduce)

1. In the library, click **Blank step** again. Name the new step `Overall summary`.

2. On its **Prompt** tab, fill in the two blocks. For example, in **System**:

   ```text
   You are given notes on every part of one patient record. Each note says which pages it covers.
   Combine them into one summary for a reader who has not seen the record. Group related facts,
   remove repetition, and keep numbers and dates exact.
   ```

   and in **Instructions**:

   ```text
   Write the summary in under 400 words.
   ```

3. Drag from the right dot of **Note the pages** to the left dot of **Overall summary**.

   The new connection is labelled **Reduce**, with **8 → 1 item** under it.

[Reduce](instructions.md#reduce) makes exactly one call, which receives every item at once. Here the call receives the 8 sets of notes and produces 1 summary. A connection from one step to another starts as Reduce; you can change it on the **Input** tab.

On the **Input** tab, **What each call receives** is set to **Earlier outputs**: the summary step reads the notes, not the pages. Because each set of notes is passed on together with the page numbers it covers, the summary can still cite pages.

> **Screenshot to add:** `images/builder-reduce-connection.png`. Three blocks in a row: the source, "Note the pages" and "Overall summary"; the second connection is solid green and labelled "Reduce" and "8 → 1 item"; the right-hand panel on the Input tab with Instruction set to Reduce and What each call receives set to Earlier outputs.

## Part 6: Add an Output

1. In the library, under **Output**, click **Output**.

2. Drag from the right dot of **Overall summary** to the left dot of the output block.

3. Click the output block. In the right-hand panel, rename it `Summary`. Leave **Show as** on **Text**.

An output collects what one step produces. Each output of a flow appears under its name on the [Results screen](results-screen.md). An output takes exactly one connection, and it must come from a step.

> **Screenshot to add:** `images/builder-output-panel.png`. The finished chain of four blocks: source, "Note the pages", "Overall summary" and an output named "Summary", which is selected; the right-hand panel shows the Output panel with the line "Collects what Overall summary produces" and Show as set to Text.

## Part 7: Validate

1. Look at the bar under the canvas. When nothing stands in the way of a run it reads **No problems. This flow can run.**

2. Choose **Validate** in the top bar. A short message confirms: **No problems found. This flow can run.**

If something is wrong, the bar shows the number of problems and the first message, and the block concerned carries a warning sign. Click the bar to see the list, then click a problem to jump to the block. Typical messages at this stage are that a step **needs a prompt**, that a block **has no input**, or that the flow still needs **an output**. The [problems bar](builder.md#the-problems-bar) section lists what the builder checks.

The top bar now shows the estimate for the chosen file: **9 calls**, an approximate number of output tokens, and an approximate cost. The 9 calls are the 8 Map calls and the 1 Reduce call.

> **Screenshot to add:** `images/builder-validated.png`. The whole builder with the finished flow, nothing selected: the top bar estimate showing "9 calls", the bar under the canvas reading "No problems. This flow can run.", and the right-hand panel showing Estimate by step with one row per step.

## Part 8: Test run

1. Choose **Test run** in the top bar. The button is available once there are no problems and every source has a file.

2. In the **Test run** dialog, check that **File** shows the 24-page sample. Leave **Priority** on **Interactive**. The line **This run:** repeats the estimate.

3. Choose **Start**.

The [Run screen](run-screen.md) opens and shows the job as it runs: the 8 calls of **Note the pages**, then the single call of **Overall summary**. When the job is done, open its results to read the summary; each page reference opens that page of the file beside the text. [Test runs](test-runs.md) describes the dialog and what follows in detail.

To go back to the flow, choose **Flows** in the top bar and open it again. A test run uses the flow as it is on the canvas at that moment, saved version or not.

> **Screenshot to add:** `images/builder-test-run-dialog.png`. The Test run dialog over the builder: the File list set to the 24-page sample, Priority with Interactive selected, the line "This run: 9 calls · ~… output tokens · about $…", and the Cancel and Start buttons.

## Part 9: Save a version

1. Choose **Save version** in the top bar.

   A message reads **Saved as v1**, and the badge beside the flow name changes from **New · Draft** to **v1 · Saved**.

A version is a numbered copy of the flow as it is now. **Save version** checks the flow first, so a flow with problems is not saved as a version. Saving a version does not make the flow available to callers of the API; that is what **Publish** does. See [Publishing](publishing.md).

## Optional: add a value input

A [value input](value-inputs.md) is a small value that is sent with each run, so the same flow can behave differently without being edited. Here you add one that says who the summary is for.

1. Click an empty part of the canvas, so that nothing is selected. The right-hand panel shows the flow panel, with the section **Inputs**.

2. Choose **Add an input**. A new input called **Input 1** appears.

3. Replace the name with `Audience` and press Enter. Leave **Type** on **Text**. In **Default**, type `a general reader`. In the description field, type `Who the summary is written for`.

   The note under the input reads **Used when a run does not supply it.** followed by **Not used by any step yet.**

4. Click the step **Overall summary** and open its **Prompt** tab. Click at the end of the **Instructions** block and type ` Write for `, then, under the blocks, beside **Insert a flow input:**, click **Audience**.

   The text `{{Audience}}` is inserted where the cursor is. The instructions now read: `Write the summary in under 400 words. Write for {{Audience}}`.

5. Choose **Test run**. The dialog now has a **Values** section with a field **Audience**, marked **Default: a general reader**. Leave it empty to use the default, or type another value such as `a hospital pharmacist`, then choose **Start**.

When the job is submitted, every `{{Audience}}` in the flow is replaced by the value for that run. The job records the values it ran with.

> **Screenshot to add:** `images/builder-inputs-editor.png`. Nothing selected on the canvas; the right-hand flow panel shows the Inputs section with one input named "Audience": Type set to Text, Default "a general reader", the description filled in, and the Add an input button below.

## Optional: add a Filter

A [Filter](instructions.md#filter) lets a step run only on the items that match a rule. The rule reads a field from the output of the step before it, so that step must have a schema output. Here you add a second branch to the flow: one step classifies every page, and a second step runs only on the pages classified as reports.

1. In the library, under **Steps**, click **Classify page type**.

   This is a ready-made step. It uses Claude Haiku, has a prompt already, and has a schema output with one field, **page_type**, which is one of `letter`, `report`, `form`, `table` or `other`.

2. Drag from the right dot of the source block to the left dot of **Classify page type**.

   The connection starts as **Map 4 / 1**. This step classifies single pages, so on the **Input** tab set **Overlap** to 0, then **Window size** to 1. The label becomes **Map 1 / 0** with **24 → 24 items**: one call per page.

3. Add a **Blank step** and name it `Describe the reports`. Give it a prompt, for example in **System**: `You are given one page of a patient record that holds a report. State what kind of report it is, its date, and its main findings, exactly as printed.` and in **Instructions**: `Describe this report.`

4. Drag from the right dot of **Classify page type** to the left dot of **Describe the reports**. The connection starts as **Reduce**.

5. On the **Input** tab, set **Instruction** to **Filter**. Under **Keep items where**, choose the field **page_type**, the comparison **equals**, and the value **report**.

   **What each call receives** changes to **Their pages**: the step receives the page itself, not the classification.

6. Add a second **Output**, connect **Describe the reports** to it, and name it `Reports`.

The Filter connection is dashed and labelled **Filter**, with **report · 24 → ~6** under it. The engine cannot know in advance how many pages the model will classify as reports, so until the flow has run once it assumes that a quarter of the items are kept. After a run, the estimate uses the share kept in that run. How many pages are kept in your run depends on what the model answers for each page.

> **Screenshot to add:** `images/builder-filter-rule.png`. The flow with its second branch: source, "Classify page type", a dashed orange connection labelled "Filter" and "report · 24 → ~6", "Describe the reports" and an output named "Reports"; the right-hand panel on the Input tab with Instruction set to Filter, the rule "page_type equals report", and What each call receives set to Their pages.

## What you built

The flow has one source, four steps and two outputs:

| Block | Instruction on the way in | Calls for the 24-page sample |
|---|---|---|
| Note the pages | Map, window 4, overlap 1 | 8 |
| Overall summary | Reduce | 1 |
| Classify page type | Map, window 1, overlap 0 | 24 |
| Describe the reports | Filter, `page_type` equals `report` | one per page kept |

Choose **Save version** again to keep this state as the next version.

## See also

- [Flow builder](builder.md): every control you used here, and the ones you did not.
- [Instructions](instructions.md): Map, Reduce and Filter in full, with more worked examples.
- [Steps](steps.md): prompt blocks, models, output limits, thinking and the output contract.
- [Test runs](test-runs.md): what a test run does and how to test a single step.
- [Publishing](publishing.md): making the finished flow available to callers.
