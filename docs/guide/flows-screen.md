[Documentation](../README.md) › [User guide](README.md) › The Flows screen

# The Flows screen

The Flows screen is the first screen of Document Engine. It lists every [flow](../glossary.md#flow), shows at a
glance how each one has been used, and is where you create, copy and delete flows. This page is for anyone who
builds or runs flows. It also describes the top bar, which is the same on every screen.

**On this page**

- [The top bar](#the-top-bar)
- [Light and dark](#light-and-dark)
- [The list of flows](#the-list-of-flows)
- [What a flow card shows](#what-a-flow-card-shows)
- [Create a flow](#create-a-flow)
- [Duplicate a flow](#duplicate-a-flow)
- [Delete a flow](#delete-a-flow)
- [The sample flows](#the-sample-flows)

> **Screenshot to add:** `images/flows-screen-overview.png`. The Flows screen with the four sample flows and one flow of your own, in the light theme, top bar visible.

## The top bar

Every screen has the same bar across the top.

| Part | What it does |
|---|---|
| The logo button, at the left | Returns to the Flows screen from anywhere. |
| The title beside the logo | Names the screen you are on, or the flow, file or run you are looking at. |
| **Flows** | Opens this screen. It stays highlighted while you are in the [builder](builder.md), because the builder edits one flow. |
| **Files** | Opens the [Files screen](files-screen.md): every file the engine holds. |
| **Activity** | Opens the [Activity screen](activity-screen.md): every job and the quota for every model. It stays highlighted while you look at a [run](run-screen.md) or its [results](results-screen.md). |
| The sun or moon button | Switches the whole site between light and dark. See below. |
| Buttons at the right | The actions of the current screen. On this screen there is one: **New flow**. |

## Light and dark

The button after **Activity** switches every screen between a light and a dark theme. In the light theme it
shows a moon and its tooltip reads **Switch to dark mode**; in the dark theme it shows a sun and reads
**Switch to light mode**.

Your choice is remembered in the browser you made it in, so it applies the next time you open Document Engine
in that browser. It is not tied to a person or an account: another browser or another computer starts fresh.
Until you make a choice, the site follows your system's light or dark setting. If the browser does not allow
sites to store anything, the choice lasts only until the page is reloaded.

## The list of flows

Below the heading is one card per flow. The sample flows come first, then your own flows, the most recently
edited first.

- While the list loads, the screen says **Loading flows…**.
- If there are no flows at all, it says **No flows yet. Create one to get started.**

Select a card anywhere outside its buttons to open that flow in the [builder](builder.md). With the keyboard,
move to the card with Tab and press Enter.

## What a flow card shows

> **Screenshot to add:** `images/flows-screen-card.png`. One flow card close up, a published sample flow that has been run at least once, so every line of the card has a value.

| On the card | Meaning |
|---|---|
| The name | The flow's name, as set in the builder. |
| **Sample** | A tag on the flows that come with Document Engine. A sample flow cannot be deleted. |
| The description | The flow's description, or **No description.** when it has none. |
| **v3**, or **Draft** | The number of the flow's latest saved version. **Draft** means no version has been saved yet. A new flow and a duplicate both start as drafts. Versions are explained in [Publishing](publishing.md). |
| **· Published**, or **· v2 is published** | Shown after the version when the flow is published, which means it can be run by name from outside Document Engine. **Published** means the version shown is the published one. **v2 is published** means a newer version has been saved since, and callers still get version 2. See [Publishing](publishing.md). |
| **5 blocks** | The size of the flow: the number of blocks on its canvas, less one. For a flow with one source this is the number of steps and outputs. |
| **12 runs** | How many jobs have been started from this flow, from any screen. Tests of a single step count too. |
| **Last run 3 h ago** | When the most recent of those jobs was submitted, or **Last run never**. |
| **Edited 2 d ago** | When the flow was last saved. Saving a version, publishing and unpublishing also count as edits. |
| **Duplicate** | Makes a copy. See below. |
| **Delete** | Deletes the flow. Not shown on sample flows. See below. |

Times are written as **just now** (under a minute), **5 min ago**, **3 h ago** or **2 d ago**.

## Create a flow

1. Select **New flow** in the top bar.
2. Document Engine creates a flow named **Untitled flow**, with an empty canvas, and opens it in the builder.

The flow exists from that moment. If you go back without adding anything, it stays in the list as an empty
draft until you delete it. [Build a flow](build-a-flow.md) walks through what to do next.

## Duplicate a flow

**Duplicate** on a card makes a copy of that flow and opens the copy in the builder.

- The copy is named after the original with **(copy)** added, and keeps its description, blocks, connections
  and value inputs.
- The copy is your own flow: it is a draft, it is not published, and it is not a sample, so it can be changed
  and deleted freely.
- The copy starts with no runs. The original is not changed.

Duplicating is the way to change a sample flow without losing the original.

## Delete a flow

1. Select **Delete** on the flow's card.
2. The browser asks: **Delete "name"? Its past runs stay in Activity.** Confirm to delete.

The flow and its saved versions are removed and this cannot be undone. Jobs that ran the flow are kept: they
remain in the [Activity screen](activity-screen.md) and their [results](results-screen.md) can still be opened,
because every job keeps its own copy of the flow it ran.

Sample flows have no **Delete** button.

## The sample flows

Four flows are installed with Document Engine, together with [sample files](files-screen.md#the-sample-files)
to run them on. Each sample flow already has its sample files chosen, so it can be run as it is. All four are
installed as version 1 and published.

| Flow | What it does | Sources |
|---|---|---|
| **Medical record summary** | Summarizes a long record with page references, and pulls lab results into a table. | One: **Patient record** |
| **Contract file review** | Briefs a contract file with page references, and pulls invoice lines into a table. | One: **Contract file** |
| **Compare two medication lists** | Reads two files in one call and reports what changed between the admission list and the discharge list. | Two: **Admission list**, **Discharge list** |
| **Check an invoice against its order** | Reads the order and the delivery note, then checks each invoice page against both. | Three: **Purchase order**, **Delivery note**, **Invoice** |

### Medical record summary

Two branches read the same file.

- **Summarize window** works through the record four pages at a time, each [window](../glossary.md#window)
  overlapping the next by one page ([Map](instructions.md)). **Final summary** then merges all the notes into
  one summary ([Reduce](instructions.md)). The output is **Summary with citations**, shown as text.
- **Classify page** labels every page with its type. **Extract lab values** runs only on the pages classified
  as a lab report ([Filter](instructions.md)). The output is **Lab results table**, shown as a table.

### Contract file review

The same shape as the medical flow, for a contract file.

- **Note the terms** works through the file three pages at a time with one page of overlap, and
  **Contract brief** merges the notes. The output is **Brief with citations**.
- **Classify page** labels every page, and **Extract invoice lines** runs only on the pages classified as an
  invoice. The output is **Invoice lines table**.

### Compare two medication lists

One step, **Compare the lists**, makes a single call. It works through the **Admission list** and receives
the **Discharge list** whole as a [reference](several-files.md). The output, **Differences with citations**,
has three sections: changes, unchanged medicines, and changes the discharge list does not explain.

The two sample lists differ on purpose, so there is something to find: one dose changed, one frequency
changed, one medicine stopped, and medicines started.

### Check an invoice against its order

- **Read the order** records what the purchase order lists, and **Read the delivery** records what the
  delivery note says arrived.
- **Check the invoice** works through the invoice one page at a time. On every call it receives the outputs of
  the two reading steps as references.
- **Verdict** merges the page checks into a short verdict that starts with *Pay in full*, *Pay in part* or
  *Do not pay yet*. The output is **Invoice verdict**.

This flow declares two [value inputs](value-inputs.md), which the **Check the invoice** step uses:

| Value input | Type | Default | Meaning |
|---|---|---|---|
| **Price tolerance** | Number | 0.5 | Largest unit price difference that still counts as agreeing with the order |
| **Accept delivery charges** | Yes / no | no | Let a delivery charge pass when the order did not list one |

The sample invoice differs from the order and the delivery note on purpose: one quantity is billed above what
was delivered, one unit price is higher than ordered, and one charge was never ordered.

> **Not yet confirmed:** the sample flows have run only against the fake gateway, which does not read the
> files. Whether a real model finds the differences planted in the sample files, and writes its page
> references in the expected form, will be checked in the first session against the real gateway.

## See also

- [Build a flow](build-a-flow.md): what to do after **New flow**.
- [The builder](builder.md): the screen a flow card opens.
- [The Files screen](files-screen.md): the sample files these flows run on.
- [Start a test run](test-runs.md): run a flow once and watch it.
- [Publishing](publishing.md): versions, and what **Published** allows.
