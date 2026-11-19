[Documentation](../README.md) › [User guide](README.md) › Flow builder

# Flow builder

This page is the complete reference for the flow builder, the screen where a flow is drawn, configured, checked and tested. It describes every control and what it does. It is for anyone who builds or changes flows; if you have not built one yet, start with [Build a flow](build-a-flow.md).

**On this page**

- [The parts of the screen](#the-parts-of-the-screen)
- [How your work is saved](#how-your-work-is-saved)
- [The top bar](#the-top-bar)
- [The library](#the-library)
- [The canvas](#the-canvas)
- [The right-hand panel](#the-right-hand-panel)
- [The problems bar](#the-problems-bar)

## The parts of the screen

The builder opens when you choose **New flow** or open a flow on the [Flows screen](flows-screen.md). It has five parts:

| Part | Where | What it is for |
|---|---|---|
| Top bar | Across the top | The flow's name and version, the estimate, and the actions on the whole flow. |
| Library | Left | The blocks and instructions you can add. |
| Canvas | Centre | The flow itself: blocks and the connections between them. |
| Right-hand panel | Right | The settings of whatever is selected, or of the flow when nothing is. |
| Problems bar | Under the canvas | What stops the flow from running, and the zoom controls. |

A flow is made of three kinds of block. A **source** stands for one file. A **step** makes model calls. An **output** collects what a step produces. Blocks are joined by connections, and the connection into a step carries its [instruction](instructions.md): Map, Reduce or Filter.

> **Screenshot to add:** `images/builder-overview.png`. The whole builder with the sample flow "Medical record summary" open and nothing selected: top bar with estimate and buttons, library on the left, canvas with seven blocks and labelled connections, the minimap, the right-hand flow panel, and the bar under the canvas reading "No problems. This flow can run."

## How your work is saved

The builder saves the flow by itself shortly after every change, including moving a block. While it does, **Saving…** appears beside the version badge; if a save fails, **Not saved** appears there instead. What is saved this way is the *draft*: the flow as it is on the canvas.

A draft is not a version. **Save version** and **Publish** make numbered versions; see [Publishing](publishing.md).

## The top bar

From left to right:

| Control | What it does |
|---|---|
| Logo | Goes to the Flows screen. |
| **Document Engine / Flows** | Links back to the Flows screen. |
| Flow name | Click it and type to rename the flow. A published flow is run by this name, so see [Publishing](publishing.md#the-name-rule) before renaming one. |
| Version badge | Shows the latest version number and the state of the flow. See below. |
| Estimate | The estimated calls, output tokens and cost of one run. See below. |
| **Flows**, **Files**, **Activity** | Go to the [Flows](flows-screen.md), [Files](files-screen.md) and [Activity](activity-screen.md) screens. |
| Sun or moon button | Switches the whole site between light and dark. The choice is remembered in the browser. |
| **Validate** | Checks the flow now and reports the result. |
| **Test run** | Runs the whole flow once on the chosen files. |
| **Save version** | Stores the flow as it is now as the next numbered version. |
| **API** | Opens the panel that shows how to run the flow from code. |
| **Publish** | Stores the next version and makes it the one callers run. |

### Version badge

| Badge | Meaning |
|---|---|
| **New · Draft** | The flow has no version yet. |
| **v3 · Draft** | Version 3 is the latest version, and the flow has been changed since that version was made. Moving a block does not count as a change. |
| **v3 · Saved** | Version 3 is the latest version and it is not the published one. |
| **v3 · Published** (green) | Version 3 is the latest version and it is the published one. |
| **· v2 is published** after any of the above | Callers still get version 2: a newer version has been saved, or the flow has been changed, since it was published. |

### Estimate

The middle of the top bar reads **Estimate for**, followed by the file and three figures in the form `9 calls · ~8.1k output tokens · about $0.30`. The figures depend on the flow, the file and the prices configured for each model; a cost below one cent is shown as `under $0.01`.

- With one source, the file is a list. Choosing a file here is the same as choosing it on the source block.
- With several sources, the bar shows the number of files and their total pages, for example `3 files · 6 pages`. Choose the file for each source on its block.
- With no source, it reads **no source yet**.
- Until every source has a file, the figures are replaced by **to see the figures** (one source) or **choose a file for every source to see the figures** (several).

The estimate is worked out from each step's settings, and from real calls once a step has run: after a step has made three real calls, its measured output size replaces the **Expected output tokens per call** setting. A Filter is assumed to keep a quarter of its items until the flow has run once. [Estimates](../how-it-works/estimates.md) explains the calculation.

The estimate is recalculated a moment after anything that changes the flow's meaning. Moving blocks does not change it.

### Validate

**Validate** checks the flow and tells you the result at once. With no problems it reports **No problems found. This flow can run.** With warnings only, it says the flow can run, gives the number of warnings and opens the list. Otherwise it reports the number of problems and opens the list over the canvas. The builder also checks the flow by itself after every change, so the [problems bar](#the-problems-bar) is always current; **Validate** is the way to ask for the answer explicitly.

### Test run

**Test run** opens a dialog that runs the whole flow once: a file for each source, a value for each [value input](value-inputs.md), a **Priority** (**Interactive** or **Bulk**), the estimate for this run, and **Start**. The button is unavailable while the flow has problems (**Fix the problems first**) or while a source has no file (**Choose a file for every source first**). A test run uses the flow as it is on the canvas, not a saved version. See [Test runs](test-runs.md).

### Save version, API and Publish

**Save version** stores the flow as the next version and reports **Saved as v4**. It does not check the flow, so a flow with problems can still be saved as a version.

**Publish** checks the flow first. If there are problems it refuses with **Fix the problems before publishing.** and opens the problem list. Otherwise it stores the next version, makes it the published one, and reports **Published as v4**.

**API** opens the panel titled **Run "…" from code**. All three are described in [Publishing](publishing.md).

## The library

The library lists everything that can be added to a flow. The **Search blocks** field at the top narrows the list to the entries whose names contain what you type.

To add a block, drag it onto the canvas, or click it. A dragged block lands where you drop it. A clicked block is placed below the lowest block on the canvas, and the view is refitted so that you can see it. A new block is selected, so its settings appear in the right-hand panel.

### Sources

| Item | What it adds |
|---|---|
| **File: PDF, image or text** | A source block named **File**, with no file chosen. A second and third source are named **File 2**, **File 3**, because each source of a flow needs its own name. See [File types](file-types.md) and [Several files in one flow](several-files.md). |

### Steps

| Item | What it adds |
|---|---|
| **Blank step** | A step named **New step** with an empty prompt. Model: Claude Sonnet. **Max output tokens**: 1500. Thinking off. Text output. **Track source pages** on. |
| **Classify page type** | A ready-made step that classifies a single page. Model: Claude Haiku. **Max output tokens**: 300, expected output 40. The prompt is filled in. Schema output with one field, `page_type`, one of `letter`, `report`, `form`, `table`, `other`. It is meant to be followed by a [Filter](instructions.md#filter). |
| **Summarize window** | A ready-made step that writes notes on a small group of consecutive pages. Model: Claude Sonnet. **Max output tokens**: 1500, expected output 900. The prompt is filled in. Text output. |

The two ready-made steps are ordinary steps. Change anything in them after adding them.

### Instructions

The instructions are not blocks. An instruction belongs to the connection into a step. Clicking one here applies it to the connection that the selected step works through, and opens the step's **Input** tab. The instruction in use is highlighted. Until a step with an input, or a connection into a step, is selected, the entries are unavailable (**Select a step or a connection first**).

| Item | Description shown | What it does |
|---|---|---|
| **Map** | Run over windows of items | One call per window of consecutive items. |
| **Fold** | Each call gets the last output | Marked **Soon**. Fold is designed but not available yet, and cannot be chosen. |
| **Reduce** | Many in, exactly one out | One call that receives every item. |
| **Filter** | Keep items that match a rule | Keeps the items whose earlier output matches a rule, then one call per kept item. Not possible on a connection that comes from a source: the builder answers **A filter reads a field from an earlier step.** |

Applying an instruction from the library resets **What each call receives** to the default for that instruction. [Instructions](instructions.md) explains each one.

### Output

| Item | What it adds |
|---|---|
| **Output** | An output block named **Output**, shown as text. |

> **Screenshot to add:** `images/builder-library.png`. The library panel alone: the Search blocks field, the groups Sources, Steps, Instructions (Map, Fold with the "Soon" chip, Reduce, Filter) and Output, and the hint at the bottom about dragging and the "/" key.

## The canvas

### Blocks

Each block shows its kind in small capitals (**SOURCE**, **STEP**, **OUTPUT**; a selected step reads **STEP · SELECTED**), its name, and a row of chips:

| Block | Chips |
|---|---|
| Source | The number of pages, or **No file**; then **PDF**, **Image** or **Text**. When the flow has one source, the block is headed by the file's name. When it has several, it is headed by the source's own name, and the file's name is the first chip. |
| Step | The model; **Text out** or **Schema:** followed by the first field's name; and **Thinking low**, **medium** or **high** when thinking is on. |
| Output | **Text** or **Table**. |

A block with a problem carries a warning sign. A step with a problem shows the problem in place of its chips, for example **Needs a prompt**.

Blocks have connection dots: a source has one on its right, a step has one on each side, an output has one on its left.

### Moving around

- Drag a block to move it. Blocks snap to a fine grid.
- Drag an empty part of the canvas to move the view, and use the mouse wheel or the zoom controls to zoom.
- The zoom controls are at the right of the bar under the canvas: **−**, the current zoom as a percentage, **+**, and **Fit**, which brings the whole flow into view. Zoom runs from 30% to 160%.
- The minimap in the corner of the canvas shows the whole flow and the part now in view. Drag inside it to move the view, and scroll over it to zoom. The selected block is shown in the accent colour and blocks with problems in the warning colour.

### Connecting blocks

Drag from the dot on the right of one block to the dot on the left of another.

What the new connection becomes depends on the two blocks:

| From | To | The connection becomes |
|---|---|---|
| Source | Step with no input yet | **Map**, window 4 and overlap 1. If the file chosen for the source has one page: **Map**, window 1 and overlap 0. |
| Step | Step with no input yet | **Reduce**. |
| Source or step | Step that already has an input | A [reference](several-files.md#references). The builder confirms: *name* **added as a reference for** *step*. |
| Step | Output | A plain connection. An output has no instruction. |

Connections that are not allowed are refused with a short message:

| Message | Why |
|---|---|
| **A source cannot receive a connection.** | A source is where a flow starts. |
| **Those two blocks are already connected.** | Two blocks can be joined once in the same direction. |
| **An output takes one input. Remove it first.** | An output collects from exactly one step. |
| **An output is fed by a step.** | A source cannot be connected straight to an output. |
| **An output is the end of a flow.** | Nothing can be connected from an output. |

### How connections look

Every connection into a step has a label, and the label is a button: click it to select the connection.

| Connection | Line | Label | Second line of the label |
|---|---|---|---|
| Map | Solid, blue | **Map 4 / 1** (window size / overlap) | Items in and calls out for the chosen file, for example `24 → 8 items` |
| Reduce | Solid, green | **Reduce** | For example `8 → 1 item` |
| Filter | Dashed, orange | **Filter** | The value the rule compares with, then items in and items kept, for example `report · 24 → ~6`. The `~` means the share kept is still an assumption. |
| Reference | Dotted, grey | **Reference** | `whole, on every call` |
| Into an output | Solid, grey | None | A small note with the number of items, for example `1 item` |

### Selecting

- Click a block to select it. Its settings appear in the right-hand panel.
- Double-click a block to select it and open its settings; for a step this opens the **Prompt** tab.
- Click a connection's label to select the connection. The right-hand panel shows the step the connection goes into, on its **Input** tab.
- Click an empty part of the canvas, or choose **Done** in a step's panel, to select nothing. The right-hand panel then shows the flow panel.

### Right-click menu of a block

Right-clicking a block selects it and opens a menu headed by the block's name.

| Item | Shortcut shown | What it does |
|---|---|---|
| **Configure** | Double click | Selects the block and shows its settings; for a step, on the **Prompt** tab. |
| **Rename** | F2 | Puts the cursor in the name field of the right-hand panel, with the name selected. |
| **Duplicate** | Ctrl D | Adds a copy of the block, named with ` copy` at the end, a little below the original. The copy has the same settings and no connections. |
| **Test this step** | T | Steps only. Opens the dialog that runs the flow up to and including this step. See [Steps](steps.md#test-this-step). |
| **View last outputs** | | Steps only. Shows what this step produced in the latest run. See [Steps](steps.md#view-last-outputs). |
| **Delete** | Del | Removes the block and every connection to and from it. |

### Right-click menu of a connection

Right-clicking a connection opens a menu headed **Connection**.

| Item | Shown when | What it does |
|---|---|---|
| **Use as the step's input** | The connection is a reference into a step | Makes this connection the one the step works through. The step's previous input becomes a reference. |
| **Use as a reference** | The connection is the input of a step | Turns the connection into a reference. The step then has nothing to work through until another connection is made its input. |
| **Delete connection** (Del) | Always | Removes the connection. |

A connection that becomes a reference loses its instruction settings. A reference that becomes the input starts as Map with window 1 and overlap 0 when it comes from a source, and as Reduce when it comes from a step. [Several files in one flow](several-files.md) explains inputs and references.

### Keyboard shortcuts

The shortcuts work when the cursor is not in a text field and no dialog is open.

| Key | What it does |
|---|---|
| `/` | Opens **Add a block**, the quick add dialog. |
| `F2` | Renames the selected block. |
| `Ctrl` + `D` (or `Cmd` + `D`) | Duplicates the selected block. |
| `T` | Opens **Test this step** for the selected step. |
| `Delete` or `Backspace` | Removes the selected block or connection. |
| `Esc` | Closes a menu, the problem list or a dialog. |

### Quick add

Pressing `/` opens the dialog **Add a block**, with the five blocks of the library: **Blank step**, **Classify page type**, **Summarize window**, **Output** and **File: PDF, image or text**. Click one to add it, placed as a clicked library item would be.

### The empty canvas

A flow with no blocks shows **This flow is empty**, with a reminder of the order to work in: a **File** source, then a step, then an output, connected by dragging from one block's dot to the next.

> **Screenshot to add:** `images/builder-block-menu.png`. The canvas with a step right-clicked: the menu headed by the step's name, with Configure, Rename, Duplicate, Test this step, View last outputs and Delete, each with its shortcut at the right.

## The right-hand panel

The right-hand panel shows the settings of what is selected. It has five states.

### Nothing selected: the flow panel

The panel is headed **Flow**, with the flow's name and the line **Select a block or a connection to edit it.** It holds:

- **Inputs**: the editor for the flow's [value inputs](value-inputs.md). Each input has a name, a **Type** (**Text**, **Number**, **Choice**, **Yes / no**, **JSON**), a **Default** and a description. A choice input also has its list of choices. **Add an input** adds one; the cross beside a name removes it. The note under each input says whether a run must supply it (**No default: every run must supply it.**) or not (**Used when a run does not supply it.**), and warns when it is **Not used by any step yet.**
- **Estimate by step**: one row per step, with its number of calls and its estimated cost for the chosen files. The heading shows the number of pages the estimate is for. Click a row to select that step.
- When the flow has a Filter that has not run yet: **A filter's share is assumed to be 25% until the flow has run once.**
- A reminder of three shortcuts: right-click for more actions, `Del` to remove, `F2` to rename, `Ctrl D` to duplicate.

### A source selected

The panel is headed **Source**.

| Control | What it does |
|---|---|
| Name | The name of this source. When a flow has several sources, this name identifies the file to the model and appears in page references, for example `[Invoice p. 2]`. |
| **File** | The file this source uses for the estimate and for test runs. Sample files are marked **sample**. Each entry shows the file's size: a number of pages, **image**, or pages **of text**. |
| **Upload file** | Uploads a PDF, an image or a text file from your computer and chooses it for this source. |
| **Manage files** | Opens the [Files screen](files-screen.md). |

The file chosen here is used for the estimate and for test runs only; a published flow can be run on any file. The builder remembers the file chosen for each source of each flow in the browser. A new source has no file until you choose one, so nothing is estimated or run on a file nobody picked.

### A step selected

The panel is headed **Step**. Under the name, one line says what the step receives, for example **Receives windows of 4 pages through Map**, **Receives all outputs through Reduce**, **Receives the items that pass the filter**, or **Not connected yet**.

The settings are on four tabs. [Steps](steps.md) explains each setting in depth; this is the map.

| Tab | What is on it |
|---|---|
| **Prompt** | **Prompt blocks**: **System** and **Instructions**, with a tag that reads **Cache ready** or **Too short to cache**. The row **Insert a flow input:** with one button per value input, and **Manage inputs** (or **Add one**), which shows the flow panel. A line saying what is inserted from the input: **pages**, **outputs** or both. A line listing the step's references. Then **Model**, **Max output tokens**, **Output contract** (**Text** or **Schema**) and **Track source pages**. |
| **Model** | **Model**, **Max output tokens**, **Thinking** (**Off**, **Low**, **Medium**, **High**), **Expected output tokens per call**, and a line with the model's limits per minute and its prices. |
| **Input** | The block the step works through, the **Instruction** (**Map**, **Reduce**, **Filter**) and its settings, **What each call receives**, the figures for the chosen file, and the step's **References**. See below. |
| **Output** | **Output contract**, the **Fields** of a schema output with **+ Add field**, and **Track source pages**. |

At the bottom of every tab are **Test this step** and **Done**. **Done** closes the step's settings by selecting nothing.

#### The Input tab

When the step has no input, the tab says how to connect one. Otherwise it shows:

| Control | What it does |
|---|---|
| First row | The name of the block the step works through, with the note **Works through this**. |
| **Instruction** | **Map**, **Reduce** or **Filter**. **Filter** is unavailable when the input comes straight from a source. |
| **Window size**, **Overlap** | Map only. How many consecutive items each call receives, and how many of them are shared with the next call. See [Map](instructions.md#map). |
| **Keep items where** | Filter only. The rule: a field of the earlier step's schema output, a comparison, and a value. Under it, **Or compare with a flow input:** offers a button for each value input. See [Filter](instructions.md#filter). |
| **What each call receives** | Shown when the input comes from another step. **Earlier outputs**: what that step produced. **Their pages**: the pages of the file that those outputs cover. **Both**. When the input is a source, the tab says instead **This step reads pages straight from the file.** |
| **For this file:** | Items in, calls and approximate output tokens for the chosen file. |
| **References** | One row per reference, with **Make input** (work through this instead; the current input becomes a reference) and a cross that removes the reference. With no references, a line explains how to add one. With references, a line gives their approximate input tokens per call. |

### An output selected

The panel is headed **Output**. Under the name, one line reads **Collects what** *step* **produces**, or **Not connected yet**.

| Control | What it does |
|---|---|
| Name | The name of this output. Results are listed under it. |
| **Show as** | **Text** shows each item as text. **Table** shows the items as rows, and needs the step before it to have a schema output. |

### A connection selected

Selecting a connection shows the block the connection goes into:

- a connection into a step shows that step's panel on the **Input** tab, where the instruction and its settings are;
- a connection into an output shows the output's panel.

While a connection into a step is selected, the instructions in the library apply to that step's input.

> **Screenshot to add:** `images/builder-step-input-tab.png`. A step selected with the right-hand panel on the Input tab: the "Works through this" row, Instruction set to Map, Window size and Overlap, the "For this file" line, and the References section with one reference row showing Make input and the remove cross.

## The problems bar

The bar under the canvas says whether the flow can run.

- **No problems. This flow can run.** means nothing stands in the way.
- **This flow can run.** followed by a number of warnings means the flow runs, but something deserves a look. Clicking the bar opens the list.
- Otherwise the bar shows the number of problems and the first message. With one problem, clicking the bar goes straight to it. With several, clicking opens the list over the canvas; click a problem to go to it. Going to a problem selects the block, centres the view on it, and opens the **Input** tab when the problem is on a connection, or the **Prompt** tab otherwise.

Problems stop **Test run** and **Publish**. The list can also hold warnings, shown with a fainter sign; warnings do not stop a run. The two warnings are a step that **goes nowhere** (it is not connected to a step or an output) and a value input that **is not used by any step**.

What the builder checks:

| Area | What must be true |
|---|---|
| The flow | It has at least one source, one step and one output, and no connection loops back to an earlier block. |
| Sources | Each is connected to a step. When there are several, each has its own name. |
| Steps | Each has an input, and exactly one connection it works through. It has a prompt (something in **System** or **Instructions**), a configured model and a known thinking setting. No two connections come from the same block. |
| Schema outputs | At least one named field, no two fields with the same name, and allowed values for every `one of` field. |
| Map | **Window size** is at least 1 and **Overlap** is smaller than the window. |
| Filter | The earlier step has a schema output; the rule names one of its fields; the rule has a value, unless the comparison is `is true` or `is false`. |
| Outputs | Each has exactly one connection, from a step. |
| Value inputs | Each has a name without braces, no two share a name, a choice input has its list of choices, a default is valid for its type, and every `{{Name}}` in a prompt or rule names a declared input. |

> **Tip:** When you lower **Window size** to 1 on a connection that still has **Overlap** 1, the builder reports that the overlap must be smaller than the window. Set **Overlap** to 0.

> **Screenshot to add:** `images/builder-problems-list.png`. A flow with two problems: the bar under the canvas showing "2 problems" and the first message, the problem list open over the canvas, and the two blocks concerned carrying warning signs.

## See also

- [Build a flow](build-a-flow.md): the same controls used in order, on a worked example.
- [Steps](steps.md): every setting on the step's four tabs.
- [Instructions](instructions.md): Map, Reduce and Filter, with numbers.
- [Test runs](test-runs.md): the **Test run** dialog and what follows.
- [Publishing](publishing.md): **Save version**, **Publish**, the **API** panel and **Unpublish**.
