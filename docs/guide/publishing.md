[Documentation](../README.md) › [User guide](README.md) › Publishing

# Publishing

Publishing makes a flow available to be run from code, by its name. This page explains the difference between a draft, a saved version and the published version, what publishing makes available, the rule about names, the **API** panel, and **Unpublish**. It is for anyone who decides when a flow is ready for others to call.

**On this page**

- [Draft, version, published version](#draft-version-published-version)
- [Save version](#save-version)
- [Publish](#publish)
- [What publishing makes available](#what-publishing-makes-available)
- [The name rule](#the-name-rule)
- [Edits are not live until you publish again](#edits-are-not-live-until-you-publish-again)
- [The API panel](#the-api-panel)
- [Unpublish](#unpublish)

## Draft, version, published version

A flow exists in up to three forms at once.

| Form | What it is | How it is made | Who uses it |
|---|---|---|---|
| **Draft** | The flow as it is on the canvas. | Saved by the builder by itself, after every change. | The builder, the estimate, and test runs. |
| **Version** | A numbered copy of the flow, taken at one moment: v1, v2, v3. | **Save version**, or **Publish**. | A record of the flow at that moment. |
| **Published version** | The one version that callers run. | **Publish**. | Callers of the [API](../api/README.md). |

A flow has at most one published version. The badge beside the flow's name in the [builder](builder.md#version-badge) shows where things stand:

| Badge | Meaning |
|---|---|
| **New · Draft** | No version yet. |
| **v3 · Draft** | The flow has been changed since version 3 was made. |
| **v3 · Saved** | Version 3 is the latest version. It is not the published one. |
| **v3 · Published** | Version 3 is the latest version, and callers run it. |

On the [Flows screen](flows-screen.md), a flow that has a published version is marked **Published** beside its version number.

> **Note:** The four sample flows are published when they are installed, so the API has something to call from the start.

## Save version

**Save version**, in the builder's top bar, stores the flow as it is now as the next numbered version, and confirms with **Saved as v4**.

- It does not change what callers run.
- It does not check the flow. A flow with problems can be saved as a version.
- Each use makes a new version number, whether or not anything changed.

Use it to mark a state you may want to refer to: before a large change, or after a test run that went well. A test run records the number of the latest version at the time it was started; the flow it actually runs is the draft on the canvas.

## Publish

**Publish**, in the builder's top bar, does three things in one action:

1. It checks the flow. If there are problems, nothing is published: the message reads **Fix the problems before publishing.** and the problem list opens over the canvas.
2. It checks the flow's name against the [name rule](#the-name-rule).
3. It stores the flow as it is now as the next numbered version, makes that version the published one, and confirms with **Published as v4**.

The badge turns green and reads **v4 · Published**.

You do not need to choose **Save version** first. **Publish** always publishes the flow as it is on the canvas at that moment, as a new version.

> **Screenshot to add:** `images/builder-published-badge.png`. The builder's top bar just after publishing: the flow name with the green badge "v4 · Published", and the buttons Validate, Test run, Save version, API and Publish.

## What publishing makes available

Once a flow is published, a program can:

- look up what the flow needs: its file inputs, its [value inputs](value-inputs.md) with their types and defaults, and its outputs;
- start a job on the published version by sending the files and values;
- check the job's status until it is done;
- fetch the results;
- cancel the job.

The flow is addressed by its name, or by its flow id. In a name, upper and lower case, spacing and punctuation do not matter, so `Contract file review` and `contract-file-review` are the same flow.

Everything a caller sends is checked before a job exists. A request with a missing file, a wrong value or an unknown field is refused, and creates no job. The endpoint itself, with every address, field and error, is described in the [API](../api/README.md) pages.

A flow that is not published cannot be started from code: a caller who names it is told that the flow exists but is not published. Publishing changes nothing about how you work in the builder: test runs and the [Activity screen](activity-screen.md) work with unpublished flows as well.

> **Not yet confirmed:** This codebase, including the endpoint for published flows, has run only against the fake gateway. Calling a published flow against the real gateway has not been done yet.

## The name rule

**Two published flows cannot share a name.** Callers run a flow by its name, so the name must lead to exactly one flow.

Names are compared the way callers may write them: without regard to upper and lower case, spacing or punctuation. `Invoice check`, `invoice-check` and `INVOICE  CHECK!` are all the same name.

| Situation | What happens when you choose Publish |
|---|---|
| Another published flow has the same name | Refused: **Another published flow is already named "…". Callers run a flow by its name, so rename this one before publishing.** |
| The name has no letters or digits | Refused: **Give the flow a name before publishing. Callers run it by that name.** |

Unpublished flows may share names freely, with each other and with a published flow. The rule only applies at the moment of publishing. Remember that the sample flows are published: a copy of a sample must be renamed before it can be published. A flow made with **Duplicate** gets ` (copy)` added to its name, which is already enough to make it different.

> **Note:** The name callers use is the name the flow had when it was published. Renaming a published flow in the builder changes nothing for callers until you publish again; from then on callers must use the new name. The flow id never changes, so a caller that uses the id is unaffected by a rename. When the two names differ, the **API** panel says which name callers use.

## Edits are not live until you publish again

Callers always run the published version. Changes you make in the builder after publishing, to prompts, connections, models, inputs or anything else on the canvas, are saved to the draft and have no effect on what callers run.

This means you can work on a published flow safely:

1. Edit the flow. The badge changes to **v4 · Draft**. Callers still run version 4.
2. Test the changes with **Test run**, which uses the draft.
3. Optionally choose **Save version**. The badge reads **v5 · Saved**. Callers still run version 4.
4. When the changes are ready, choose **Publish**. The flow becomes version 6 and callers run it from then on.

Jobs that are already running are not affected by publishing: each job works from its own copy of the flow, taken when it was submitted.

If a change alters what the flow needs, such as a new required value input, a renamed input or a renamed source, callers must change what they send at the moment you publish. Tell them first.

The one exception is the flow's name, as described under [The name rule](#the-name-rule).

## The API panel

**API**, in the builder's top bar, opens a panel titled **Run "**_flow name_**" from code**. It shows what a caller needs to know, with commands ready to copy.

### When the flow is not published

The panel says that the flow is not published, so it cannot be run from code yet, and points to **Publish** in the top bar.

### When the flow is published

| Part | What it shows |
|---|---|
| First line | **Callers run version N of this flow by its name.** followed by either **It matches what is on the canvas.** or **Changes made since then are not live until you publish again.** |
| **Files** | One row per source: the name of the file input, and what it accepts (a PDF, an image or a text file). A flow with one source has one row. |
| **Values** | One row per value input: its name, its type (with the choices of a choice input), and either **required** or its default. **None** when the flow has no value inputs. |
| **1. Start a job. The reply holds the job id.** | A `curl` command that sends one file per source, and the values, to the flow's address. |
| **2. Check its status until it is done.** | A `curl` command for the job's status. |
| **3. Fetch the results.** | A `curl` command for the job's results. |
| Closing note | Replace the file names with your own files and `JOB_ID` with the id from step 1. A file already stored can be sent by its id instead. |
| **Unpublish** | See [Unpublish](#unpublish). |

Each command box has a **Copy** button.

The commands are written for this flow:

- The address uses this installation's own address and the flow's name in lower case with hyphens, for example `/api/v1/flows/check-an-invoice-against-its-order/jobs`.
- With one source, the file is sent in a field named `file`. With several, each file is sent in a field named after its source.
- The example file names are made from the source names and end in `.pdf`. They are placeholders: send any PDF, image or text file.
- The `values` field holds an example value for every input: its default when it has one, otherwise a sample of the right type.

For the sample flow **Check an invoice against its order**, the first command looks like this:

```bash
curl -X POST 'https://your-installation/api/v1/flows/check-an-invoice-against-its-order/jobs' \
  -F 'Purchase order=@purchase-order.pdf' \
  -F 'Delivery note=@delivery-note.pdf' \
  -F 'Invoice=@invoice.pdf' \
  -F 'values={"Price tolerance":0.5,"Accept delivery charges":false}'
```

The panel is a starting point. The [API](../api/README.md) pages are the full reference.

> **Screenshot to add:** `images/builder-api-panel.png`. The panel "Run "Check an invoice against its order" from code" open over the builder: the line about the published version, the Files list with three inputs, the Values list with two inputs and their defaults, the three command boxes each with a Copy button, and the Unpublish button at the bottom right.

## Unpublish

**Unpublish** is at the bottom of the **API** panel of a published flow.

1. Open the flow in the builder and choose **API**.
2. Choose **Unpublish**.
3. Confirm the question: **Unpublish "…"? Callers will no longer be able to start it. Jobs already started carry on.**

After that:

- Callers can no longer start the flow. A caller who names it is told that the flow exists but is not published.
- Jobs that were already started carry on to the end, and their status and results stay available.
- The flow, its draft and all its versions are kept. Only the mark saying which version is published is removed. The badge returns to **Saved**.
- The flow's name is free for another flow to publish under.

To make the flow available again, choose **Publish**. That publishes the flow as it is on the canvas now, as a new version; there is no action that re-publishes an earlier version.

## See also

- [API](../api/README.md): the endpoint that runs published flows, with addresses, fields and errors.
- [Flow builder](builder.md#the-top-bar): where **Save version**, **API** and **Publish** are.
- [Test runs](test-runs.md): checking a draft before publishing it.
- [Value inputs](value-inputs.md): the values a caller sends with the files.
- [Several files in one flow](several-files.md): the named file inputs a caller sends.
