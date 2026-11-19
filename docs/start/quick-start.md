[Documentation](../README.md) › Start here › Quick start

# Quick start

Ten minutes with a sample flow: run it, watch it, read the results, then run the same flow from a command
line. You need the address of a running Document Engine. If nobody has set one up for you, follow
[Local setup](../operations/local-setup.md) first; it ends with the application at `http://localhost:8000`.

**On this page**

- [1. Open a sample flow](#1-open-a-sample-flow)
- [2. Run it](#2-run-it)
- [3. Watch the run](#3-watch-the-run)
- [4. Read the results](#4-read-the-results)
- [5. Change a value and run again](#5-change-a-value-and-run-again)
- [6. Run it from code](#6-run-it-from-code)
- [Where to go next](#where-to-go-next)

## 1. Open a sample flow

Open the application in a browser. The first screen is **Flows**. Four sample flows are installed. Choose
**Check an invoice against its order**: it is the smallest, at six model calls.

> **Screenshot to add:** `images/flows-screen-samples.png`. The Flows screen with the four sample flow cards, the pointer over "Check an invoice against its order".

The flow opens in the [flow builder](../guide/builder.md). Read it from left to right:

- three **sources** on the left, one for each file: *Purchase order*, *Delivery note*, *Invoice*;
- two steps that read the order and the delivery note;
- a step, **Check the invoice**, that reads the invoice one page at a time, with the other two steps' answers
  as [references](concepts.md#reference) (the dotted lines);
- a last step, **Verdict**, that combines the page-by-page checks into one answer;
- one **output** on the right.

> **Screenshot to add:** `images/builder-sample-three-way.png`. The builder showing the whole "Check an invoice against its order" flow, nothing selected, so the right-hand panel shows the flow's two inputs.

Each source already has a sample file chosen. The top bar shows the estimate for those files: the number of
calls, the output tokens and the cost.

## 2. Run it

1. Choose **Test run** in the top bar.
2. The dialog lists a file for each source and the flow's two [value inputs](concepts.md#value-input),
   **Price tolerance** and **Accept delivery charges**, filled with their defaults. Leave everything as it is.
3. Choose **Start**.

> **Screenshot to add:** `images/test-run-dialog-three-way.png`. The Test run dialog for the sample flow: three file pickers, the two value inputs at their defaults, Priority set to Interactive.

More about this dialog: [Test runs](../guide/test-runs.md).

## 3. Watch the run

The application moves to the **Run** screen. The same flow is drawn again, and now it is live: each step fills
in as its calls finish, the gauges show how much of each model's quota is in use, and the feed on the side
lists what is happening.

> **Screenshot to add:** `images/run-screen-in-progress.png`. The Run screen part-way through the sample job: two steps complete, the third running, quota gauges and the event feed visible.

This job is over in well under a minute. A long file looks the same, with more calls. Every part of the
screen is explained in [Run screen](../guide/run-screen.md).

## 4. Read the results

When the run completes, choose **View results**.

The output is the verdict on the invoice. The sample files disagree on purpose: one quantity, one unit price,
and one line, a delivery charge, that was never ordered. Each statement ends with a page reference such as
`[Invoice p. 2]`. Select one and that page opens beside the text.

> **Note:** on a setup that uses the [fake gateway](../operations/fake-gateway.md), the text is filler. The
> fake gateway imitates the model's timing and limits, not its reading.

> **Screenshot to add:** `images/results-screen-page-open.png`. The Results screen for the sample job with a page reference selected and the invoice page shown beside the text.

More: [Results screen](../guide/results-screen.md).

## 5. Change a value and run again

Go back to the flow and choose **Test run** again. This time set **Price tolerance** to `10` and
**Accept delivery charges** to **Yes**, then **Start**.

The flow is the same and the files are the same, but the step that checks the invoice was told different
limits. With a tolerance of 10 the price difference should pass, and the delivery charge is now accepted;
the wrong quantity should still be reported. That is what value inputs are for: one flow, adjusted by each run.

> **Not yet confirmed:** that a real model acts on these values as intended. The sample has so far run only
> against the fake gateway, which does not read prompts. See [Limits](../operations/limits.md).

## 6. Run it from code

1. In the builder, choose **API** in the top bar. If the panel says the flow is not published, close it,
   choose **Publish**, and open the panel again.
2. The panel shows three commands. Copy the first into a terminal, replace the three file names with files of
   your own, and run it.

```bash
curl -X POST 'http://localhost:8000/api/v1/flows/check-an-invoice-against-its-order/jobs' \
  -F 'Purchase order=@purchase-order.pdf' \
  -F 'Delivery note=@delivery-note.pdf' \
  -F 'Invoice=@invoice.pdf' \
  -F 'values={"Price tolerance":0.5,"Accept delivery charges":false}'
```

3. The reply holds a `job_id`. Use it in the second command to check the status, and in the third to fetch
   the results once the status is `done`.

The job also appears on the **Activity** screen, labelled `API`, and can be opened and watched like any other.

> **Screenshot to add:** `images/builder-api-panel.png`. The "Run from code" panel for the sample flow, showing the files, the values and the three commands.

More: [Running a flow from code](../api/README.md).

## Where to go next

- [Build a flow](../guide/build-a-flow.md): make your own from an empty canvas
- [Concepts](concepts.md): the words used on every screen
- [Instructions](../guide/instructions.md): Map, Reduce and Filter in depth
- [Under heavy load](../how-it-works/heavy-load.md): start ten jobs at once and see what the scheduler does
