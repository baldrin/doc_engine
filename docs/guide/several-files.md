[Documentation](../README.md) › [User guide](README.md) › Several files in one flow

# Several files in one flow

A flow can read more than one file in a run: two lists to compare, or an invoice to check against its order and its delivery note. This page explains named sources, the difference between the one input a step works through and its references, how to make and swap them, their limits, and how page references name the file they point into. It is for anyone building a flow that needs more than one file.

**On this page**

- [Several sources](#several-sources)
- [One input, any number of references](#one-input-any-number-of-references)
- [References](#references)
- [Making a reference](#making-a-reference)
- [Swapping an input and a reference](#swapping-an-input-and-a-reference)
- [Writing the prompt](#writing-the-prompt)
- [Page references carry the input name](#page-references-carry-the-input-name)
- [Two sample flows to study](#two-sample-flows-to-study)
- [Limits](#limits)

> **Not yet confirmed:** Flows with several sources and references have run only against the fake gateway. The prompts and page references described here have not yet met a real model; that is planned for the first session against the real gateway.

## Several sources

Add one source block for each file the flow needs. Each source is a named **input** of the flow that takes exactly one file per run.

- The name is the name of the block. Set it in the right-hand panel with the source selected. The first source you add is called **File**, the next **File 2**, then **File 3**; rename them to what they hold, such as `Purchase order` and `Invoice`.
- When a flow has several sources, every source needs a name, and no two may share one. Upper and lower case, spacing and punctuation do not make names different, because that is how the names a caller sends are matched. A name needs at least one letter or digit.
- The name matters. It is how the model is told which file is which, how page references are labelled, and the name under which a caller of the [API](../api/README.md) sends that file.

With several sources, the builder changes in a few places:

| Where | With one source | With several sources |
|---|---|---|
| Source block | Headed by the file's name. | Headed by the source's name; the file's name is a chip. |
| Top bar estimate | A list to choose the file. | The number of files and their total pages, for example `3 files · 6 pages`. Choose each file on its block. |
| **Test run** dialog | One **File** list. | One list per source, labelled with the source's name. |

Each source must be connected to a step, and every source needs a file before the estimate is shown or a test run can start.

> **Screenshot to add:** `images/builder-several-sources.png`. The sample flow "Check an invoice against its order" on the canvas: three source blocks named Purchase order, Delivery note and Invoice, each with its file name, page count and type as chips; the top bar estimate reading "3 files" with the total pages.

## One input, any number of references

Every step has exactly one connection that it **works through**. This is its input (in the engine's own terms, its *material*). The [instruction](instructions.md) on that connection, Map, Reduce or Filter, decides how many calls the step makes.

A step can also have any number of **references**. A reference does not change how many calls the step makes. It is extra reading that is handed to the step whole, on every call.

| | The input | A reference |
|---|---|---|
| How many per step | Exactly one | None, one or several |
| Has an instruction | Yes: Map, Reduce or Filter | No |
| What a call receives | The window, item or items for that call | All of it, every time |
| Line on the canvas | Solid (dashed for Filter), coloured by instruction | Dotted, grey, labelled **Reference** |
| Decides the number of calls | Yes | No |

**Example.** A step checks an invoice page by page against a purchase order. The invoice is the input, with Map and a window of 1: a 3-page invoice makes 3 calls, one per page. The purchase order is a reference: each of the 3 calls receives the whole purchase order beside its one invoice page.

## References

A reference can come from either kind of block:

| The reference comes from | What every call of the step receives |
|---|---|
| A step | Everything that step produced in this job: all its outputs, each marked with the pages it covers. |
| A source | The complete file. |

Three properties follow from "whole, on every call":

- **The step waits.** A step starts only when the block it works through and every block it references have finished.
- **The cost repeats.** A reference is sent again with every call of the step, and it is not part of the cached opening of the prompt. A large reference on a step with many calls is paid for on every one of them. The step's **Input** tab shows the approximate input tokens per call that its references add, and the estimate includes them.
- **Size is limited.** A source used as a reference may have at most 100 pages (the setting `worker.max_reference_pages`). See [Limits](#limits).

When a file is long, do not attach it as a reference. Read it once in a step of its own, and use that step as the reference. The sample flow **Check an invoice against its order** does this: one step records what was ordered, another what was delivered, and the checking step references those two short records, not the two files.

## Making a reference

Connect a second block to a step that already has an input.

1. Make sure the step already has the connection it works through.
2. Drag from the right dot of the other block, a source or a step, to the left dot of the step.

The builder makes the new connection a reference and confirms it: *name* **added as a reference for** *step*. A connection into a step that has no input yet becomes its input; a connection into a step that already has one becomes a reference.

The step's panel shows its references in two places: on the **Prompt** tab, in the line **References, whole on every call:** (a source is marked **(whole file)**), and on the **Input** tab, under **References**.

To remove a reference, click the cross on its row under **References**, or right-click the connection and choose **Delete connection**.

## Swapping an input and a reference

Sometimes the builder's guess is the wrong way round, because the block you connected first was meant to be the reference. There are two ways to swap.

**From the canvas:**

1. Right-click the dotted reference connection.
2. Choose **Use as the step's input**.

**From the panel:**

1. Select the step and open the **Input** tab.
2. Under **References**, choose **Make input** on the row of the block the step should work through.

Either way, the chosen connection becomes the input and the previous input becomes a reference. Then check the **Instruction** on the **Input** tab. A connection that was the step's input before gets back the instruction, window, overlap and rule it had then. One that has never been the input starts with a default: Map with window 1 and overlap 0 when it comes from a source, Reduce when it comes from a step.

The right-click menu of an input connection has the opposite item, **Use as a reference**. It turns the step's input into a reference and leaves the step with nothing to work through, which the builder reports as a problem until you make another connection the input.

> **Screenshot to add:** `images/builder-reference-menu.png`. A step with one solid input connection and one dotted grey connection labelled "Reference"; the dotted connection is right-clicked and its menu shows "Use as the step's input" and "Delete connection"; the right-hand panel on the Input tab lists the reference with the Make input button.

## Writing the prompt

The model is given each reference under the name of the block it comes from, so use those names in the prompt.

- A reference from a step arrives labelled with the step's name, for example `Read the order`.
- A reference from a source arrives as the whole file, introduced by its input name, for example `Purchase order`.
- The pages the step works through are introduced, at the end of the request, as pages of the input with that source's name.

A prompt for the checking step in the example above could say: *"You check one page of a supplier invoice against two references: what was ordered, in the reference named Read the order, and what was delivered, in the reference named Read the delivery."*

Renaming a block changes the name the model sees, so rename the block and the prompt together.

## Page references carry the input name

In a flow with one source, a page reference names only the page: `[p. 12]` or `[pp. 12-14]`.

In a flow with several sources, "page 2" could be page 2 of any of the files. So the engine asks the model to cite the input name with the page, exactly as the source is named:

```text
[Invoice p. 2]
[Purchase order pp. 1-2]
```

On the [Results screen](results-screen.md), such a reference opens that page of that file. A table output likewise shows the input name in its page column.

This is why source names should be short, distinct and stable. If you rename a source, runs made after the change use the new name; each job keeps the names it ran with.

The citation rule is added to steps with a text output and **Cite pages in the text** switched on; see [Steps](steps.md#cite-pages-in-the-text).

## Two sample flows to study

Two of the installed sample flows use several files. Open them in the builder to see the arrangements described here.

**Compare two medication lists** reads two short files in one call.

| Block | Role |
|---|---|
| **Admission list** (source) | The input of the step, through Reduce: all its pages in one call. |
| **Discharge list** (source) | A reference: the whole file, in that same call. |
| **Compare the lists** (step) | One call that sees both files. |

**Check an invoice against its order** reads three files.

| Step | Works through | References |
|---|---|---|
| **Read the order** | **Purchase order**, Reduce | |
| **Read the delivery** | **Delivery note**, Reduce | |
| **Check the invoice** | **Invoice**, Map with window 1 | **Read the order**, **Read the delivery** |
| **Verdict** | **Check the invoice**, Reduce | |

The two reading steps run first. **Check the invoice** waits for both, then makes one call per invoice page, each with both records attached.

## Limits

| Limit | Value | What happens beyond it |
|---|---|---|
| Inputs a step works through | Exactly one | A step with none, or with more than one, is reported as a problem. |
| References per step | No fixed number | Each one adds input tokens to every call of the step. |
| Pages of a source used as a reference | 100 (`worker.max_reference_pages`) | The run is refused before it starts. The message names the file and the step, and advises summarizing the file in a step first and using that step as the reference. |
| Size of one request | 16 MB (`gateway.max_request_mb`) | A call whose pages and references exceed it is not sent, and the job fails. |
| Connections between the same two blocks | One | A second is refused: **Those two blocks are already connected.** |
| What can be a reference | A source or a step | An output cannot be one. |
| What can have references | A step | An output takes exactly one connection, from a step. |
| Loops | Not allowed | A reference that would close a loop is reported as a problem. |
| Files per source | One per run | Batches of files as one source are not built. |

The limit on reference pages is checked against the file chosen for the run, so a flow can pass with a short file and be refused with a long one. Administrators can change both settings; see [Settings](../operations/settings.md).

## See also

- [Instructions](instructions.md): what the one input connection does.
- [Steps](steps.md): prompt blocks, and what the engine adds around them.
- [File types](file-types.md): references can be PDFs, images or text files.
- [Results screen](results-screen.md): following a page reference into the right file.
- [API](../api/README.md): sending one file per named input from code.
