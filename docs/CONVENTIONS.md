# Documentation conventions

Rules for everyone who writes pages in `docs/`. Keep them, so the set reads as one work.

## Layout

```
docs/README.md                       home: the map of everything
docs/glossary.md
docs/start/        overview.md  concepts.md  quick-start.md
docs/guide/        README.md  build-a-flow.md  flows-screen.md  builder.md  instructions.md  steps.md
                   several-files.md  value-inputs.md  file-types.md  files-screen.md  test-runs.md
                   run-screen.md  activity-screen.md  results-screen.md  publishing.md
docs/api/          README.md  reference.md  examples.md
docs/how-it-works/ README.md  jobs-and-tasks.md  queue-and-priority.md  quota-ledger.md  heavy-load.md
                   prompt-caching.md  failures-and-recovery.md  estimates.md
docs/operations/   README.md  local-setup.md  databricks.md  settings.md  commands.md  monitoring.md
                   troubleshooting.md  limits.md  fake-gateway.md  first-real-session.md
docs/images/       screenshots (added later)
```

Link only to files in this list, with relative links. Link generously: the first time a page uses a term
another page explains, link it. Link terms to `glossary.md#term` where no page explains them better.

## Every page

1. First line, a breadcrumb: `[Documentation](../README.md) › [User guide](README.md) › Page title`
2. `# Page title`
3. One short paragraph saying what the page covers and who it is for.
4. Pages with more than three sections: a `**On this page**` list of links to the `##` sections.
5. The body, in `##` and `###` sections with plain descriptive headings.
6. Last, a `## See also` list of two to five related pages, each with a few words on why to go there.

## Writing

- Write for a reader who has not seen the code. Plain words, complete sentences, active voice.
- Use the product's words exactly as the screens show them (button and tab names in **bold**).
- Vocabulary: a **file** is anything uploaded (PDF, image, text file); never call it a document. A file has
  **pages**. Use unit, item, window, step, instruction (Map, Reduce, Filter), flow, job, task, source,
  reference, value input, as the glossary defines them. The product is called Document Engine.
- Say what happens and why it matters before how it is implemented.
- Tables for options and settings; numbered lists for procedures; code fences with a language for commands,
  JSON and YAML.
- State only what the code or README supports. Read the code before describing behaviour. Do not guess.
- Do not mention how the documentation or the code was produced.

## Evidence

The scheduler design was measured on the real Databricks AI Gateway in an earlier proof of concept, on
Sonnet 5.5 only. This codebase has so far run only against the fake gateway in `fake_gateway/`.

- Never present a number seen on the fake gateway as a fact about the real gateway.
- A measured fact carries its source: "measured in the proof of concept on Sonnet 5.5".
- Mark anything not yet run on the real gateway, Lakebase or Databricks Apps with this callout:

  `> **Not yet confirmed:** what has not been checked, and when it will be.`

- Other callouts: `> **Note:**` and `> **Tip:**`.

## Screenshots

Screenshots are added later. Where one belongs, put exactly this, on its own lines:

```
> **Screenshot to add:** `images/<name>.png`. What the picture shows, and what state the screen is in.
```

Use lower-case, hyphenated names that start with the screen: `builder-step-prompt-tab.png`.
Describe the picture well enough that someone else can capture it.
