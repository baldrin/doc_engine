[Documentation](../README.md) › [API](README.md) › Reference

# API reference

Every request and reply of the public endpoint, with its fields and error codes. Read
[Running a flow from code](README.md) first for the overall shape.

**On this page**

- [Conventions](#conventions)
- [GET /api/v1/flows](#get-apiv1flows)
- [GET /api/v1/flows/{flow}](#get-apiv1flowsflow)
- [POST /api/v1/flows/{flow}/jobs](#post-apiv1flowsflowjobs)
- [GET /api/v1/jobs/{job_id}](#get-apiv1jobsjob_id)
- [GET /api/v1/jobs/{job_id}/results](#get-apiv1jobsjob_idresults)
- [POST /api/v1/jobs/{job_id}/cancel](#post-apiv1jobsjob_idcancel)
- [POST /api/v1/files](#post-apiv1files)
- [Errors](#errors)
- [The internal API](#the-internal-api)

## Conventions

- All addresses begin with `/api/v1`. Replies are JSON in UTF-8.
- Times are ISO 8601 with a time zone offset, for example `2026-11-18T12:13:26.108966-06:00`.
- `{flow}` is a flow's **name** or its **flow id**. In a name, case, spacing and punctuation do not matter, so
  a name can be written with hyphens in place of spaces. Letters and digits of every script count, so names in
  non-Latin scripts work and accented letters matter: `cafe` and `café` are different names. Names with other
  characters must be URL-encoded.
- Names of file inputs follow the same rule. Names of value inputs ignore case and extra spaces.
- Only **published** flows exist here. See [Publishing a flow](../guide/publishing.md).

## GET /api/v1/flows

Lists every published flow.

**Reply `200`**

```json
{ "flows": [ { "name": "...", "flow_id": "...", "version": 2, "...": "..." } ] }
```

Each entry is a flow description, as below. The list is in alphabetical order of name.

## GET /api/v1/flows/{flow}

Describes one published flow: what to send and what comes back.

**Reply `200`**

| Field | Type | Meaning |
|---|---|---|
| `name` | string | The flow's name |
| `flow_id` | string | The flow's id. It does not change when the flow is renamed. |
| `version` | number | The published version. This is the version a job will run. |
| `description` | string | The flow's description as stored with the published version, or `""` |
| `files` | array | One entry per source of the flow: `{ "name": "Invoice" }`. Each needs a file on every run. |
| `values` | array | The flow's value inputs. See the next table. |
| `outputs` | array | One entry per Output block: `{ "name": "Invoice verdict", "format": "text" }`. `format` is `text` or `table`. |
| `submit_url` | string | The address that starts a job on this flow, by flow id |

Each entry of `values`:

| Field | Type | Meaning |
|---|---|---|
| `name` | string | The input's name |
| `type` | string | `text`, `number`, `choice`, `yesno` or `json` |
| `required` | boolean | `true` when the input has no default and must be sent |
| `default` | any | The value used when the input is not sent, or `null` |
| `choices` | array of strings | Present for `choice`: the allowed values |
| `description` | string | The description written in the builder, or `""` |

**Errors:** `404 flow_not_found`, `404 flow_not_published`, `409 flow_name_ambiguous`.

## POST /api/v1/flows/{flow}/jobs

Starts one job on the published version of a flow. The body is either a form with the files in it, or JSON
naming files that are already stored.

### As a form (`multipart/form-data`)

| Field | Content |
|---|---|
| *the name of a file input* | The file. One field per source of the flow. A file id as plain text is accepted in place of a file. |
| `file` | The file, for a flow with exactly one source. A shorthand, so the caller need not know the input's name. |
| `values` | Optional. A JSON object of value input name to value: `{"Price tolerance": 10}` |
| *the name of a value input* | Optional. One value as plain text, for example `Price tolerance=10`. An alternative to `values`. |
| `priority` | Optional. `interactive` (the default) or `bulk` |
| `label` | Optional. A short text shown beside the job on the Activity screen. The default is `API`. |

A form request must carry a `Content-Length` header; without one the reply is `411 length_required`. A form
whose declared length is more than 200 MB for each file input of the flow, plus 4 MB, is refused with
`413 file_too_large` before any of it is read.

### As JSON (`application/json`)

```json
{
  "files": { "Purchase order": "doc_c406131a29", "Delivery note": "doc_6d1bb50555", "Invoice": "doc_04decf63b9" },
  "values": { "Price tolerance": 10, "Accept delivery charges": true },
  "priority": "bulk",
  "label": "March invoices"
}
```

| Field | Type | Meaning |
|---|---|---|
| `files` | object | File input name to file id. For a flow with one source, the key `file` is accepted. |
| `values` | object | Optional. Value input name to value. |
| `priority` | string | Optional. `interactive` or `bulk`. |
| `label` | string | Optional. |

A JSON body may be at most 2 MB. A larger one answers `413 request_too_large`.

### How values are read

| Type | Accepted |
|---|---|
| `text` | Any text |
| `number` | A JSON number, or text such as `10`, `0.5` or `1,250`. A comma is accepted only as a thousands separator (`1,250`, `1,250.5`): `1,5` is refused with a message asking for a decimal point. A number too large to represent is refused. |
| `yesno` | `true` or `false`, or the text `yes`, `no`, `true`, `false`, `y`, `n`, `1`, `0` |
| `choice` | One of the input's choices. Case and spacing do not matter. |
| `json` | Any JSON value. In a form, JSON written as text. A JSON value that is itself a piece of text is passed on unchanged. |

An input that is not sent, or is sent empty, takes its default. An input with no default must be sent. Text
and JSON values are limited to 20,000 characters (`worker.max_value_chars`); longer content belongs in a file.

### What is checked

Everything is checked before the job is created. The request is refused, and nothing is kept, when:

- a file input has no file;
- a field is not a file input, a value input, `values`, `priority` or `label`;
- a value is missing, has the wrong type, or is not one of the choices;
- a file id does not exist;
- a file is empty, larger than 200 MB, or not a PDF, an image or a text file.

When several things are wrong with the values, the message lists all of them.

**Reply `202`**

| Field | Type | Meaning |
|---|---|---|
| `job_id` | string | The job's id |
| `status` | string | Always `queued` |
| `flow` | string | The flow's name |
| `flow_version` | number | The version the job runs |
| `status_url` | string | Where to poll |
| `results_url` | string | Where the results will be |

**Errors:** `400 invalid_request`, `400 invalid_values`, `400 invalid_file`, `400 file_not_found`,
`411 length_required`, `413 file_too_large`, `413 request_too_large`, `404 flow_not_found`,
`404 flow_not_published`, `409 flow_name_ambiguous`.

## GET /api/v1/jobs/{job_id}

Reports where a job stands. This is the address to poll.

**Reply `200`**

| Field | Type | Meaning |
|---|---|---|
| `job_id` | string | The job's id |
| `status` | string | `queued`, `running`, `done`, `failed` or `cancelled` |
| `flow` | string | The flow's name when the job was started |
| `flow_version` | number | The version the job ran |
| `priority` | string | `interactive` or `bulk` |
| `label` | string | The label sent with the job |
| `submitted_at` | time | When the job was accepted |
| `started_at` | time or null | When its first call was sent |
| `finished_at` | time or null | When it reached `done`, `failed` or `cancelled` |
| `progress.calls_done` | number | Model calls finished |
| `progress.calls_planned` | number | Model calls planned so far |
| `error` | string or null | Why the job failed or was cancelled |
| `files` | array | The files the job ran on: `input`, `file_id`, `name`, `kind` (`pdf`, `image`, `text`), `pages` |
| `values` | object | The values the job ran with, defaults included |
| `status_url`, `results_url` | string | The job's two addresses |

`calls_planned` grows while a job runs. The calls of a step are planned when the steps before it have finished,
because a filter decides how many items the next step receives. Treat `progress` as a sign of life, not as a
percentage. See [Jobs and tasks](../how-it-works/jobs-and-tasks.md).

| Status | Meaning | Final |
|---|---|---|
| `queued` | Accepted. No call has been sent yet. | no |
| `running` | At least one call has been sent | no |
| `done` | Every step finished. Results are available. | yes |
| `failed` | A step could not be completed. `error` says why. | yes |
| `cancelled` | Stopped by a cancel request or from the Run screen | yes |

**Errors:** `404 job_not_found`.

## GET /api/v1/jobs/{job_id}/results

Returns the outputs of a job whose status is `done`.

**Reply `200`**

| Field | Type | Meaning |
|---|---|---|
| `job_id`, `status`, `flow`, `flow_version`, `finished_at`, `files`, `values` | | As in the status reply |
| `outputs` | array | One entry per Output block of the flow, in the order they are drawn from top to bottom |

Each entry of `outputs`:

| Field | Type | Meaning |
|---|---|---|
| `name` | string | The Output block's name |
| `format` | string | `text` or `table` |
| `text` | string | The text of every item, joined by blank lines. For most flows this is the answer. |
| `items` | array | The individual results that reached the output. See below. |
| `table` | object | Present when the feeding step has a schema: `{ "columns": [...], "rows": [ {...} ] }` |

Each entry of `items`:

| Field | Type | Meaning |
|---|---|---|
| `pages` | array of numbers | The pages of the file this result covers |
| `input` | string | Present when the flow has several sources: the file input those pages belong to |
| `text` | string | The model's reply |
| `data` | object or null | The reply as structured data, when the step has a schema |
| `truncated` | boolean | `true` when the reply stopped at the step's maximum output |

An output fed by a Reduce step has one item. An output fed by a Map or Filter step has one item per call.

Page references inside `text` look like `[p. 12]` and `[pp. 12-14]`, and carry the input name when the flow
has several sources: `[Invoice p. 2]`. In a `table`, the first column is `page`.

**Errors:** `404 job_not_found`, `409 job_not_finished`, `409 job_failed`, `409 job_cancelled`. The `409`
replies carry `job_status`.

## POST /api/v1/jobs/{job_id}/cancel

Stops a job. Calls that are already with the model finish and are discarded; nothing further is sent.
Cancelling a job that has already ended changes nothing.

**Reply `200`:** the job's status, as from `GET /api/v1/jobs/{job_id}`.

**Errors:** `404 job_not_found`.

## POST /api/v1/files

Stores a file and returns its id, for use in later jobs.

Send the file either as the whole request body, with its name in the address:

```bash
curl -X POST 'http://localhost:8000/api/v1/files?name=price-list.pdf' \
  -H 'Content-Type: application/pdf' --data-binary @price-list.pdf
```

or as a form with one part named `file`:

```bash
curl -X POST 'http://localhost:8000/api/v1/files' -F 'file=@price-list.pdf'
```

**Reply `201`**

| Field | Type | Meaning |
|---|---|---|
| `file_id` | string | The file's id |
| `name` | string | The name it was sent with |
| `kind` | string | `pdf`, `image` or `text`, decided from the content |
| `pages` | number | Its pages. An image is one page. |

Sending the same content under the same name again returns the id already held; the file is stored once.

Files sent through the endpoint are listed on the [Files screen](../guide/files-screen.md) with an **API**
tag, and can be removed there. They do not appear in the builder's file pickers, unless someone later uploads
the same file under the same name from a screen.

A form upload must carry a `Content-Length` header, and its declared length may be at most 200 MB plus 4 MB.

**Errors:** `400 invalid_request` (no name), `400 invalid_file`, `411 length_required` (a form with no
`Content-Length` header), `413 file_too_large`.

## Errors

Every error reply has the same shape:

```json
{ "error": "Input \"Price tolerance\" must be a number.", "code": "invalid_values" }
```

`error` is a sentence for a person. `code` is stable and is what a program should test.

| Status | Code | Meaning | What to do |
|---|---|---|---|
| 400 | `invalid_request` | A field is missing, unknown or malformed | Read the message; compare with the flow's description |
| 400 | `invalid_values` | A value is missing, of the wrong type, or not declared by the flow | Fix the values named in the message |
| 400 | `invalid_file` | A file is empty or of a type that cannot be read | Send a PDF, an image or a text file |
| 400 | `file_not_found` | No file has the id that was sent | Store the file again, or send it with the job |
| 404 | `flow_not_found` | No published flow has that name or id | Check the name with `GET /api/v1/flows` |
| 404 | `flow_not_published` | The flow exists but is not published | Publish it in the builder |
| 404 | `job_not_found` | No job has that id | Check the id |
| 404 | `not_found` | There is no such address under `/api/v1` | Check the address |
| 409 | `flow_name_ambiguous` | Several published flows match the name. The reply lists `flow_ids`. | Use a flow id |
| 409 | `job_not_finished` | Results were asked for too early | Keep polling the status |
| 409 | `job_failed` | Results were asked for, but the job failed. `error` holds the reason. | Read the reason; see [Troubleshooting](../operations/troubleshooting.md) |
| 409 | `job_cancelled` | Results were asked for, but the job was cancelled | Start a new job |
| 411 | `length_required` | A form upload came without a `Content-Length` header | Send the header |
| 413 | `file_too_large` | A file is larger than 200 MB, or a form request is larger than 200 MB for each file input of the flow, plus 4 MB | Split the file |
| 413 | `request_too_large` | A JSON body on the job-start address is larger than 2 MB, or another request that is not a file upload is larger than 20 MB | Send long content as a file |

A reply with status `5xx` is a fault in the application, not in the request. Try again later. A job id
exists only in a `202` reply, so a request that failed this way has no job to poll.

## The internal API

The screens of the application use other addresses under `/api/` (without `v1`), for example `/api/jobs`
and `/api/documents`. They serve the user interface, change with it, and are not described here. Programs
should use only `/api/v1`.

## See also

- [Running a flow from code](README.md): the overview and a first run
- [Examples](examples.md): complete clients to copy
- [Value inputs](../guide/value-inputs.md): how values are declared and used
- [Results screen](../guide/results-screen.md): the same outputs as a person sees them
