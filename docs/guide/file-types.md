[Documentation](../README.md) › [User guide](README.md) › File types

# File types

A source takes a PDF, an image or a text file. This page explains how Document Engine tells them apart, how each is split into pages and sent to the model, the limits, what is refused, and the setting that sends images as PDFs. It is for anyone who uploads files or builds flows for files that are not PDFs.

**On this page**

- [The three types at a glance](#the-three-types-at-a-glance)
- [How the type is detected](#how-the-type-is-detected)
- [PDF](#pdf)
- [Image](#image)
- [Text](#text)
- [What "page" means](#what-page-means)
- [Limits](#limits)
- [What is refused](#what-is-refused)
- [Sending images as PDFs](#sending-images-as-pdfs)
- [Sample files to try](#sample-files-to-try)

## The three types at a glance

| Type | Examples | How it is split | How a call receives it |
|---|---|---|---|
| PDF | Any PDF, scanned or digital | One page of the PDF is one page | A small PDF holding only the pages of that call |
| Image | PNG, JPEG, GIF, WebP, BMP, TIFF | The image is one page | The image, turned upright and scaled down |
| Text | `.txt`, `.md`, `.csv`, `.json` and any other plain text | Pages of about 3,000 characters, cut at line ends | Text, with each page marked by its number |

The same flow works on all three. A step does not need to know which type of file it is given: it works through pages in every case.

In the builder and on the [Files screen](files-screen.md), a file's size is shown as a number of pages for a PDF, as **image** for an image, and as a number of pages **of text** for a text file. A source block carries the chip **PDF**, **Image** or **Text**.

## How the type is detected

The type is decided when the file is uploaded, from the file's content first and its name second. A PDF that was renamed `scan.txt` is still treated as a PDF.

The checks run in this order:

1. **PDF**: the file starts with a PDF header.
2. **Image**: the file starts with the signature of a PNG, JPEG, GIF, TIFF or WebP image. A BMP image is recognised by its signature together with the ending `.bmp`.
3. **Office file**: the name ends in an office ending (such as `.docx`, `.xlsx`, `.pptx`, `.doc`, `.odt`, `.rtf`), or the content has the signature of an office file. These are [refused](#what-is-refused).
4. **Zip archive**: the content has the signature of a zip archive and does not look like an office file. Refused, with its own message.
5. **Damaged image or PDF**: the name ends in an image ending or in `.pdf`, but the content is not one. Refused.
6. **Other binary content**: refused.
6. **Text**: everything else.

So "text" means any file that holds readable characters, whatever its ending. The upload button suggests common endings (`.txt`, `.md`, `.csv`, `.tsv`, `.json`, `.xml`, `.log`, `.yaml`, `.yml`), but the list is only a suggestion.

## PDF

- **Pages.** Every page of the PDF is one page. A 150-page PDF gives a step 150 [items](../glossary.md#item) to work through.
- **Sending.** For each call, the engine builds a small PDF that holds only the pages of that call's window, and sends that. With Map and a window of 4, each call receives a 4-page PDF. The call is also told which pages of the original file those are, so page references use the original page numbers.
- **Scans.** A scanned PDF, in which each page is a picture, is sent the same way as any other PDF.
- **Size in tokens.** For the estimate, a PDF page counts as a fixed number of input tokens, set for each model (`models.<name>.input_tokens_per_page`). See [Estimates](../how-it-works/estimates.md).

## Image

- **Pages.** An image is exactly one page. Whatever the window size, Map makes one call for it; see [What a short file does](instructions.md#what-a-short-file-does).
- **Preparation at upload.** The image is turned upright, using the orientation recorded by the camera or scanner. Transparent areas are filled with white. If its longer edge is above 1,568 pixels, it is scaled down to that (the setting `documents.image_max_px`).
- **Stored form.** Images that arrive as PNG, GIF, BMP or TIFF are stored as PNG, which keeps scans and screenshots of text sharp. JPEG and WebP images, and any image that would be too large as a PNG, are stored as JPEG. The prepared image is what is stored and what is sent; the original upload is not kept.
- **Only the first frame.** For an animated GIF or a multi-page TIFF, only the first frame or page is used. To process a multi-page scan, convert it to a PDF.
- **Sending.** A call receives the image itself, and is told that it is page 1 of the file.

> **Not yet confirmed:** Image input has run only against the fake gateway. It has not been sent to the real gateway. Preflight checks it for each model; if a model refuses images, see [Sending images as PDFs](#sending-images-as-pdfs).

## Text

- **Reading.** The file is read as UTF-8, or as UTF-16 when it begins with a UTF-16 byte-order mark. A file that is neither is read as an older Windows encoding, with unreadable characters replaced.
- **Pages.** The text is cut into pages of at most about 3,000 characters (the setting `documents.text_page_chars`). The rules:
  - a page ends at the end of a line, never in the middle of one;
  - a form feed character always starts a new page, so a text export that already has page breaks keeps them;
  - a single line longer than a page is cut at the page size;
  - blank pages are dropped.
- **Pages are fixed at upload.** A text file is split once, when it is stored. If an administrator later changes the page size, files already uploaded keep their pages; only new uploads use the new size.
- **Sending.** A call receives the text of its pages, each page marked with its number, under the file's name. Page references therefore work for text files as they do for PDFs.

**Example.** A plain text export of 10,000 characters, with no form feeds and lines of ordinary length, becomes about 4 pages: three of nearly 3,000 characters and a shorter last one. With Map 4 / 1, a 4-page file fits in one window, so a step makes one call for it. A CSV export of 600,000 characters becomes a little over 200 pages.

For tables of data, such as CSV, remember that a page break can fall between any two lines, and that the header line is on the first page only. A step that needs the header on every page should be told the column names in its prompt.

## What "page" means

"Page" means the same for all three types: it is what a step works through, and what a page reference points at.

| Type | A page is | A page reference opens |
|---|---|---|
| PDF | One page of the PDF | That page of the PDF |
| Image | The whole image | The image |
| Text | One block of about 3,000 characters | That block of text |

Page references are followed on the [Results screen](results-screen.md).

## Limits

| Limit | Value | Notes |
|---|---|---|
| Size of an upload | 200 MB | Any type. |
| Size of a text file | 5 MB | Larger text is refused, with the advice to split it or send it as a PDF. |
| Image long edge | 1,568 pixels | Larger images are scaled down, not refused. Setting: `documents.image_max_px`. |
| Text page size | 3,000 characters | Setting: `documents.text_page_chars`. |
| Size of one request to the model | 16 MB | Setting: `gateway.max_request_mb`. A call whose pages exceed it is not sent, and the job fails with a message giving the size and advising a smaller window. This mostly concerns large windows of heavy scanned PDFs. |
| Source used whole as a [reference](several-files.md#references) | 100 pages | Setting: `worker.max_reference_pages`. |

The same file uploaded again under the same name is stored once: the upload returns the file already held.

Administrators change the settings in the configuration file; see [Settings](../operations/settings.md) and [Limits](../operations/limits.md).

## What is refused

A refused upload stores nothing. The message says why.

| File | Message |
|---|---|
| An empty file | The upload was empty. |
| Word, Excel, PowerPoint and other office files | *name* **is an office file, which is not supported. Save it as a PDF and upload that.** |
| A zip archive | *name* **is a zip archive, which is not supported. Upload the files inside it one at a time.** |
| A file with an image ending that is not a readable image | *name* **could not be read as an image.** |
| A file ending in `.pdf` that is not a readable PDF, or a damaged PDF | *name* **could not be read as a PDF.** |
| A PDF with no pages | *name* **has no pages** |
| Any other binary file, such as a program or an archive that is not a zip | *name* **is not a file type this can read. Send a PDF, an image (PNG, JPEG, GIF, WebP, BMP, TIFF) or a text file.** |
| A text file over 5 MB | *name* **is larger than 5 MB of text. Split it, or send it as a PDF.** |
| A text file with nothing but blank space | *name* **holds no text** |
| A file over 200 MB | *name* **is larger than 200 MB** |

> **Note:** Modern office files are zip archives too. Document Engine tells them apart by the names of the parts inside: a zip archive that holds the parts of a Word, Excel, PowerPoint or OpenDocument file gets the office-file message, and any other zip archive gets the zip message.

## Sending images as PDFs

By default, an image is sent to the model as an image. An administrator can change this with one setting:

```yaml
worker:
  send_images_as: pdf      # image (the default) | pdf
```

With `pdf`, every image is wrapped in a one-page PDF at the moment it is sent, both as the pages a step works through and as a reference. Nothing changes in the builder, in the stored file, or in how pages are counted and cited: an image is still one page.

Use this when preflight reports that a model refuses image input. PDF input is the form that was measured in the proof of concept on Sonnet 5.5, so it is the safe fallback. The setting applies to the whole installation, not to one flow. See [Settings](../operations/settings.md).

## Sample files to try

Two sample files are installed to show the other two types. Both hold the same fictional content as one of the sample PDFs.

| Sample file | Type | Same content as |
|---|---|---|
| **Purchase order (text export).txt** | Text | **Purchase order.pdf** |
| **Delivery note, page 1 (scan).png** | Image | The first page of **Delivery note.pdf** |

To try them, open the sample flow **Check an invoice against its order**, select the source **Purchase order** or **Delivery note**, and choose the text or image file in the **File** list in place of the PDF. Then start a test run. The flow itself does not change.

> **Screenshot to add:** `images/builder-source-file-types.png`. The sample flow "Check an invoice against its order" with the Purchase order source set to the text export and the Delivery note source set to the scan image: the three source blocks showing the chips "Text", "Image" and "PDF", and the File list open in the right-hand panel with entries reading "… pages", "image" and "… pages of text".

## See also

- [Files screen](files-screen.md): uploading files and removing them.
- [Instructions](instructions.md): how pages are grouped into calls.
- [Several files in one flow](several-files.md): giving a flow more than one file.
- [Results screen](results-screen.md): opening the page behind a page reference.
- [Settings](../operations/settings.md): the settings named on this page.
