"""Documents: stored in Postgres, split into page windows on demand.

Three kinds of file are accepted:
  pdf    every page is one unit. A window is sent as a small PDF holding only its pages.
  image  one unit. Stored already turned upright and scaled down, and sent as an image.
  text   split into pages when it is stored (at form feeds, else every `text_page_chars`
         characters at a line end). A window is sent as text with each page marked by its number.

"Page" therefore means the same thing everywhere: the unit a step works through and a citation points at.
"""
from __future__ import annotations

import hashlib
import io
from collections import OrderedDict
from pathlib import PurePosixPath
from typing import Any

from pypdf import PdfReader, PdfWriter

from .db import Db
from .flows import new_id

KINDS = ("pdf", "image", "text")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
OFFICE_EXT = {".doc", ".docx", ".docm", ".odt", ".rtf", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".pages"}
ACCEPTED = "PDF, an image (PNG, JPEG, GIF, WebP, BMP, TIFF) or a text file"
TEXT_MAX_BYTES = 5 * 1024 * 1024
IMAGE_TARGET_BYTES = 3_500_000          # the API limit is 5 MB per image once encoded; stay well under


def page_count(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


def _ext(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).suffix.lower()


def detect_kind(name: str, data: bytes) -> str:
    """pdf, image or text, from the content first and the name second. ValueError for anything else."""
    head = data[:1024]
    ext = _ext(name)
    if b"%PDF-" in head:
        return "pdf"
    if (head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"II*\x00", b"MM\x00*"))
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP") or (head[:2] == b"BM" and ext == ".bmp")):
        return "image"
    office = f"{name} is an office file, which is not supported. Save it as a PDF and upload that."
    if ext in OFFICE_EXT or head.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError(office)
    if head.startswith(b"PK\x03\x04"):
        # Modern office files are zip archives too. They name their parts in a recognisable way.
        if any(mark in data[:65536] for mark in (b"[Content_Types].xml", b"word/", b"xl/", b"ppt/", b"mimetypeapplication/vnd.oasis")):
            raise ValueError(office)
        raise ValueError(f"{name} is a zip archive, which is not supported. Upload the files inside it one at a time.")
    if ext in IMAGE_EXT:
        raise ValueError(f"{name} could not be read as an image.")
    if ext == ".pdf":
        raise ValueError(f"{name} could not be read as a PDF.")
    if b"\x00" in data[:8192] and not head.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError(f"{name} is not a file type this can read. Send a {ACCEPTED}.")
    return "text"


def prepare_image(name: str, data: bytes, max_px: int = 1568) -> tuple[bytes, str, float]:
    """(image bytes, media type, estimated tokens). Upright, at most `max_px` on its long edge, PNG or JPEG."""
    from PIL import Image, ImageOps
    try:
        img = Image.open(io.BytesIO(data))
        img.load()                                     # first frame of an animation or a multi-page TIFF
    except Exception as e:
        raise ValueError(f"{name} could not be read as an image: {e}") from e
    lossless = (img.format or "").upper() in ("PNG", "GIF", "BMP", "TIFF")
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):                # flatten transparency onto white
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel("A"))
        img = flat
    elif img.mode != "RGB":
        img = img.convert("RGB")
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
    if min(img.size) < 1:
        raise ValueError(f"{name} is an empty image")
    tokens = img.size[0] * img.size[1] / 750.0

    def encode(fmt: str, **kw: Any) -> bytes:
        buf = io.BytesIO()
        img.save(buf, fmt, **kw)
        return buf.getvalue()

    if lossless:                                       # screenshots and scans of text stay sharp as PNG
        out = encode("PNG", optimize=True)
        if len(out) <= IMAGE_TARGET_BYTES:
            return out, "image/png", tokens
    for q in (90, 80, 70):
        out = encode("JPEG", quality=q)
        if len(out) <= IMAGE_TARGET_BYTES:
            break
    return out, "image/jpeg", tokens


def decode_text(name: str, data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")   # older Windows exports


def paginate_text(text: str, page_chars: int = 3000) -> list[str]:
    """Pages of at most `page_chars` characters, broken at line ends. A form feed always starts a new page."""
    page_chars = max(200, int(page_chars))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    pages: list[str] = []
    for part in text.split("\f"):
        cur: list[str] = []
        size = 0
        for line in part.split("\n"):
            while len(line) > page_chars:              # a single line longer than a page
                if cur:
                    pages.append("\n".join(cur))
                    cur, size = [], 0
                pages.append(line[:page_chars])
                line = line[page_chars:]
            if cur and size + len(line) + 1 > page_chars:
                pages.append("\n".join(cur))
                cur, size = [], 0
            cur.append(line)
            size += len(line) + 1
        if cur:
            pages.append("\n".join(cur))
    return [p.strip("\n") for p in pages if p.strip()]


def prepare(name: str, data: bytes, *, image_max_px: int = 1568, text_page_chars: int = 3000) -> dict[str, Any]:
    """What is stored for an upload: {kind, media_type, content, pages, page_tokens}.
    `page_tokens` is the estimated input tokens per page, or None to use the model's figure for a PDF page."""
    if not data:
        raise ValueError(f"{name} is empty")
    kind = detect_kind(name, data)
    if kind == "pdf":
        try:
            pages = page_count(data)
        except Exception as e:  # pypdf raises many types on a damaged file
            raise ValueError(f"{name} could not be read as a PDF: {e}") from e
        if pages == 0:
            raise ValueError(f"{name} has no pages")
        return {"kind": "pdf", "media_type": "application/pdf", "content": data, "pages": pages, "page_tokens": None}
    if kind == "image":
        content, media_type, tokens = prepare_image(name, data, image_max_px)
        return {"kind": "image", "media_type": media_type, "content": content, "pages": 1, "page_tokens": round(tokens)}
    if len(data) > TEXT_MAX_BYTES:
        raise ValueError(f"{name} is larger than {TEXT_MAX_BYTES // (1024 * 1024)} MB of text. Split it, or send it as a PDF.")
    pages = paginate_text(decode_text(name, data), text_page_chars)
    if not pages:
        raise ValueError(f"{name} holds no text")
    content = "\f".join(pages).encode("utf-8")
    return {"kind": "text", "media_type": "text/plain; charset=utf-8", "content": content, "pages": len(pages),
            "page_tokens": round(sum(len(p) for p in pages) / len(pages) / 3.6 + 12)}


DOC_COLUMNS = "document_id, name, pages, size_bytes, is_sample, created_at, kind, page_tokens"
MAX_FILE_BYTES = 200 * 1024 * 1024


class FileTooLarge(ValueError):
    pass


async def read_body(request: Any, name: str = "the file", limit: int = MAX_FILE_BYTES) -> bytes:
    """The request body, read in pieces and given up as soon as it passes the limit, so an oversized upload
    is never held in memory whole."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise FileTooLarge(f"{name} is larger than {limit // (1024 * 1024)} MB")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise FileTooLarge(f"{name} is larger than {limit // (1024 * 1024)} MB")
        chunks.append(chunk)
    return b"".join(chunks)


async def read_part(part: Any, name: str = "the file", limit: int = MAX_FILE_BYTES) -> bytes:
    """One uploaded form part. Form parts are kept on disk while the request is read; the size is checked
    before the part is loaded."""
    if getattr(part, "size", None) is not None and part.size > limit:
        raise FileTooLarge(f"{name} is larger than {limit // (1024 * 1024)} MB")
    data = await part.read(limit + 1)
    if len(data) > limit:
        raise FileTooLarge(f"{name} is larger than {limit // (1024 * 1024)} MB")
    return data


async def store_document(db: Db, name: str, data: bytes, is_sample: bool = False,
                         document_id: str | None = None, cfg: Any = None, via_api: bool = False) -> dict[str, Any]:
    """Stores a file and returns its row. The same content under the same name is stored once: the row
    already held comes back with "reused": True. `via_api` marks a file a caller sent with a job, which
    the builder's file pickers leave out."""
    opts = (cfg or {}).get("documents") or {}
    doc = prepare(name, data, image_max_px=int(opts.get("image_max_px", 1568)),
                  text_page_chars=int(opts.get("text_page_chars", 3000)))
    sha = hashlib.sha256(data).hexdigest()               # of the file as uploaded
    existing = await db.fetchone(f"SELECT {DOC_COLUMNS}, via_api FROM documents WHERE sha256 = %s AND name = %s", (sha, name))
    if existing and document_id is None:
        if existing.pop("via_api") and not via_api:
            # First sent by a caller of the endpoint, now uploaded from the screen: show it in the file pickers.
            await db.execute("UPDATE documents SET via_api = false WHERE document_id = %s", (existing["document_id"],))
        return {**existing, "reused": True}
    doc_id = document_id or new_id("doc")
    await db.execute(
        "INSERT INTO documents (document_id, name, pages, size_bytes, sha256, is_sample, content, kind, media_type, page_tokens, via_api) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (document_id) DO UPDATE SET name = excluded.name, "
        "pages = excluded.pages, size_bytes = excluded.size_bytes, sha256 = excluded.sha256, content = excluded.content, "
        "kind = excluded.kind, media_type = excluded.media_type, page_tokens = excluded.page_tokens",
        (doc_id, name, doc["pages"], len(doc["content"]), sha, is_sample, doc["content"], doc["kind"], doc["media_type"],
         doc["page_tokens"], via_api))
    return {"document_id": doc_id, "name": name, "pages": doc["pages"], "size_bytes": len(doc["content"]),
            "is_sample": is_sample, "kind": doc["kind"], "page_tokens": doc["page_tokens"], "reused": False}


class DocumentCache:
    """Loaded documents and built windows, kept per process. Safe to lose: everything reloads from Postgres."""

    def __init__(self, db: Db, max_docs: int = 8, max_windows: int = 2000) -> None:
        self.db = db
        self._docs: OrderedDict[str, dict] = OrderedDict()
        self._windows: OrderedDict[tuple, bytes] = OrderedDict()
        self.max_docs = max_docs
        self.max_windows = max_windows

    async def _doc(self, document_id: str) -> dict:
        """{kind, media_type, name, and one of: reader (pdf), content (image), pages (text)}"""
        d = self._docs.get(document_id)
        if d is not None:
            self._docs.move_to_end(document_id)
            return d
        row = await self.db.fetchone("SELECT name, kind, media_type, content FROM documents WHERE document_id = %s",
                                     (document_id,))
        if row is None:
            raise KeyError(f"document {document_id} not found")
        content = bytes(row["content"])
        d = {"kind": row["kind"], "media_type": row["media_type"], "name": row["name"]}
        if d["kind"] == "image":
            d["content"] = content
        elif d["kind"] == "text":
            d["pages"] = content.decode("utf-8").split("\f")
        else:
            d["reader"] = PdfReader(io.BytesIO(content))
        self._docs[document_id] = d
        while len(self._docs) > self.max_docs:
            self._docs.popitem(last=False)
        return d

    def forget(self, document_id: str) -> None:
        """Drops a removed file from this process's memory."""
        self._docs.pop(document_id, None)
        for key in [k for k in self._windows if k[0] == document_id]:
            del self._windows[key]

    def _keep(self, key: tuple, b: bytes) -> bytes:
        self._windows[key] = b
        while len(self._windows) > self.max_windows:
            self._windows.popitem(last=False)
        return b

    async def kind(self, document_id: str) -> str:
        return (await self._doc(document_id))["kind"]

    async def window(self, document_id: str, pages: list[int]) -> bytes:
        """A PDF holding the given pages (1-based), in the order given. An image becomes a one-page PDF."""
        key = (document_id, tuple(pages))
        b = self._windows.get(key)
        if b is not None:
            self._windows.move_to_end(key)
            return b
        d = await self._doc(document_id)
        buf = io.BytesIO()
        if d["kind"] == "image":
            from PIL import Image
            Image.open(io.BytesIO(d["content"])).convert("RGB").save(buf, "PDF", resolution=96.0)
        elif d["kind"] == "text":
            raise ValueError("a text file has no PDF form")
        else:
            w = PdfWriter()
            for p in pages:
                w.add_page(d["reader"].pages[p - 1])
            w.write(buf)
        return self._keep(key, buf.getvalue())

    async def material(self, document_id: str, pages: list[int], images_as_pdf: bool = False) -> dict:
        """The given pages in the form they are sent to the model:
        {"kind": "pdf", "pdf": bytes} | {"kind": "image", "data": bytes, "media_type"} | {"kind": "text", "pages": [(n, text)]}"""
        d = await self._doc(document_id)
        if d["kind"] == "text":
            return {"kind": "text", "pages": [(p, d["pages"][p - 1]) for p in pages]}
        if d["kind"] == "image" and not images_as_pdf:
            return {"kind": "image", "data": d["content"], "media_type": d["media_type"]}
        return {"kind": "pdf", "pdf": await self.window(document_id, pages)}

    async def page_view(self, document_id: str, page: int) -> tuple[bytes, str]:
        """One page for a person to look at: (bytes, media type)."""
        d = await self._doc(document_id)
        if d["kind"] == "image":
            if page != 1:
                raise IndexError(page)
            return d["content"], d["media_type"]
        if d["kind"] == "text":
            if page < 1:
                raise IndexError(page)
            return d["pages"][page - 1].encode("utf-8"), "text/plain; charset=utf-8"
        return await self.window(document_id, [page]), "application/pdf"


def page_ranges(pages: list[int]) -> str:
    """[1,2,3,7] -> '1-3, 7'"""
    if not pages:
        return ""
    ps = sorted(set(pages))
    out = []
    start = prev = ps[0]
    for p in ps[1:]:
        if p == prev + 1:
            prev = p
            continue
        out.append(f"{start}-{prev}" if prev > start else f"{start}")
        start = prev = p
    out.append(f"{start}-{prev}" if prev > start else f"{start}")
    return ", ".join(out)
