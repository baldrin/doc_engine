[Documentation](../README.md) › [User guide](README.md) › The Files screen

# The Files screen

The Files screen lists every file Document Engine holds: the PDFs, images and text files that flows are tested
and run on. Here you upload files, see where each one has been used, and remove files you no longer need. This
page is for anyone who runs flows on their own files.

**On this page**

- [Open the screen](#open-the-screen)
- [The table](#the-table)
- [The Sample and API tags](#the-sample-and-api-tags)
- [Upload files](#upload-files)
- [Remove a file](#remove-a-file)
- [The sample files](#the-sample-files)

> **Screenshot to add:** `images/files-screen-overview.png`. The Files screen with two uploaded files at the top (one of them in use by a run that has not finished, so its Remove button is greyed out), one file tagged API, and the sample files below.

## Open the screen

Select **Files** in the [top bar](flows-screen.md#the-top-bar). In the builder, the **Manage files** link on a
source block's panel opens the same screen.

A file is chosen in two places: on a source block in the [builder](builder.md), or when a run is started (see
[Start a test run](test-runs.md) and the [Activity screen](activity-screen.md)). This screen is where the whole
collection is managed.

## The table

Your own files come first, the newest at the top. The sample files follow.

| Column | Meaning |
|---|---|
| **Name** | The file's name as it was uploaded, followed by a **Sample** or **API** tag where one applies. |
| **Type** | **PDF**, **Image** or **Text**. Document Engine decides the type from the file's content, not from its name. See [File types](file-types.md). |
| **Pages** | How many pages the file has. A PDF has its own pages, an image is always one page, and a text file is divided into pages when it is uploaded. |
| **Size** | The size of the file as Document Engine stores it, in B, KB or MB. |
| **Uploaded** | How long ago the file was uploaded, for example **5 min ago** or **2 d ago**. Empty for sample files. |
| **Used in** | How many runs have used the file: **No runs**, **1 run**, **4 runs**. When some of those runs are still queued or running, the count says so: **4 runs, 1 not finished**. |
| The last column | The **Remove** button. Sample files have none. |

Other messages you may see:

- **Loading files…** while the list loads.
- **No files yet. Upload one to get started.** when Document Engine holds no files at all.
- **Only the sample files so far. Files you upload appear here.** below the table, when nothing has been
  uploaded yet.

The list is read when the screen opens and again after each upload or removal. It also refreshes by itself
every few seconds, and when the browser window regains focus. A **Remove** button therefore becomes available
by itself when the run that uses the file ends.

## The Sample and API tags

| Tag | Meaning |
|---|---|
| **Sample** | The file came with Document Engine. Sample files are fictional, are there to try the [sample flows](flows-screen.md#the-sample-flows) on, and cannot be removed. |
| **API** | The file was sent by a caller of the public endpoint, together with a job, instead of being uploaded by someone using these screens. Hover over the tag to read **Sent by a caller of the public endpoint**. |

Files tagged **API** are listed on this screen only. They do not appear in the builder's file lists, in the
**Test run** dialog or in the **Submit jobs** form on the Activity screen, so the files that callers send do
not crowd the lists you choose from. You can still see how many runs used such a file, and remove it, here.
If you upload the same file under the same name from a screen, it loses the **API** tag and appears in those
lists from then on.
The public endpoint is described in the [API guide](../api/README.md).

## Upload files

1. Select **Upload files** in the top bar.
2. Choose one or more files. The file chooser offers PDFs, images (PNG, JPEG, GIF, WebP, BMP, TIFF) and text
   files (such as `.txt`, `.md`, `.csv`, `.tsv`, `.json`, `.xml`, `.log`, `.yaml`).
3. The button reads **Uploading…** while the files are sent, one after another.

For each file a message appears briefly at the bottom of the screen:

- On success: the file's name, **uploaded**, and its size in pages, for example
  **Report.pdf uploaded (12 pages)**. A text file reads **4 pages of text** and an image reads **image**.
- When Document Engine already holds the same file under the same name: the file's name and
  **is already here**, for example **Report.pdf is already here (12 pages)**.
- On failure: the file's name and the reason. The other files in the same upload still go ahead.

Things to know:

- A file may be at most 200 MB. An empty file is refused.
- Word and other office files are refused with a message asking for a PDF. A zip archive is refused with a
  message asking for the files inside it, one at a time. [File types](file-types.md) lists what is accepted
  and how each type is divided into pages.
- Uploading the same file again under the same name does not make a second copy. Document Engine keeps the one
  it has, and the message says **is already here** instead of **uploaded**.

> **Tip:** you can also upload without leaving your work. The source block's panel in the builder and the
> **Test run** dialog both have an **Upload file** button, which takes one file and chooses it for that source
> straight away.

## Remove a file

1. Find the file in the table and select **Remove** in its row.
2. The browser asks for confirmation. Confirm to remove the file.

The confirmation reads **Remove "name"? This cannot be undone.** When past runs used the file it also says how
many, and what removing will do to them, for example: **3 past runs used it: their results stay, but their page
views of this file will stop working.**

After the removal a message confirms it: the file's name and **removed**.

### What removing does to past results

Removing a file deletes the file itself and nothing else.

- Runs that used the file stay in the [Activity screen](activity-screen.md), and their
  [results](results-screen.md) stay readable: the text and tables a run produced are kept with the run.
- What stops working is the page viewer for that file. A [page reference](results-screen.md#page-references)
  in those results can no longer show the page, because the page was part of the file.

Remove a file only when nobody needs to check results against it any more.

### Why a file in use cannot be removed

While a run that uses a file is queued or running, the file's **Remove** button is greyed out, and its tooltip
reads **In use by a run that has not finished**. The **Used in** column shows how many such runs there are.

The reason is that a run reads its files as it goes: each call is given the pages it needs when the call is
sent, not when the run is submitted. Removing the file part-way would make the run's remaining calls fail.
Document Engine checks again at the moment of removal, so if a run started on the file after the screen was
loaded, the removal is refused with a message naming the file and the number of unfinished runs, and asking you
to remove it when they are done.

To remove such a file, wait for the run to finish, or cancel it from the
[Run screen](run-screen.md#cancel-a-run) or the [Activity screen](activity-screen.md#cancel-a-job). The
**Remove** button becomes available within a few seconds.

### Files that cannot be removed

Sample files have no **Remove** button and cannot be removed.

## The sample files

Ten fictional files are installed with Document Engine. Every name, date and value in them is invented.

| File | Type | Pages | Used by |
|---|---|---|---|
| `Patient record.pdf` | PDF | 150 | **Medical record summary** (chosen by default) |
| `Patient record (short, 24 pages).pdf` | PDF | 24 | **Medical record summary**, for a quicker and cheaper run |
| `Vendor contract file.pdf` | PDF | 60 | **Contract file review** |
| `Medication list, admission.pdf` | PDF | 2 | **Compare two medication lists**, the **Admission list** source |
| `Medication list, discharge.pdf` | PDF | 2 | **Compare two medication lists**, the **Discharge list** source |
| `Purchase order.pdf` | PDF | 2 | **Check an invoice against its order**, the **Purchase order** source |
| `Delivery note.pdf` | PDF | 2 | **Check an invoice against its order**, the **Delivery note** source |
| `Invoice.pdf` | PDF | 3 | **Check an invoice against its order**, the **Invoice** source |
| `Purchase order (text export).txt` | Text | | The same purchase order as plain text |
| `Delivery note, page 1 (scan).png` | Image | 1 | The first page of the same delivery note as a picture |

The last two show the other [file types](file-types.md) at work. To try them, open
**Check an invoice against its order** and choose them for the **Purchase order** and **Delivery note** sources
in place of the PDFs.

The short files differ from each other on purpose, so the sample flows have something to report:

- The two medication lists: one dose is higher on discharge, one frequency changed, one medicine was stopped
  and others were started.
- The invoice, against the order and the delivery note: it bills six standing desk frames where five were
  delivered, prices the monitor arm at 68.50 where the order says 62.50, and adds a delivery and handling
  charge of 45.00 that the order excludes.

## See also

- [File types](file-types.md): what can be uploaded and how each type becomes pages.
- [The Flows screen](flows-screen.md#the-sample-flows): the sample flows these files belong to.
- [Start a test run](test-runs.md): choose or upload a file as you start a run.
- [The Results screen](results-screen.md): the page viewer that removing a file affects.
- [API guide](../api/README.md): how callers send the files tagged **API**.
