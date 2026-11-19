"""Builds the request for a task.

Layout (kept from the POC, where it was confirmed on the gateway):
  system   one block holding everything static for the step: its system prompt, its instructions,
           the output contract and the citation rule. The cache marker sits at its end, so every
           call of the step, and its warm-up, share one cached prefix.
  user     the step's references (whole, the same on every call of the step), then the window
           and/or the earlier outputs, then a short closing text with what is specific to this
           call. Documents come before the text that asks about them.

A window is sent in the form of its file: a small PDF, an image, or text with each page marked.

When a flow has several sources, each is called by its input name (the source block's title), and
page citations carry that name: [Invoice p. 3].

Thinking is stated on every request, because the current models think by default and thinking
counts against max_tokens and the output quota.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

from .config import Section, model_cfg
from .documents import page_ranges
from .flows import json_schema, text_tokens

CITE_RULE = (
    "Source pages: every statement you make must be traceable. After each finding, cite the page or pages "
    "it comes from in square brackets, using the document's own page numbers given at the end of the request, "
    "for example [p. 12] or [pp. 12-14]. Never cite a page you were not shown."
)


CITE_RULE_MULTI = (
    "Source pages: this task involves more than one document. Each is called by its input name, given in the "
    "request. Every statement you make must be traceable. After each finding, cite the input name and the page "
    "or pages it comes from in square brackets, for example [Invoice p. 2] or [Purchase order pp. 1-2]. Use the "
    "input names exactly as given. Never cite a page you were not shown."
)


def system_text(step: dict, multi: bool = False) -> str:
    parts = []
    if (step.get("system") or "").strip():
        parts.append(step["system"].strip())
    if (step.get("instructions") or "").strip():
        parts.append(step["instructions"].strip())
    out = step.get("output") or {}
    if out.get("type") == "schema":
        schema = json_schema(out.get("fields") or [])
        parts.append(
            "Output contract: reply with one JSON object and nothing else. No preamble, no explanation, "
            "no code fence. The object must match this JSON Schema exactly:\n"
            + json.dumps(schema, indent=1, sort_keys=True))
    elif step.get("track_pages", True):
        parts.append(CITE_RULE_MULTI if multi else CITE_RULE)
    return "\n\n".join(parts)


def prefix_hash(model: str, system: str) -> str:
    return hashlib.sha256((model + "\n" + system).encode()).hexdigest()[:24]


def is_cacheable(cfg: Section, model: str, system: str) -> bool:
    # text_tokens is rough, so lean towards marking: a marker on a prefix that turns out too short
    # is ignored by the API, while a missing marker on a long one loses the saving.
    return text_tokens(system) >= 0.75 * float(model_cfg(cfg, model).get("cache_min_tokens", 1024))


def system_blocks(cfg: Section, model: str, step: dict, multi: bool = False) -> list[dict]:
    text = system_text(step, multi) or "You are a careful document analyst."
    block: dict[str, Any] = {"type": "text", "text": text}
    if is_cacheable(cfg, model, text):
        block["cache_control"] = {"type": "ephemeral"}
    return [block]


def thinking_params(cfg: Section, model: str, level: str) -> dict:
    """Request parameters for a thinking level. "off" is sent the way this model accepts it."""
    if level in ("low", "medium", "high"):
        return {"thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": level}}
    form = model_cfg(cfg, model).get("thinking_off", "disabled")
    if form == "between_tools":
        # Sonnet 5.5 rejects {"type": "disabled"} with a 400. We send no tools, so this is "off".
        return {"thinking": {"type": "between_tools"}}
    if form == "effort_low":
        # Thinking cannot be turned off on this model. Lowest effort is the closest setting.
        return {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}
    return {"thinking": {"type": "disabled"}}


def pdf_block(pdf: bytes, title: str) -> dict:
    return {"type": "document", "title": title,
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": base64.standard_b64encode(pdf).decode("ascii")}}


def image_block(data: bytes, media_type: str) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                        "data": base64.standard_b64encode(data).decode("ascii")}}


def text_pages_block(name: str, pages: list[tuple[int, str]]) -> dict:
    """Pages of a text file, each marked with its page number."""
    body = "\n".join(f"<page number=\"{n}\">\n{t}\n</page>" for n, t in pages)
    return {"type": "text", "text": f"<document name=\"{name}\">\n{body}\n</document>"}


def material_blocks(material: dict | None, title: str, name: str) -> list[dict]:
    """Content blocks for what DocumentCache.material() returned."""
    if not material:
        return []
    if material["kind"] == "image":
        return [image_block(material["data"], material["media_type"])]
    if material["kind"] == "text":
        return [text_pages_block(name, material["pages"])]
    return [pdf_block(material["pdf"], title)]


def closing_text(doc_name: str, pages: list[int], has_pdf: bool | str, n_items: int, instruction: str | None,
                 input_name: str | None = None, n_refs: int = 0) -> str:
    """`has_pdf` is the form the window was sent in: "pdf" (or True), "image", "text", or False for none.
    `input_name` is set when the flow has several sources: pages are then cited with that name."""
    lines = []
    what = f"the input named \"{input_name}\" (file \"{doc_name}\")" if input_name else f"\"{doc_name}\""
    form = "pdf" if has_pdf is True else has_pdf
    cite = (f"Cite its pages as [{input_name} p. N], using the document page numbers." if input_name
            else "Use the document page numbers when you cite.")
    if n_refs:
        lines.append("The references above are background for this task. Use them as your instructions say.")
    if form == "image" and pages:
        lines.append(f"The {'last ' if n_refs else ''}image above is page {pages[0]} of {what}.")
        lines.append(f"Cite it as [{input_name} p. {pages[0]}]." if input_name else f"Cite it as [p. {pages[0]}].")
    elif form == "text" and pages:
        lines.append(f"The text {'just ' if n_refs else ''}above holds page{'s' if len(pages) > 1 else ''} "
                     f"{page_ranges(pages)} of {what}. Each page is marked with its number.")
        lines.append(cite)
    elif form and pages:
        if len(pages) == 1:
            lines.append(f"The {'last ' if n_refs else ''}document above is page {pages[0]} of {what}.")
        else:
            mapping = ", ".join(f"PDF page {i + 1} = document page {p}" for i, p in enumerate(pages))
            lines.append(f"The {'last ' if n_refs else ''}document above holds pages {page_ranges(pages)} of {what} ({mapping}).")
        lines.append(cite)
    elif pages:
        lines.append(f"The material above covers pages {page_ranges(pages)} of {what}.")
    if n_items > 1 and instruction == "reduce":
        lines.append(f"You were given {n_items} earlier outputs. Use all of them.")
    lines.append("Follow your instructions now.")
    return " ".join(lines)


def items_text(sources: list[dict]) -> str:
    """Earlier outputs, each tagged with the pages it covers (and the input they come from, when given)."""
    parts = []
    for s in sources:
        body = s.get("output_text") or ""
        if s.get("output_data") is not None and not body.strip():
            body = json.dumps(s["output_data"], ensure_ascii=False)
        src = f"source=\"{s['input_name']}\" " if s.get("input_name") else ""
        parts.append(f"<item {src}pages=\"{page_ranges(s.get('pages') or [])}\">\n{body.strip()}\n</item>")
    return "\n\n".join(parts)


def reference_blocks(refs: list[dict]) -> list[dict]:
    """References, whole. Each is {"kind": "step", "label", "items": [...]} or
    {"kind": "source", "label", "name", "pages", "material"} (or "pdf" in place of "material")."""
    out: list[dict] = []
    for r in refs:
        if r["kind"] == "source":
            material = r.get("material") or {"kind": "pdf", "pdf": r["pdf"]}
            noun = {"image": "image", "text": "text file"}.get(material["kind"], "document")
            out.append({"type": "text", "text": f"Reference {noun}. Input name: \"{r['label']}\". File: \"{r['name']}\", "
                                                f"{r['pages']} page{'s' if r['pages'] != 1 else ''}, attached in full. "
                                                f"Cite its pages as [{r['label']} p. N]."})
            out += material_blocks(material, f"{r['label']} ({r['name']})", r["name"])
        else:
            body = items_text(r.get("items") or []) or "(this step produced no output)"
            out.append({"type": "text", "text": f"<reference name=\"{r['label']}\">\n{body}\n</reference>"})
    return out


def build_request(cfg: Section, *, step: dict, model: str, doc_name: str, pages: list[int], pdf: bytes | None,
                  sources: list[dict], instruction: str | None, max_tokens: int,
                  refs: list[dict] | None = None, input_name: str | None = None,
                  material: dict | None = None) -> dict:
    """`input_name` (the source block's title) is given when the flow has several sources.
    The window is `material` (see DocumentCache.material), or `pdf` for a plain PDF window."""
    multi = input_name is not None
    refs = refs or []
    if material is None and pdf is not None:
        material = {"kind": "pdf", "pdf": pdf}
    content: list[dict] = reference_blocks(refs)
    content += material_blocks(material, f"{input_name or doc_name} pages {page_ranges(pages)}", doc_name)
    if sources:
        content.append({"type": "text", "text": items_text(sources)})
    content.append({"type": "text", "text": closing_text(doc_name, pages, material["kind"] if material else False,
                                                         len(sources), instruction, input_name, len(refs))})
    params: dict[str, Any] = {
        "model": model_cfg(cfg, model).gateway_name,
        "max_tokens": int(max_tokens),
        "system": system_blocks(cfg, model, step, multi),
        "messages": [{"role": "user", "content": content}],
    }
    params.update(thinking_params(cfg, model, step.get("thinking", "off")))
    return params


def warmup_request(cfg: Section, *, step: dict, model: str, multi: bool = False) -> dict:
    """Writes the step's static prompt to the cache so the burst that follows reads it."""
    params: dict[str, Any] = {
        "model": model_cfg(cfg, model).gateway_name,
        "max_tokens": int(cfg.worker.get("warmup_max_tokens", 1)),
        "system": system_blocks(cfg, model, step, multi),
        "messages": [{"role": "user", "content": "ok"}],
    }
    params.update(thinking_params(cfg, model, "off"))
    return params


def request_bytes(params: dict) -> int:
    return len(json.dumps(params, separators=(",", ":")).encode())


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


def extract_json(text: str) -> Any:
    """The JSON object in a reply, tolerating a code fence or a stray sentence around it."""
    t = _FENCE.sub("", text or "").strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a != -1 and b > a:
        return json.loads(t[a:b + 1])
    raise ValueError("the reply holds no JSON object")
