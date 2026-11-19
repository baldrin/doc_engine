# Demo notes: sprint planning, 2026-11-19

Talking notes for an informal walk-through of about five to eight minutes. Not the official demo (2026-12-01).

**Say this first:** the model replies today are simulated. The screens, the queue and the scheduling are the
real code; the text in the results is filler. The first run against our real gateway is the next step.

## The one-sentence version

Document Engine is one shared service where a file-processing job is built as a flow on a canvas, then run
from a screen or from one HTTP endpoint, with every job sharing one model quota.

## Why I built it

- Each request from the business has meant a new application: new hosting, new logging, new queueing, built
  differently each time.
- Hosting is about $33 a day per application on Databricks Apps, about $12,000 a year each.
- The applications compete for the same model quota without knowing about each other.
- Most of them do the same thing underneath: cut a file into pages, send pages to a model, combine the answers.

## Walk-through

Address: `http://localhost:8100`

| # | Where | Do | Say |
|---|---|---|---|
| 1 | **Flows** | Show the four sample flows. | "Each card is what would have been a separate application." |
| 2 | **Builder** | Open **Medical record summary**. Point at the two branches. | "Top branch: summarize every 4 pages with Sonnet, then one final summary with Opus. Bottom branch: Haiku classifies each page, a filter keeps the lab reports, Sonnet extracts the values from only those." |
| 3 | **Builder** | Click **Classify page**. Show the Prompt, Model and Output tabs. Click the connection after it to show the filter rule. | "A cheap model sorts pages so the expensive one only sees what matters. Model, prompt and output shape are settings, not code." |
| 4 | **Builder** | Point at the estimate in the header. | "Calls, tokens and cost, before anything is run." |
| 5 | **Test run** | Choose **Test run** and start it. | "Every call is a task in one queue. The gauges are the shared quota: the scheduler only sends a call when it fits, so the gateway never has to reject one." |
| 6 | **Results** | Open the results. Click a page reference. | "Every finding links back to the page it came from." (Text is filler today.) |
| 7 | **Builder** | Go back to the flow you just ran. Click **Summarize window**, open the **Model** tab, and point at **Learned so far: about N tokens** under Expected output tokens per call. | "It measures what each step really produces and plans with that, not with the configured guess. After three calls of a step, the scheduler and the cost estimate both use the measured figure." |
| 8 | **Activity** | Submit about 10 jobs, some interactive and some bulk. Confirm when asked. | "Ten jobs at once, one quota, interactive goes first, rejections stay at zero. Separate applications cannot do this, because none of them can see the others." |
| 9 | **Builder** | Open **Check an invoice against its order**, choose **API**. | "Publish a flow and any program can run it: send the flow name and the files, get a job id, poll for the result. That is the whole integration." |

If time is short, do 1, 2, 5 and 8.

Step 7 only shows a figure after the flow has run at least once on this machine, with a file chosen for its
source. Run it once before the meeting so the figure is there.

Optional, 1 minute: on **Flows**, choose **Duplicate** on a sample, rename it, change one prompt. "That is a new
process."

## What it does today

- **Flows built on a canvas:** sources, steps, outputs. Three instructions: Map (one call per window of pages),
  Reduce (one call over everything), Filter (keep items by a rule, no model call).
- **Per step:** prompt, model (Haiku, Sonnet or Opus), thinking level, text or structured output.
- **Several files in one flow,** and reference material sent with every call (the dotted lines).
- **Value inputs:** a flow can take settings, such as a tolerance, at run time.
- **PDF, image and text files.**
- **Page references** carried from the first step to the final output.
- **Estimates that correct themselves:** the engine measures what each step really produces and uses that
  for scheduling and for the cost estimate.
- **One scheduler for everything:** shared quota per model, interactive before bulk, retries, recovery when a
  worker dies.
- **Versions and publishing:** what callers run only changes when a flow is published again.
- **A public endpoint** to run a published flow by name.
- **A full record:** every call, its tokens and its cost are stored.
- **Written documentation** for users, developers and operators.

## What it means for new work

- A new request becomes a flow, not an application. Hosting, queueing, retries, logging and storage are
  already there.
- A proof of concept in a day or two, not a week or more. The time that remains is the part that matters:
  getting the prompts right with the business area.
- A fix or a new feature reaches every flow at once.
- Things that were too complex to build one at a time, such as several files checked against each other,
  are a few blocks.

## Time and money

- **Hosting:** one deployment in place of several. Four applications at $33 a day is about $48,000 a year;
  one is about $12,000. The saving is real only once the old ones are retired.
- **Development:** most of each new application's build is no longer needed.
- **Model cost:** a cheap model per step where it is enough, caching of repeated prompts, and a cost estimate
  before a run.
- **Quota:** fewer rejected and retried calls, and interactive work stays fast while bulk work runs.

## What is proven and what is not

- **Proven on our real gateway (the earlier proof of concept):** a scheduler keeps many jobs moving under one
  shared quota with no rejections, and interactive jobs stay fast under bulk load.
- **Not yet proven:** this codebase against the real gateway, and deployment on Databricks Apps with Lakebase.
  Those are the next two sessions.
- **Not built yet:** sign-in and job owners (planned through Databricks / Entra ID), batches of jobs in one
  request, a retention period for files.

## What it is not

It processes content as jobs. It is not for chat or anything that streams answers to a person as they type.
The claim is "most file-processing requests", not "everything".

## Next steps

1. First run against the real gateway.
2. Deploy to Databricks Apps with Lakebase.
3. Official demo on 2026-12-01.
4. Rebuild one of our existing applications as a flow and compare the output. That is the real proof.

## Likely questions

- **"Is it real?"** The scheduling result is, from the proof of concept on our gateway. This build has only
  run against a simulation so far.
- **"Who can use it?"** Today anyone who can reach it. Sign-in comes with the Databricks deployment.
- **"What if it goes down?"** Everything is in Postgres. Jobs survive a restart, and a call whose worker died
  is sent again.
- **"Can it replace application X?"** If X takes files in and gives results out, probably. If X is a chat, no.
