# Document Engine documentation

Document Engine turns a long or complicated reading task into a **flow**: a set of model calls that a person
arranges on a canvas, tests on a file, and then makes available to other programs. Behind every flow, one
scheduler decides which model call goes next, so that many jobs share one model quota without being rejected
and without slow jobs holding up quick ones.

This is the map of the documentation. Every page links onward, so you can start anywhere.

## Start here

| If you want to | Read |
|---|---|
| Understand what the application is and what it is for | [Overview](start/overview.md) |
| Learn the dozen words the rest of the documentation uses | [Concepts](start/concepts.md) |
| See it work in ten minutes | [Quick start](start/quick-start.md) |
| Build your first flow, step by step | [Build a flow](guide/build-a-flow.md) |
| Call a flow from your own program | [Running a flow from code](api/README.md) |
| Understand how it copes with a heavy workload | [Under heavy load](how-it-works/heavy-load.md) |
| Install it or deploy it | [Setup and operations](operations/README.md) |
| Look up a word | [Glossary](glossary.md) |

## The four parts

### [User guide](guide/README.md)

For people who build and run flows in the browser.

- **Learn by doing:** [Build a flow](guide/build-a-flow.md)
- **The screens:** [Flows](guide/flows-screen.md) · [Flow builder](guide/builder.md) ·
  [Files](guide/files-screen.md) · [Run](guide/run-screen.md) · [Activity](guide/activity-screen.md) ·
  [Results](guide/results-screen.md)
- **Building blocks:** [Instructions: Map, Reduce, Filter](guide/instructions.md) · [Steps](guide/steps.md) ·
  [Several files in one flow](guide/several-files.md) · [Value inputs](guide/value-inputs.md) ·
  [File types](guide/file-types.md)
- **Running and sharing:** [Test runs](guide/test-runs.md) · [Publishing a flow](guide/publishing.md)

### [API](api/README.md)

For developers whose programs run published flows.

- [Running a flow from code](api/README.md): the model, and a complete run in three requests
- [Reference](api/reference.md): every request, reply and error code
- [Examples](api/examples.md): complete clients in Python and shell

### [How it works](how-it-works/README.md)

For anyone who wants to know what happens underneath, and why it holds up under load.

- [Architecture](how-it-works/README.md): one process, one database, one quota
- [Jobs and tasks](how-it-works/jobs-and-tasks.md): from a submitted job to its results
- [Queue and priority](how-it-works/queue-and-priority.md): how the engine decides what goes first
- [The quota ledger](how-it-works/quota-ledger.md): how many jobs share one model quota
- [Under heavy load](how-it-works/heavy-load.md): many jobs waiting, each with many calls
- [Prompt caching](how-it-works/prompt-caching.md): paying for a long prompt once
- [Failures and recovery](how-it-works/failures-and-recovery.md): what happens when something goes wrong
- [Estimates](how-it-works/estimates.md): where the builder's calls, tokens and cost figures come from

### [Setup and operations](operations/README.md)

For the people who install, configure and look after the application.

- [Local setup](operations/local-setup.md) · [Deploying to Databricks Apps](operations/databricks.md)
- [Settings](operations/settings.md) · [Commands](operations/commands.md)
- [Monitoring](operations/monitoring.md) · [Troubleshooting](operations/troubleshooting.md)
- [Limits and what is not confirmed](operations/limits.md) · [The fake gateway](operations/fake-gateway.md)
- [The first session on the real gateway](operations/first-real-session.md)

## How to read these pages

- Every page begins with a line showing where it sits, and ends with **See also**.
- Words with a special meaning link to the page that explains them, or to the [glossary](glossary.md).
- A box that begins **Not yet confirmed** marks behaviour that has not yet been checked against the real model
  gateway or on Databricks. [Limits](operations/limits.md) gathers all of these in one place.
- Screenshots are being added. Until then, a box that begins **Screenshot to add** describes the picture that
  will stand there.

Writing a page? Follow the [conventions](CONVENTIONS.md).
