[Documentation](README.md) › Glossary

# Glossary

Every term with a special meaning in Document Engine, in alphabetical order. Each entry is short and links to
the page that explains the idea in full. For the same ideas in a learning order, read
[Concepts](start/concepts.md).

[A](#admission) · [B](#bucket) · [C](#call) · [E](#estimate) · [F](#file) · [G](#gateway) · [I](#input) ·
[J](#job) · [L](#lease) · [M](#map) · [O](#output) · [P](#page) · [Q](#queue) · [R](#reduce) · [S](#safety-margin) ·
[T](#task) · [U](#unit) · [V](#value-input) · [W](#warm-up)

## Admission

The decision to send one waiting call to the model now. It is made in the database, for one call at a time,
and only if the ledger shows room. See [The quota ledger](how-it-works/quota-ledger.md).

## Bucket

The gateway's way of limiting output: an allowance that each finished call draws down and that refills
steadily. The engine keeps its own picture of each model's bucket.
See [The quota ledger](how-it-works/quota-ledger.md).

## Bulk

One of the two priorities of a job. Bulk jobs give way to interactive jobs. See [Priority](#priority).

## Call

One request to a model and its reply. A step applied by Map makes one call per window.

## Citation

See [Page reference](#page-reference).

## Connection

A line between two blocks on the canvas. The connection into a step carries its
[instruction](#instruction), or makes the block at its other end a [reference](#reference).
See [Flow builder](guide/builder.md).

## Estimate

The builder's forecast of a run: number of calls, output tokens and cost. It comes from each step's settings,
and from real calls once a step has run. See [Estimates](how-it-works/estimates.md).

## Event

A record of one thing that happened in a job: a call admitted, a call finished, a step completed. The Run
screen is drawn from events. See [Run screen](guide/run-screen.md).

## Expected output

How many tokens the engine expects a call of a given step to produce. It starts from the step's setting and is
then learned from real calls. The ledger counts calls in flight at this figure.
See [The quota ledger](how-it-works/quota-ledger.md).

## Fake gateway

A stand-in for the model gateway, used for development and tests. It imitates timing and limits and returns
filler text. Nothing it shows is evidence about the real gateway.
See [The fake gateway](operations/fake-gateway.md).

## File

Anything uploaded for a flow to read: a PDF, an image or a text file. A file's name is a label; its file id
identifies it. See [File types](guide/file-types.md) and [Files screen](guide/files-screen.md).

## Filter

An [instruction](#instruction). It keeps the items whose earlier answer matches a rule, and runs the step once
for each kept item. It makes no model call of its own to decide. See [Instructions](guide/instructions.md).

## Flow

The recipe: sources, steps, outputs and the connections between them, drawn on a canvas. Built once, run many
times. See [Build a flow](guide/build-a-flow.md).

## Fold

An instruction shown in the library as coming later. It is not built.

## Gateway

The model endpoint the engine calls: the Databricks AI Gateway, which serves the Claude models and enforces
the quota.

## Input

Used in two senses. A step's **input** is the one connection it works through by its instruction, as opposed
to its [references](#reference). A flow's **inputs** are what a run must supply: its files, one per
[source](#source), and its [value inputs](#value-input).

## Instruction

How a step is applied to the items arriving on its input: [Map](#map), [Reduce](#reduce) or
[Filter](#filter). See [Instructions](guide/instructions.md).

## Interactive

One of the two priorities of a job, and the default. Interactive jobs go ahead of bulk jobs.
See [Priority](#priority).

## Item

One element of the list that moves along a connection. From a source, an item is a page. From a step, an item
is one answer. Every item records the pages it covers. See [Concepts](start/concepts.md#items).

## Job

One run of a flow on a particular set of files and values. See
[Jobs and tasks](how-it-works/jobs-and-tasks.md).

## Lease

The engine's claim on a call that is in flight. If the worker handling it stops, the lease runs out and the
call returns to the queue. See [Failures and recovery](how-it-works/failures-and-recovery.md).

## Ledger

The engine's running account of each model's quota: what has been used, what is in flight, what has drained
back. One row per model in the database. See [The quota ledger](how-it-works/quota-ledger.md).

## Map

An [instruction](#instruction). It runs the step once for each [window](#window) of consecutive items.
See [Instructions](guide/instructions.md).

## Output

A block that collects the answers of one step as a result of the flow, as text or as a table.
See [Results screen](guide/results-screen.md).

## Overlap

In a Map, how many items each window shares with the one before it, so that nothing is lost at the boundary
between windows. See [Instructions](guide/instructions.md).

## Page

The unit a file is made of. A PDF page, a whole image, or one page-sized piece of a text file.
See [File types](guide/file-types.md).

## Page reference

A marker in an answer that says where a statement came from: `[p. 12]`, `[pp. 12-14]`, or `[Invoice p. 2]` in
a flow with several sources. On the Results screen it opens that page.
See [Results screen](guide/results-screen.md).

## Preflight

A command that checks a setup cheaply before any real work: configuration, database, and a few tiny calls to
each model. See [Commands](operations/commands.md).

## Priority

Whether a job is interactive or bulk. The queue sends interactive tasks first.
See [Queue and priority](how-it-works/queue-and-priority.md).

## Profile

What the engine has learned about one step from real calls: typical output, typical duration. Used by the
ledger and by the estimate. See [Estimates](how-it-works/estimates.md).

## Publish

To make the current flow the version that outside programs run. See [Publishing a flow](guide/publishing.md).

## Queue

The waiting tasks of every job, in the order they will be sent: interactive before bulk, then by when the job
was submitted, then by position within the job. There is one queue per model.
See [Queue and priority](how-it-works/queue-and-priority.md).

## Quota

The tokens per minute the gateway allows for a model, shared by everything that uses that model.
See [The quota ledger](how-it-works/quota-ledger.md).

## Reduce

An [instruction](#instruction). It runs the step once, on all the items together.
See [Instructions](guide/instructions.md).

## Reference

Material a step is given whole on every call, beside the input it works through: another step's finished
answer, or an entire file. Drawn as a dotted connection.
See [Several files in one flow](guide/several-files.md).

## Rejection

A call the gateway refused because the quota was exceeded (HTTP status 429). The engine is built to avoid
them, and pauses briefly when one occurs. See [Under heavy load](how-it-works/heavy-load.md).

## Safety margin

A share of each model's allowance that the engine leaves unused, to absorb error in its estimates.
See [Settings](operations/settings.md).

## Schema

A step's output described as named fields. The engine checks the model's reply against it.
See [Steps](guide/steps.md).

## Source

A block where one file enters a flow. A flow may have several, each with a name.
See [Several files in one flow](guide/several-files.md).

## Step

A block that calls a model: a prompt, a model, and the shape of the answer. See [Steps](guide/steps.md).

## Task

One unit of work inside a job. Almost always one model call. See
[Jobs and tasks](how-it-works/jobs-and-tasks.md).

## Thinking

A model setting that lets the model reason before it answers. A step sets it to off, low, medium or high.
See [Steps](guide/steps.md).

## Unit

The smallest piece of a file that a flow handles. In practice, a [page](#page).

## Value input

A small value a run supplies beside its files, written into prompts as `{{Name}}`.
See [Value inputs](guide/value-inputs.md).

## Version

A numbered, saved copy of a flow. A job records the version it ran.
See [Publishing a flow](guide/publishing.md).

## Warm-up

One small call made before a step's many calls, so that the step's long prompt is cached and the calls that
follow pay less for it. See [Prompt caching](how-it-works/prompt-caching.md).

## Window

A group of consecutive items handed to a step in one call under Map. Set by window size and overlap.
See [Instructions](guide/instructions.md).

## Worker

The part of the application that sends calls to the model. One runs inside the application; more can be
started. See [Architecture](how-it-works/README.md).
