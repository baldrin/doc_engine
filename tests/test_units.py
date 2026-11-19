"""Unit tests that need neither a database nor a gateway.  Run:  python -m pytest -q"""
from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfWriter

from doc_engine import flows, prompts
from doc_engine.config import ROOT, load_config
from doc_engine.documents import page_count, page_ranges
from doc_engine.gateway import parse_429
from doc_engine.samples import SAMPLE_FLOWS, compare_flow, contract_flow, medical_flow, three_way_flow

CFG = load_config(ROOT / "config.example.yaml")
MODELS = list(CFG.models)


def test_windows_match_the_brief():
    w = flows.windows(150, 4, 1)
    assert len(w) == 50 and w[0] == [0, 1, 2, 3] and w[1][0] == 3 and w[-1][-1] == 149
    assert len(flows.windows(150, 1, 0)) == 150
    assert flows.windows(0, 4, 1) == []
    assert flows.windows(3, 4, 1) == [[0, 1, 2]]
    for n, s, o in [(150, 4, 1), (150, 1, 0), (7, 3, 2), (1, 5, 0), (60, 3, 1), (10, 10, 3)]:
        assert flows.window_count(n, s, o) == len(flows.windows(n, s, o))
    pages = sorted({i for g in flows.windows(37, 5, 2) for i in g})
    assert pages == list(range(37))


def test_sample_flows_are_valid():
    for _, name, _, fn in SAMPLE_FLOWS:
        assert [p for p in flows.validate(fn(), MODELS) if p["level"] == "error"] == [], name


def test_validation_names_the_problem():
    g = medical_flow()
    step = next(n for n in g["nodes"] if n["id"] == "extract")
    step["data"]["system"] = step["data"]["instructions"] = ""
    msgs = [p["message"] for p in flows.validate(g, MODELS)]
    assert "Extract lab values needs a prompt" in msgs

    g = medical_flow()
    next(e for e in g["edges"] if e["id"] == "e5")["data"]["rule"]["field"] = "nope"
    assert any("does not output" in p["message"] for p in flows.validate(g, MODELS))

    g = medical_flow()
    g["edges"].append({"id": "loop", "source": "final", "target": "summarize", "data": {"instruction": "reduce"}})
    msgs = [p["message"] for p in flows.validate(g, MODELS)]
    assert any("2 inputs to work through" in m for m in msgs)

    g = medical_flow()
    next(e for e in g["edges"] if e["id"] == "e1")["data"].update(window=2, overlap=2)
    assert any("overlap" in p["message"] for p in flows.validate(g, MODELS))

    g = medical_flow()
    next(n for n in g["nodes"] if n["id"] == "final")["data"]["model"] = "gpt"
    assert any("not configured" in p["message"] for p in flows.validate(g, MODELS))
    assert flows.validate({"nodes": [], "edges": []}, MODELS)


def test_filter_rules():
    r = {"field": "page_type", "op": "equals", "value": "lab report"}
    assert flows.rule_matches(r, {"page_type": "Lab Report"})
    assert not flows.rule_matches(r, {"page_type": "letter"})
    assert not flows.rule_matches(r, None)
    assert flows.rule_matches({"field": "t", "op": "in", "value": "a, b"}, {"t": "b"})
    assert flows.rule_matches({"field": "n", "op": "greater_than", "value": "3"}, {"n": 4})
    assert not flows.rule_matches({"field": "n", "op": "greater_than", "value": "3"}, {"n": "x"})
    assert flows.rule_matches({"field": "f", "op": "is_true"}, {"f": True})
    assert flows.rule_matches({"field": "tags", "op": "contains", "value": "urgent"}, {"tags": ["Urgent", "x"]})


def test_schema_and_json_extraction():
    s = flows.json_schema([{"name": "page_type", "type": "enum", "values": ["a", "b"]},
                           {"name": "rows", "type": "table", "columns": ["test", "result"]},
                           {"name": "", "type": "string"}])
    assert s["required"] == ["page_type", "rows"]
    assert s["properties"]["page_type"]["enum"] == ["a", "b"]
    assert s["properties"]["rows"]["items"]["required"] == ["test", "result"]
    assert prompts.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert prompts.extract_json('Here it is: {"a": {"b": 2}} done') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        prompts.extract_json("no json here")


def test_estimate_counts_calls():
    est = flows.estimate(medical_flow(), 150, CFG, "f", {}, {"extract": 12 / 150})
    per = est["per_node"]
    assert per["summarize"]["calls"] == 50 and per["final"]["calls"] == 1
    assert per["classify"]["calls"] == 150 and per["extract"]["calls"] == 12
    assert est["calls"] == 213                      # the number in the design mockup
    assert est["cost"] > 0 and not est["assumed_filter_ratio"]
    assert flows.estimate(contract_flow(), 60, CFG)["assumed_filter_ratio"]


def test_prune_to_one_step():
    g = flows.prune_to(medical_flow(), "extract")
    ids = {n["id"] for n in g["nodes"]}
    assert ids == {"source", "classify", "extract", "out_step_test"}
    assert [p for p in flows.validate(g, MODELS) if p["level"] == "error"] == []
    assert next(n for n in g["nodes"] if n["id"] == "out_step_test")["data"]["format"] == "table"


def test_429_body_as_measured_on_the_gateway():
    body = {"error_code": "REQUEST_LIMIT_EXCEEDED",
            "message": "REQUEST_LIMIT_EXCEEDED: Exceeded workspace output tokens per minute rate limit for "
                       "databricks-claude-sonnet-5-5. ..."}
    assert parse_429(body, "") == "output"
    assert parse_429({"message": "Exceeded workspace input tokens per minute rate limit"}, "") == "input"
    assert parse_429({"message": "Exceeded queries per hour"}, "") == "queries"
    assert parse_429(None, "something else") == "unknown"


def test_thinking_is_sent_the_way_each_model_accepts_it():
    assert prompts.thinking_params(CFG, "sonnet", "off") == {"thinking": {"type": "between_tools"}}
    assert prompts.thinking_params(CFG, "haiku", "off") == {"thinking": {"type": "disabled"}}
    assert prompts.thinking_params(CFG, "opus", "off") == {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}
    hi = prompts.thinking_params(CFG, "sonnet", "high")
    assert hi["thinking"]["type"] == "adaptive" and hi["output_config"] == {"effort": "high"}


def _pdf(pages: int) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_request_layout():
    step = flows.step_data(next(n for n in medical_flow()["nodes"] if n["id"] == "summarize"))
    pdf = _pdf(4)
    req = prompts.build_request(CFG, step=step, model="sonnet", doc_name="Patient record.pdf", pages=[10, 11, 12, 13],
                                pdf=pdf, sources=[], instruction="map", max_tokens=1500)
    assert req["model"] == "system.ai.claude-sonnet-5-5" and req["max_tokens"] == 1500
    assert req["thinking"] == {"type": "between_tools"}
    assert len(req["system"]) == 1 and req["system"][0]["cache_control"] == {"type": "ephemeral"}
    content = req["messages"][0]["content"]
    assert content[0]["type"] == "document" and content[-1]["type"] == "text"      # document before the text about it
    assert base64.standard_b64decode(content[0]["source"]["data"]) == pdf
    assert "PDF page 1 = document page 10" in content[-1]["text"]
    warm = prompts.warmup_request(CFG, step=step, model="sonnet")
    assert warm["system"] == req["system"] and warm["max_tokens"] == 1          # the same cached prefix

    short = flows.step_data({"data": {"system": "Be brief.", "model": "sonnet"}})
    r2 = prompts.build_request(CFG, step=short, model="sonnet", doc_name="d.pdf", pages=[1, 2], pdf=None,
                               sources=[{"pages": [1], "output_text": "one"}, {"pages": [2], "output_text": "two"}],
                               instruction="reduce", max_tokens=100)
    assert "cache_control" not in r2["system"][0]
    assert '<item pages="1">' in r2["messages"][0]["content"][0]["text"]

    schema_step = flows.step_data(next(n for n in medical_flow()["nodes"] if n["id"] == "classify"))
    assert "JSON Schema" in prompts.system_text(schema_step)


def test_pages():
    assert page_ranges([1, 2, 3, 7, 9, 10]) == "1-3, 7, 9-10"
    assert page_ranges([]) == ""
    assert page_count(_pdf(5)) == 5
    assert flows.profile_key("f", "n", "sonnet", "weird") == "f:n:sonnet:off"


def test_several_sources_and_references():
    g = three_way_flow()
    assert flows.multi_source(g) and [flows.node_title(n) for n in flows.sources(g)] == ["Purchase order", "Delivery note", "Invoice"]
    assert flows.material_edge(g, "check")["source"] == "src_inv"
    assert {e["source"] for e in flows.reference_edges(g, "check")} == {"order", "delivery"}
    assert flows.lineage_source(g, "verdict") == "src_inv" and flows.lineage_source(g, "order") == "src_po"

    est = flows.estimate(g, {"src_po": 2, "src_dn": 2, "src_inv": 3}, CFG)
    per = est["per_node"]
    assert per["order"]["calls"] == 1 and per["check"]["calls"] == 3 and per["verdict"]["calls"] == 1
    assert per["check"]["reference_tokens"] == 500 + 400 and est["pages"] == 7      # both extracts, on every call
    cmp_est = flows.estimate(compare_flow(), 2, CFG)
    assert cmp_est["calls"] == 1 and cmp_est["per_node"]["compare"]["reference_tokens"] == 2 * 1728

    # a second connection to work through is a problem; as a reference it is not
    g = three_way_flow()
    next(e for e in g["edges"] if e["id"] == "e4")["data"] = {"instruction": "reduce"}
    assert any("2 inputs to work through" in p["message"] for p in flows.validate(g, MODELS))
    g = three_way_flow()
    next(n for n in g["nodes"] if n["id"] == "src_dn")["data"]["title"] = "purchase order"
    assert any("both named" in p["message"] for p in flows.validate(g, MODELS))
    g = compare_flow()
    next(e for e in g["edges"] if e["id"] == "e1")["data"]["role"] = "reference"
    assert any("nothing to work through" in p["message"] for p in flows.validate(g, MODELS))

    # testing one step keeps what its references need
    ids = {n["id"] for n in flows.prune_to(three_way_flow(), "check")["nodes"]}
    assert ids == {"src_po", "src_dn", "src_inv", "order", "delivery", "check", "out_step_test"}


def test_request_with_references():
    g = three_way_flow()
    step = flows.step_data(next(n for n in g["nodes"] if n["id"] == "check"))
    pdf = _pdf(1)
    refs = [{"kind": "step", "label": "Read the order",
             "items": [{"pages": [1, 2], "output_text": "12 chairs at 85.00 [Purchase order p. 1]", "input_name": "Purchase order"}]},
            {"kind": "source", "label": "Delivery note", "name": "dn.pdf", "pages": 2, "pdf": _pdf(2)}]
    req = prompts.build_request(CFG, step=step, model="sonnet", doc_name="inv.pdf", pages=[2], pdf=pdf, sources=[],
                                refs=refs, input_name="Invoice", instruction="map", max_tokens=2000)
    content = req["messages"][0]["content"]
    assert '<reference name="Read the order">' in content[0]["text"] and 'source="Purchase order" pages="1-2"' in content[0]["text"]
    assert content[1]["type"] == "text" and content[2]["type"] == "document"          # the whole delivery note
    assert content[3]["type"] == "document" and base64.standard_b64decode(content[3]["source"]["data"]) == pdf
    assert 'page 2 of the input named "Invoice"' in content[-1]["text"] and "[Invoice p. N]" in content[-1]["text"]
    assert "input name" in req["system"][0]["text"]                                   # citations carry the input name
    one = prompts.build_request(CFG, step=step, model="sonnet", doc_name="inv.pdf", pages=[2], pdf=pdf, sources=[],
                                instruction="map", max_tokens=2000)
    assert "input name" not in one["system"][0]["text"] and len(one["messages"][0]["content"]) == 2


def test_value_inputs():
    g = three_way_flow()
    assert not [p for p in flows.validate(g, MODELS) if p["level"] == "error"]
    # defaults fill in what was not sent; names match without regard to case
    v = flows.resolve_values(g, {"price tolerance": "2.50"})
    assert v == {"Price tolerance": 2.5, "Accept delivery charges": False}
    filled = flows.apply_values(g, v)
    check = flows.nodes_by_id(filled)["check"]["data"]["system"]
    assert "Price tolerance: 2.5." in check and "did not list: no." in check and "{{" not in check
    assert "{{Price tolerance}}" in flows.nodes_by_id(g)["check"]["data"]["system"]      # the flow itself is untouched

    # refused: wrong type, unknown name, and a required input with no default
    for bad, words in (({"Price tolerance": "lots"}, "must be a number"), ({"Colour": "red"}, "no input named"),
                       ({"Accept delivery charges": "maybe"}, "yes or no")):
        try:
            flows.resolve_values(g, bad)
            raise AssertionError("should have been refused")
        except ValueError as e:
            assert words in str(e)
    g["inputs"].append({"name": "Region", "type": "choice", "choices": ["EU", "UK"]})
    try:
        flows.resolve_values(g, {})
        raise AssertionError("should have been refused")
    except ValueError as e:
        assert 'Input "Region" is required and has no default.' in str(e)
    assert flows.resolve_values(g, {"Region": "eu"})["Region"] == "EU"
    try:
        flows.resolve_values(g, {"Region": "US"})
        raise AssertionError("should have been refused")
    except ValueError as e:
        assert "must be one of: EU, UK" in str(e)
    msgs = [p["message"] for p in flows.validate(g, MODELS)]
    assert any("Region is not used" in m for m in msgs)

    # a placeholder with no input is a problem; so is a bad default
    g2 = three_way_flow()
    g2["inputs"] = [{"name": "Price tolerance", "type": "number", "default": "cheap"}]
    msgs = [p["message"] for p in flows.validate(g2, MODELS) if p["level"] == "error"]
    assert any("{{Accept delivery charges}}" in m for m in msgs) and any("default is not valid" in m for m in msgs)

    # filter rules take values too, and JSON is written out as JSON
    m = medical_flow()
    m["inputs"] = [{"name": "Page type", "type": "text", "default": "lab report"},
                   {"name": "Patient", "type": "json"}]
    e5 = next(e for e in m["edges"] if e["id"] == "e5")
    e5["data"]["rule"]["value"] = "{{ page type }}"
    flows.nodes_by_id(m)["extract"]["data"]["instructions"] += " Patient: {{Patient}}"
    assert not [p for p in flows.validate(m, MODELS) if p["level"] == "error"]
    f = flows.apply_values(m, flows.resolve_values(m, {"Patient": '{"id": 7}'}))
    assert next(e for e in f["edges"] if e["id"] == "e5")["data"]["rule"]["value"] == "lab report"
    assert 'Patient: {"id": 7}' in flows.nodes_by_id(f)["extract"]["data"]["instructions"]
    # testing one step asks only for the inputs that step reads
    assert [i["name"] for i in flows.prune_to(m, "classify")["inputs"]] == []
    assert [i["name"] for i in flows.prune_to(m, "extract")["inputs"]] == ["Page type", "Patient"]
    assert flows.rule_matches({"field": "ok", "op": "equals", "value": "yes"}, {"ok": True})


def test_images_and_text_files():
    from doc_engine import documents
    from doc_engine.samples import build_other_document

    # text: split into numbered pages; a form feed always starts a page
    name, data = build_other_document("doc_sample_trade_po_text")
    doc = documents.prepare(name, data)
    assert doc["kind"] == "text" and doc["pages"] == 2 and doc["page_tokens"] > 50
    pages = doc["content"].decode().split("\f")
    assert "PURCHASE ORDER" in pages[0] and "ORDER TERMS" in pages[1]
    long = documents.prepare("notes.txt", ("line of text\n" * 1000).encode(), text_page_chars=1000)
    assert long["pages"] == 14 and all(len(p) <= 1000 for p in long["content"].decode().split("\f"))
    assert documents.prepare("old.txt", "caf\xe9".encode("cp1252"))["content"].decode() == "café"

    # image: one page, scaled down, PNG kept for a lossless source
    name, data = build_other_document("doc_sample_trade_delivery_image")
    img = documents.prepare(name, data, image_max_px=800)
    assert img["kind"] == "image" and img["pages"] == 1 and img["media_type"] == "image/png"
    from PIL import Image
    assert max(Image.open(io.BytesIO(img["content"])).size) == 800 and 300 < img["page_tokens"] < 900

    # refused, with a reason a person can act on
    for bad_name, bad, words in (("letter.docx", b"PK\x03\x04....", "Save it as a PDF"), ("x.bin", b"\x00\x01\x02\x03", "not a file type"),
                                 ("empty.txt", b"  \n ", "holds no text"), ("broken.png", b"not an image", "could not be read")):
        with pytest.raises(ValueError, match=words):
            documents.prepare(bad_name, bad)

    # how each is sent
    step = flows.step_data(flows.nodes_by_id(three_way_flow())["check"])
    req = prompts.build_request(CFG, step=step, model="sonnet", doc_name="scan.png", pages=[1], pdf=None, sources=[],
                                instruction="map", max_tokens=500,
                                material={"kind": "image", "data": img["content"], "media_type": "image/png"})
    content = req["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    assert 'image above is page 1 of "scan.png"' in content[-1]["text"] and "[p. 1]" in content[-1]["text"]
    req = prompts.build_request(CFG, step=step, model="sonnet", doc_name="po.txt", pages=[1, 2], pdf=None, sources=[],
                                instruction="map", max_tokens=500, input_name="Purchase order",
                                material={"kind": "text", "pages": [(1, pages[0]), (2, pages[1])]},
                                refs=[{"kind": "source", "label": "Delivery note", "name": "scan.png", "pages": 1,
                                       "material": {"kind": "image", "data": img["content"], "media_type": "image/png"}}])
    content = req["messages"][0]["content"]
    assert [b["type"] for b in content] == ["text", "image", "text", "text"]
    assert content[0]["text"].startswith("Reference image.") and '<page number="2">' in content[2]["text"]
    assert "holds pages 1-2 of the input named" in content[-1]["text"] and "[Purchase order p. N]" in content[-1]["text"]

    # the estimate uses the document's own tokens per page
    g = three_way_flow()
    a = flows.estimate(g, {"src_po": 2, "src_dn": 2, "src_inv": 3}, CFG)
    b = flows.estimate(g, {"src_po": 2, "src_dn": 2, "src_inv": 3}, CFG, page_tokens={"src_po": 200})
    assert b["per_node"]["order"]["input_per_call"] < a["per_node"]["order"]["input_per_call"]


def test_public_endpoint_names_and_contract():
    from doc_engine.public_api import contract, flow_key

    # a flow's name as a caller may write it
    assert flow_key("Check an invoice against its order") == flow_key("check-an-invoice-against-its-order")
    assert flow_key("  Contract   FILE review ") == flow_key("contract_file_review") == "contract file review"
    assert flow_key("Report (v2)") != flow_key("Report") and flow_key("!!") == ""

    c = contract({"flow_id": "flow_x", "name": "Check an invoice", "description": "d", "published_version": 3},
                 three_way_flow(), "http://host")
    assert [f["name"] for f in c["files"]] == ["Purchase order", "Delivery note", "Invoice"]
    by = {v["name"]: v for v in c["values"]}
    assert by["Price tolerance"] == {"name": "Price tolerance", "type": "number", "required": False, "default": 0.5,
                                     "description": by["Price tolerance"]["description"]}
    assert by["Accept delivery charges"]["type"] == "yesno" and by["Accept delivery charges"]["default"] is False
    assert c["version"] == 3 and c["outputs"] and c["submit_url"] == "http://host/api/v1/flows/flow_x/jobs"
    # an input with no default is required
    g = three_way_flow()
    g["inputs"][0]["default"] = None
    assert {v["name"]: v["required"] for v in contract({"flow_id": "f", "name": "n", "published_version": 1}, g)["values"]}["Price tolerance"] is True


def test_meaning_ignores_layout_only():
    a = {"nodes": [{"id": "s", "type": "source", "position": {"x": 1, "y": 2}, "data": {"title": "File"}},
                   {"id": "t", "type": "step", "position": {"x": 5, "y": 2}, "data": {"title": "Sum"}}],
         "edges": [{"id": "e1", "source": "s", "target": "t", "data": {"instruction": "map"}}]}
    b = {"nodes": [{"id": "t", "type": "step", "position": {"x": 90, "y": 9}, "data": {"title": "Sum"}},
                   {"id": "s", "type": "source", "position": {"x": 1, "y": 2}, "data": {"title": "File"}}],
         "edges": [{"id": "other", "source": "s", "target": "t", "data": {"instruction": "map"}}], "inputs": []}
    assert flows.meaning(a) == flows.meaning(b)
    b["nodes"][0]["data"]["title"] = "Summarize"
    assert flows.meaning(a) != flows.meaning(b)
