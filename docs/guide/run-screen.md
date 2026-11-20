[Documentation](../README.md) › [User guide](README.md) › The Run screen

# The Run screen

The Run screen shows one [job](../glossary.md#job) as it executes: the flow drawn with live progress on every
block, the shared quota of each model the flow uses, and a feed of what the engine is doing. A finished run can
be replayed. This page explains every panel and control, and is for anyone who starts or watches runs.

**On this page**

- [Open a run](#open-a-run)
- [The top bar](#the-top-bar)
- [The animated flow](#the-animated-flow)
- [The end-of-run card](#the-end-of-run-card)
- [The Scheduler panel](#the-scheduler-panel)
- [In flight, Rejections and the Interactive lane](#in-flight-rejections-and-the-interactive-lane)
- [Live events](#live-events)
- [Cancel a run](#cancel-a-run)
- [Replay a finished run](#replay-a-finished-run)
- [Go to the results](#go-to-the-results)

> **Screenshot to add:** `images/run-screen-overview.png`. A run of "Medical record summary" on the 150-page sample, about half way: the Summarize window step in progress with dots moving along its connection, the gauges partly filled, several lines in the Live events feed. Dark theme.

> **Not yet confirmed:** this screen has so far been used only with the fake gateway. Everything described
> here follows from how the screen is built, but none of it has been watched during a run on the real
> Databricks AI Gateway. That is planned for the first session against the real gateway.

## Open a run

You arrive here in one of three ways:

- by selecting **Start** in the [Test run dialog](test-runs.md);
- by selecting a row in the Jobs table of the [Activity screen](activity-screen.md);
- from the builder, through **Open that run** in a step's **View last outputs**.

The screen first loads everything the job has recorded so far, then follows it live. You can leave and come
back, or open the same run in two browsers: the screen is rebuilt from the engine's record of the run, so it
always shows the same thing.

## The top bar

| Part | Meaning |
|---|---|
| The trail above the title | **Activity** (a link to the [Activity screen](activity-screen.md)), then the flow's name (a link to the flow in the builder, while the flow still exists), then the flow version the job was started from (**v2**, or **draft** when no version had been saved), then the job's label, such as **Test run**. |
| The title | The name of the file the run reads. For a run on several files: the number of files and their total pages, for example **3 files · 7 pages**. Hover to read the file names. |
| The status | **Queued**: no call has been sent yet. **Running**. **Complete**. **Failed**. **Cancelled**. During a replay it can also read **Paused**. |
| **Interactive** or **Bulk** | The job's priority. See [Queue and priority](../how-it-works/queue-and-priority.md). |
| **Elapsed** | Time since the job was submitted, in minutes and seconds. It stops when the run ends. |
| **Calls done** | Model calls completed, out of the calls planned so far. |
| **Cancel** | Stops the run, after a confirmation. Shown until the run has ended. |
| **Replay** | Plays the run back. Shown once the run has ended. |
| **View results** | Opens the [Results screen](results-screen.md). Shown once the run is complete. |

The second number of **Calls done** grows during the run. Document Engine plans a step only when the step
before it has finished, because how much work a step has can depend on the earlier result: a
[Filter](instructions.md) does not know how many pages it keeps until they have been classified. So the total
starts with the first steps and rises as later ones are planned. Calls that warm the prompt cache are included.

Directly under the top bar, a thin line across the screen shows the same progress as a bar. It is green when
the run is complete and red when it failed or was cancelled.

## The animated flow

The large area shows the flow as it was when the job was submitted, laid out as in the builder. It cannot be
edited here. Drag the background to move the picture and scroll to zoom.

### Blocks

Each block is marked **SOURCE**, **STEP** or **OUTPUT**, and shows its name. On a run with one source, the
source block shows the file's name. On a run with several sources, each source block shows the source's name,
and the file's name appears when you hover over it.

Under the name, a source shows its number of pages and a step shows its model. To the right is the block's
status, and at the bottom a progress bar.

| Block | Status | Meaning |
|---|---|---|
| Any | **Waiting** | Nothing has happened on this block yet. A step waits until the block it works through, and every block it uses as a [reference](several-files.md), is done. |
| Source | **Ready** | The file is loaded and its pages are available to the steps. |
| Step with several calls | **12 / 50** | Calls done out of the calls this step makes. |
| Step with one call | **Working**, then **350 tok** | The call is in flight. Where the reply is streamed, the count of output tokens received so far is shown, and the bar fills towards the output the step is expected to produce. |
| Step | **50 done** | Every call of the step has finished. |
| Step | **Skipped** | The step had nothing to do, for example because the filter before it kept no pages. |
| Step | **Failed** | A call of this step failed for good, which ends the run. |
| Output | **Ready** | The output is complete and can be read on the Results screen. |

A spinning mark at the top right of a block means it is running, a green tick means it is done, and a warning
sign means it failed.

### Connections

The label on each connection names the [instruction](instructions.md) and shows its progress.

| Label | Second line | Meaning |
|---|---|---|
| **Map 4 / 1** | **12 / 50 windows**, or **waiting** | The step is applied to [windows](../glossary.md#window) of pages. The two numbers in the title are the window size and the overlap. The second line counts windows done. With a window of one page it counts **pages**. |
| **Reduce** | **50 → 1**, then **merging 50**, then **50 → 1 done** | The step makes one call over everything the block before it produced. |
| **Filter** | **9 of 150 kept**, or **waiting** | The step runs only on the items that match the rule. |
| **Reference** (a dotted line) | **waiting for it**, **ready**, **on every call**, **used** | The block at the start of the line is handed whole to the step on each of its calls. |

While a step is running, the connection into it glows and dots travel along it. A connection that has not
started is grey, and one that is finished is dimmed. Dotted reference lines do not animate.

### The legend

Below the flow, a legend gives the colours: blue for **Map**, teal for **Reduce**, orange for **Filter**, and a
glowing dot for **Items in motion**. At the right it reads **Live from the engine's event log.** During a
replay it reads **Replay of a recorded run. Times and counts are the real ones.**

## The end-of-run card

When the run ends, a card appears over the flow.

| Run | The card says |
|---|---|
| **Run complete** | The number of calls, the number of rejections, the time taken and the cost, then how many outputs are ready, for example **2 outputs ready**. A **Results** button opens the [Results screen](results-screen.md). |
| **Run failed** | The same figures, then the error that ended the run. The error starts with the name of the step it happened in. |
| **Run cancelled** | The same figures, then **Cancelled**. |

The cost is worked out from the tokens every call of the job actually used, at the prices configured for each
model.

## The Scheduler panel

The right-hand side of the screen starts with the **Scheduler** panel. It has one group of gauges for each
model the flow uses.

While the run is live, the line under the heading reads **One shared quota per model, kept just under the
ceiling**, and the gauges show the whole quota of each model, not this run's part of it. Every job running on
Document Engine draws on the same quota, so the gauges of two runs watched side by side are identical. They
update about once a second.

> **Screenshot to add:** `images/run-screen-scheduler-panel.png`. The Scheduler panel during a busy run: gauges for two models, one of them near its mark, the three tiles below, and the Live events feed with a Scheduler line.

### The line above the gauges

Beside the model's name is either **8 in flight · 42 ready** or **paused after a rejection**.

- **in flight**: calls to this model that have been sent and have not finished, from all jobs.
- **ready**: [tasks](../glossary.md#task) for this model that could be sent now and are waiting for room in
  the quota, from all jobs.
- **paused after a rejection**: the gateway rejected a call to this model, and Document Engine is sending it
  nothing for a moment. See [rejections](#rejections).

### The three gauges

| Gauge | What it shows | How to read it |
|---|---|---|
| **Output tokens per minute** | Output tokens of the calls that finished in the last 60 seconds, against the model's output limit per minute. | The model's limit is the full width of the bar. The mark near the right end is the ceiling the scheduler aims to stay under: the limit less a safety margin (5% unless changed in the [settings](../operations/settings.md)). A bar that sits just below the mark means the quota is fully used, which is what the scheduler is for. |
| **Burst budget in use** | The scheduler's own account of the output that counts against the model right now: output recently completed and not yet drained away, plus the expected output of every call in flight. It is set against the most the scheduler allows itself. | This is the gauge that decides whether the next call may be sent. When it is nearly full, ready tasks wait until it drains. It can be full while the per-minute gauge is still low, at the start of a burst. |
| **Input tokens per minute** | Input tokens of the calls that finished in the last 60 seconds, against the model's input limit per minute. Tokens read from the prompt cache are not counted. | Read it like the first gauge. It has the same mark. |

The numbers at the right of each gauge are the current value and the limit, shortened: **42k / 100k**.
Rejected calls add nothing to the per-minute gauges.

The limits and the reasoning behind the burst budget are explained in
[The quota ledger](../how-it-works/quota-ledger.md).

> **Note:** the quota belongs to the endpoint, and other applications may use the same endpoint. Document
> Engine cannot see their use, so the gauges show only what Document Engine itself has sent.

### After the run, and during a replay

Once the run has ended, the line under the heading changes to **This run's share of the quota**. Each model
then has a single gauge, **Output tokens per minute**, headed **last 60 s of this run**. It is worked out from
this run's own calls: the output of the run's calls that finished in the 60 seconds before the moment shown.
The burst budget and input gauges are not shown, because they describe the live state of the whole system.

## In flight, Rejections and the Interactive lane

Three tiles sit under the gauges. Unlike the gauges, the first two describe this run only.

### In flight

The number of this run's calls that have been sent and have not yet come back. It is cleared when the run is
cancelled or fails.

### Rejections

How many of this run's calls the gateway has rejected for exceeding a rate limit. The number is green at zero
and red otherwise.

A rejection does not lose work and does not fail the run. The rejected task goes back to the queue and is sent
again, and the rejection does not count against the task's retries. The model is paused briefly for every job,
and the feed records the rejection. A run with a few rejections still completes with full results; it takes a
little longer. Rejections mean that the endpoint was busier than the scheduler believed, most often because
something outside Document Engine was using it.
[Failures and recovery](../how-it-works/failures-and-recovery.md) describes this in detail.

### Interactive lane

Interactive jobs go before bulk jobs. This tile tells you how that affects the run you are watching.

| The run is | The tile reads | Meaning |
|---|---|---|
| Interactive | **This run** | This run is in the interactive lane: its tasks go ahead of all bulk work. |
| Interactive, ended or replayed | **Clear** | |
| Bulk | **Going first** (highlighted) | Interactive tasks are waiting somewhere in Document Engine, and they are sent before this run's tasks. Expect this run to slow down or pause until they are through. |
| Bulk | **Clear** | No interactive task is waiting. This run is not being held back by priority. |

## Live events

The lower part of the right-hand side is the **Live events** feed. It shows the nine most recent events, the
newest at the top. Each line has the time since the job was submitted, a coloured dot and a short text. Before
anything has happened it reads **Waiting for the first task…**. The small light beside the heading blinks while
the run is running, and turns green or red when it ends.

Not everything the engine records gets a line. The start of each ordinary call, for instance, moves the
counters and the blocks without adding one, so that the feed stays readable.

### The run as a whole

| Line | When it appears |
|---|---|
| **Job submitted · 150 pages · interactive** | The job was created. Pages are the total over all its files. |
| **Run complete · 0 rejections** | Every block has finished. |
| **Run failed ·** and the error | A call failed for good, and the run stopped. |
| **Run cancelled** | Someone selected **Cancel**. |

### Sources, steps and outputs

In these lines, *Name* stands for the name of the block.

| Line | When it appears |
|---|---|
| *Name* **loaded · 150 pages** | A source's file is ready. This comes straight after the job is submitted. |
| *Name* **· 50 tasks scheduled** | A step has been planned: the block it works through and all its references are done, and its calls have been put in the queue. |
| **Filter · 9 kept (**rule**)** | A step fed by a Filter was planned. The line gives how many items matched the rule, and the rule. |
| *Name* **· warming the prompt cache** | Before a step with several calls, one small call stores the step's fixed prompt in the model's cache, so the calls that follow can reuse it. The step's own calls wait for it. See [Prompt caching](../how-it-works/prompt-caching.md). |
| *Name* **· cache is warm** | That call finished, and the step's calls are released. |
| *Name* **· pages 5 to 8 done** | One call of a step with several calls finished. The pages are those the call covered. |
| *Name* **· page 12 · lab report** | The same, for a step that returns a schema: the line ends with a few words from the reply, here the page type a classifier chose. For a table it gives the number of rows. |
| *Name* **· 3,950 tokens** | The call of a step that makes only one call finished, with the output tokens it produced. |
| *Name* **· cut off at max output** | A call finished, but its reply reached the step's maximum output and was cut short. The result is kept and marked on the [Results screen](results-screen.md#truncated-output). |
| *Name* **· all 50 done** | Every call of a step has finished. |
| *Name* **· nothing to do** | A step had no items to work on, and was skipped. |
| *Name* **· ready** | An output is complete. |

### Trouble and recovery

| Line | When it appears | What happens next |
|---|---|---|
| **Gateway rejected a call (**limit**) ·** *Model* **paused 1 s** | The gateway refused a call because a rate limit was exceeded. The text in brackets is the limit that was hit, as the gateway reported it. | The task returns to the queue, and the model is paused for all jobs for the time shown. |
| *Name* **· retrying (**reason**)** | A call failed in a way that may pass: the gateway timed out or returned a server error, or the reply did not match the step's schema. | The task returns to the queue and is tried again, up to a limit (three attempts unless changed in the [settings](../operations/settings.md)). |
| *Name* **·** and an error | A call failed for good: the model declined the request, the reply was empty, the request was refused, or the retries ran out. | The run fails. Calls already in flight finish and their results are discarded. |
| *Name* **· warm-up failed, continuing without the cache** | The call that warms the prompt cache failed. | The run carries on. The step's calls are sent without the cache, which costs more but changes no result. |
| *Name* **· a lost call was returned to the queue** | The worker process that was making a call stopped responding, or the call ran past its time allowance. | The task is sent again by a working process. |

### Scheduler lines

| Line | When it appears |
|---|---|
| **Scheduler ·** *Model* **output budget at 92%, holding 40 tasks** | A model this run uses has tasks ready to send, and its burst budget is at least 80% full. The scheduler is holding work back on purpose, to stay inside the quota. |
| **Scheduler ·** *Model* **paused after a rejection, 40 tasks waiting** | The same situation while the model is paused after a rejection. |

These lines appear at most once every six seconds. They describe the state of the shared quota at that moment,
counting the tasks of all jobs, and are written by the screen itself while you watch. They are not part of the
run's record, so they are absent when you reload the page and during a replay.

### Colours

| Colour | Used for |
|---|---|
| Blue | The job being submitted, sources, steps being planned, and finished calls of a Map step |
| Teal | Finished calls of a Reduce step |
| Orange | Filters, retries, recovered calls, replies that were cut off, and cancellation |
| Purple | The prompt cache and the scheduler |
| Green | Steps, outputs and runs that finished |
| Red | Rejections and failures |

## Cancel a run

Select **Cancel** in the top bar. The browser asks for confirmation: **Cancel this run? Calls already sent will finish and be paid for; their replies are not used.** Confirm to cancel. The same can be done from the **Jobs** table of the [Activity screen](activity-screen.md#cancel-a-job).

- Tasks that had not been sent are dropped.
- Calls already in flight finish at the gateway, are paid for, and their results are discarded.
- The status becomes **Cancelled**, the feed reads **Run cancelled**, and the card over the flow reads
  **Run cancelled**.

A cancelled run cannot be resumed. It stays in the [Activity screen](activity-screen.md) and can be replayed.
**View results** is not offered for it. To run the flow again, start a new run.

Cancelling a run is also how a file it uses becomes [removable](files-screen.md#remove-a-file).

## Replay a finished run

Once a run has ended, whether complete, failed or cancelled, **Replay** plays it back from the beginning. A
replay sends nothing to the gateway and costs nothing: it re-reads the events the run recorded and shows them
at their original times.

> **Screenshot to add:** `images/run-screen-replay.png`. A replay in progress: the trail ending in "Replay", the label "Replay time", the speed buttons with 2× pressed, and the Pause and Exit replay buttons.

| Control | What it does |
|---|---|
| **Replay** | Starts the replay from the beginning, at 2× speed. Select it again during a replay to start over at the speed you have chosen. |
| **1×**, **2×**, **8×** | The speed. 1× is the speed the run really had. |
| **Pause** / **Resume** | Stops and continues the replay. While paused, the status reads **Paused**. |
| **Exit replay** | Returns to the finished run. |

During a replay:

- the trail above the title ends in **· Replay**, and **Elapsed** becomes **Replay time**;
- the blocks, connections, **Calls done**, the **In flight** and **Rejections** tiles and the feed all show the
  run as it was at that moment;
- the Scheduler panel shows this run's own output per minute, as described
  [above](#after-the-run-and-during-a-replay);
- the replay stops by itself just after the moment the run ended, and the end-of-run card appears, without
  the cost and without its **Results** button. **View results** in the top bar stays available for a complete
  run.

## Go to the results

When the status is **Complete**, open the results in either way:

- **View results** in the top bar;
- **Results** on the end-of-run card.

Both open the [Results screen](results-screen.md) for this job. Results are offered only for a complete run.

## See also

- [The Results screen](results-screen.md): reading what the run produced.
- [The Activity screen](activity-screen.md): every job and the quota of every model in one place.
- [Queue and priority](../how-it-works/queue-and-priority.md): why a bulk run waits for interactive work.
- [The quota ledger](../how-it-works/quota-ledger.md): what the gauges measure and how the scheduler decides.
- [Failures and recovery](../how-it-works/failures-and-recovery.md): rejections, retries and lost calls in depth.
