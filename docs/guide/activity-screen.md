[Documentation](../README.md) › [User guide](README.md) › The Activity screen

# The Activity screen

The Activity screen shows everything Document Engine is doing: every [job](../glossary.md#job), the order in
which waiting jobs are served, and the quota of every model. It is also where you submit several jobs at once.
This page explains every part of the screen, and is for anyone who runs flows or keeps an eye on the system.

**On this page**

- [Open the screen](#open-the-screen)
- [The summary tiles](#the-summary-tiles)
- [Shared quota, by model](#shared-quota-by-model)
- [The Jobs table](#the-jobs-table)
- [Queue order](#queue-order)
- [Open a run](#open-a-run)
- [Submit jobs](#submit-jobs)
- [The confirmation for 4 or more jobs](#the-confirmation-for-4-or-more-jobs)

> **Screenshot to add:** `images/activity-screen-overview.png`. The Activity screen while several jobs run: tiles at the top, quota gauges for three models, a Jobs table with a mix of queued, running and done jobs of both priorities, and the Submit jobs form at the right.

## Open the screen

Select **Activity** in the [top bar](flows-screen.md#the-top-bar). Beside the title, a badge reads **Working**
while any listed job is queued or running, and **Idle** otherwise.

The screen keeps itself up to date. The tiles and the quota gauges update about once a second. The Jobs table
refreshes every second while a job is queued or running, and every four seconds when everything is quiet.

## The summary tiles

Five tiles across the top summarize the whole system, across all jobs and all models.

| Tile | Meaning |
|---|---|
| **Jobs running** | Jobs that have had at least one call sent and have not ended. |
| **Jobs queued** | Jobs that have been submitted and have had no call sent yet. |
| **Calls in flight** | Model calls that have been sent and have not come back, over all models. |
| **Rejections, last 60 s** | Calls the gateway rejected for exceeding a rate limit in the last minute. Green at zero, red otherwise. |
| **Interactive lane** | **Clear** when no interactive task is waiting. Otherwise, for example, **12 calls waiting**, and the tile is highlighted: that many tasks of interactive jobs are ready and will be sent before any bulk task. |

## Shared quota, by model

This panel has one card for every model Document Engine is configured with, whether or not a job is using it.
Until the first figures arrive it reads **Connecting…**.

Each card has a line with the model's name and either **8 in flight · 42 ready** or **paused after a
rejection**, followed by three gauges:

| Gauge | What it shows |
|---|---|
| **Output tokens per minute** | Output tokens of the calls that finished in the last 60 seconds, against the model's output limit per minute. |
| **Burst budget in use** | The scheduler's own account of the output that counts against the model right now, including the expected output of calls in flight, against the most it allows itself. This gauge decides whether the next call may be sent. |
| **Input tokens per minute** | Input tokens of the calls that finished in the last 60 seconds, against the model's input limit per minute. |

As the note at the top of the panel says, **the mark on each bar is the ceiling the scheduler stays under**:
the model's limit less a safety margin. A card is highlighted while its model is paused after a rejection.

Under the **Submit jobs** panel, one line gives figures for the worker inside this web process: the median and 95th percentile time one admission decision took, in milliseconds, and the most calls it has had in flight at once. The figures start again when the process restarts, and with several instances each shows its own.

These are the same gauges as on the Run screen, where they are explained at length: see
[The Scheduler panel](run-screen.md#the-scheduler-panel). The difference is that the Run screen shows only the
models one flow uses, and this screen shows them all.

> **Note:** the quota belongs to the endpoint, which other applications may share. Document Engine cannot see
> their use. The gauges show only what Document Engine itself has sent.

## The Jobs table

The table lists the 80 most recently submitted jobs, the newest at the top: test runs from the builder, jobs
submitted from this screen, and jobs started by callers of the public endpoint or from the command line.

| Column | Meaning |
|---|---|
| **Queue** | The job's place in the queue, as **#1**, **#2** and so on. Empty for a job that has ended. See [Queue order](#queue-order). |
| **Job** | In bold, the job's label: **Test run**, **Step test:** and a step's name, or **Interactive 3** and **Bulk 2** for jobs submitted together. Below it, the flow's name and the names of the files the job reads. |
| **Priority** | **Interactive** or **Bulk**. |
| **Status** | **Queued**, **Running**, **Done**, **Failed** or **Cancelled**. The dot beside **Running** blinks. |
| **Progress** | A bar and two numbers: model calls done out of the calls planned so far. The second number grows as later steps of the flow are planned; see [the Run screen](run-screen.md#the-top-bar). The bar is purple for an interactive job, blue for a bulk job, green when the job is done, and red when it failed or was cancelled. |
| **In flight** | How many of the job's calls are out at the gateway now. Empty when there are none. |
| **Rejections** | How many of the job's calls the gateway rejected for exceeding a rate limit. Red when above zero. A rejected call is sent again, so rejections slow a job without failing it. |
| **Time** | Minutes and seconds from the moment the job was submitted until it ended, or until now if it is still going. Time spent waiting in the queue is included. |

When there are no jobs at all, the table reads **No jobs yet. Submit one on the right, or start a test run
from a flow.**

## Queue order

The **Queue** column numbers the jobs that are queued or running, in the order Document Engine serves them:

1. interactive jobs before bulk jobs;
2. within the same priority, the job submitted earlier first.

Running jobs keep a number, because a running job still has tasks waiting to be sent. A job's number falls as
the jobs ahead of it finish.

The number is a guide to which job is served first, not a promise that the others stand still. The order is
applied separately for each model, to the next task that is due to be sent. A bulk job therefore still makes
progress on a model that no interactive job is using, and a later job is sent work whenever the jobs ahead of
it have nothing ready for that model, for example while they wait for a step to finish.
[Queue and priority](../how-it-works/queue-and-priority.md) describes the rule exactly.

> **Note:** the numbering is worked out from the jobs in the table. If more than 80 jobs were submitted since
> an unfinished job, that job is no longer listed and the numbers start after it.

## Open a run

Select any row of the Jobs table to open that job's [Run screen](run-screen.md). This works for jobs in every
state: a queued or running job is shown live, and a finished one can be replayed there. For a complete job,
the Run screen leads on to the [Results screen](results-screen.md).

## Submit jobs

The **Submit jobs** form at the right starts one or more jobs on a flow, all at the same moment. Use it to run
a flow outside the builder, or to see how Document Engine shares the quota among many jobs.

> **Screenshot to add:** `images/activity-screen-submit-jobs.png`. The Submit jobs form with "Check an invoice against its order" chosen: three file fields named after the sources, the Values section, Interactive jobs 2, Bulk jobs 3, and the button reading "Submit 5 jobs".

### The fields

| Field | What to enter |
|---|---|
| **Flow** | The flow to run. The list holds every flow on the [Flows screen](flows-screen.md), samples included. |
| **File** | The file the flow reads. A flow with [several sources](several-files.md) shows one field for each source instead, labelled with the source's name. Each entry in the list gives the file's name and its size, such as **12 pages**. |
| **Values** | One field for each [value input](value-inputs.md) the flow declares. Not shown when the flow declares none. |
| **Interactive jobs** | How many interactive jobs to start. Starts at 1. |
| **Bulk jobs** | How many bulk jobs to start. Starts at 0. |

More about each:

- **Flow.** The jobs run the flow's published version. If the flow is not published, they run its latest
  saved version, and if no version has been saved yet, the draft. A line under the field says which one will
  run. Changes made in the builder since that version are not run from here; use **Test run** in the builder
  for those.
- **File.** For a sample flow, the file fields are filled in with its sample files. For your own flows, a
  field is filled in only when a file has exactly the same name as the source; otherwise it reads
  **Choose a file**. The file you chose for a source in the builder is not carried over to this form. The list
  does not
  include files sent by callers of the public endpoint (see
  [the API tag](files-screen.md#the-sample-and-api-tags)), and there is no upload button in this form: upload
  new files on the [Files screen](files-screen.md) first, then reload this screen.
- **Values.** The fields work as in the Test run dialog; see [Values](test-runs.md#values). A field left empty
  uses the input's default, and an input marked **Required** must be filled in. The values of your last run of
  this flow from this browser are filled in for you.
- **Interactive jobs** and **Bulk jobs.** Every job gets the same files and the same values. One submission
  can start between 1 and 50 jobs in total.

The note under the counts sums up what happens: **All jobs are submitted at the same moment. Interactive jobs
go first; within a class, the job submitted earlier goes first.**

### Submit

The button at the bottom reads **Submit 1 job**, **Submit 5 jobs** and so on, following the two counts. It is
greyed out while:

- both counts are zero;
- a source has no file chosen;
- an input marked **Required** has no value.

When you select it:

1. Document Engine checks the flow, the files and the values. If anything is wrong, no job is created and a
   message at the bottom of the screen says what, naming the value input or the source concerned.
   [When something is missing](test-runs.md#when-something-is-missing) lists the cases.
2. If the total is 4 or more, a confirmation is asked for first. See the next section.
3. The jobs are created and a message confirms it, for example **5 jobs submitted**.

You stay on the Activity screen. The new jobs appear at the top of the Jobs table, labelled **Interactive 1**,
**Interactive 2**, and **Bulk 1**, **Bulk 2**. A job submitted on its own is labelled **Interactive** or **Bulk**. Select a row to watch that job.

## The confirmation for 4 or more jobs

When one submission holds 4 or more jobs, counting interactive and bulk together, Document Engine does not
start them straight away. A dialog titled **Start a saturating run?** appears instead.

> **Screenshot to add:** `images/activity-screen-saturation-confirmation.png`. The dialog "Start a saturating run?" after submitting 10 jobs, showing the warning, the gateway line, and the Cancel and "Start 10 jobs" buttons.

The dialog says how many jobs you asked for, and warns that this many **at once can saturate the endpoint and
slow other applications in the workspace**. Below that it names the gateway the calls go to and reminds you
that they cost real money.

| Button | Effect |
|---|---|
| **Cancel** | Closes the dialog. Nothing is started. The form keeps what you entered. |
| **Start 10 jobs** (with your number) | Starts the jobs. |

### Why it asks

A single job rarely needs the whole quota of a model. Several jobs started together do: the scheduler will,
correctly, send as much work as the limits allow until all of them are done. That is what it is for, and
Document Engine's own jobs stay in order while it happens.

The cost falls on others. The limits belong to the endpoint, and the endpoint may serve other applications in
the same workspace. While Document Engine holds the quota at its ceiling, those applications find little left
for themselves and are slowed or rejected. Document Engine cannot see their traffic, so it cannot make room
for them by itself. The confirmation is there so that a person decides, knowing this, that now is an acceptable
moment. [Heavy load](../how-it-works/heavy-load.md) describes what happens while the quota is saturated.

The number that triggers the confirmation is 4 unless your administrator changed `server.saturating_jobs`; see
[Settings](../operations/settings.md).

> **Tip:** leave at least a minute between two saturating runs, so that the quota has drained and the
> scheduler's picture of it is accurate again.

## See also

- [The Run screen](run-screen.md): one job in detail, with the gauges explained.
- [Start a test run](test-runs.md): a single run from the builder, and how the value fields work.
- [Queue and priority](../how-it-works/queue-and-priority.md): the order jobs and tasks are served in.
- [Heavy load](../how-it-works/heavy-load.md): what a saturating run does to the quota.
- [The Files screen](files-screen.md): upload the files this form offers.
