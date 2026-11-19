"""The flow model: a graph of source, step and output nodes whose connections carry the instruction.

Vocabulary (kept from the brief):
  unit        one page of a source file
  item        anything a step can consume: a unit, or the output of an earlier step
  window      a group of consecutive items, defined by a size and an overlap
  step        a model call template: prompt blocks, model, limits, output contract
  instruction how a step is applied to the items arriving on its connection:
                map     one call per window of items
                reduce  one call over all the items
                filter  keep the items whose earlier output matches a rule, then one call per kept item
                fold    designed, not built
  flow        a versioned graph of steps
  job         one execution of one flow against one document per source
  task        one model call within a job; what the scheduler schedules

A flow may have several sources. Each is a named input (its title) that takes one document.
A step has exactly one *material* connection, which it works through by its instruction, and any
number of *reference* connections. A reference hands the step something whole on every call: the
finished outputs of another step, or a complete source document. A step waits for its references.

Graph shape (the same JSON the canvas edits):
  {"nodes": [{"id", "type": "source"|"step"|"output", "position": {"x","y"}, "data": {...}}],
   "edges": [{"id", "source", "target", "data": {"role": "material"|"reference",
                                                  "instruction", "window", "overlap", "consume", "rule"}}],
   "inputs": [{"name", "type": "text"|"number"|"choice"|"yesno"|"json", "choices": [...], "default", "description"}]}

Value inputs are the small values a caller sends with the documents. A step's prompt and a filter's
rule refer to one as {{Name}}. They are filled in once, when the job is submitted: the job keeps its
own copy of the graph with every {{Name}} replaced, so planning, caching and the worker never see a
placeholder. An input with no default must be supplied.
"""
from __future__ import annotations

import copy
import json
import math
import re
import uuid
from typing import Any

from .config import THINKING_LEVELS, Section

INSTRUCTIONS = ("map", "reduce", "filter")
BUILT = ("map", "reduce", "filter")
FIELD_TYPES = ("string", "number", "boolean", "enum", "list", "table")
VALUE_TYPES = ("text", "number", "choice", "yesno", "json")
VALUE_TYPE_LABEL = {"text": "text", "number": "a number", "choice": "one of the listed choices",
                    "yesno": "yes or no", "json": "JSON"}
RULE_OPS = ("equals", "not_equals", "in", "contains", "is_true", "is_false", "greater_than", "less_than")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------- graph helpers

def nodes_by_id(graph: dict) -> dict[str, dict]:
    return {n["id"]: n for n in graph.get("nodes", [])}


def incoming(graph: dict, node_id: str) -> list[dict]:
    return [e for e in graph.get("edges", []) if e["target"] == node_id]


def outgoing(graph: dict, node_id: str) -> list[dict]:
    return [e for e in graph.get("edges", []) if e["source"] == node_id]


def edge_data(edge: dict, source_type: str) -> dict:
    """Edge settings with defaults filled in."""
    d = dict(edge.get("data") or {})
    d["role"] = "reference" if d.get("role") == "reference" else "material"
    d.setdefault("instruction", "map")
    d.setdefault("window", 1)
    d.setdefault("overlap", 0)
    if not d.get("consume"):
        d["consume"] = "pages" if (source_type == "source" or d["instruction"] == "filter") else "outputs"
    if source_type == "source":
        d["consume"] = "pages"
    return d


def is_reference(edge: dict) -> bool:
    return (edge.get("data") or {}).get("role") == "reference"


def material_edges(graph: dict, node_id: str) -> list[dict]:
    nodes = nodes_by_id(graph)
    return [e for e in incoming(graph, node_id) if e["source"] in nodes and not is_reference(e)]


def material_edge(graph: dict, node_id: str) -> dict | None:
    """The one connection a step works through (None when it has none, or more than one)."""
    m = material_edges(graph, node_id)
    return m[0] if len(m) == 1 else None


def reference_edges(graph: dict, node_id: str) -> list[dict]:
    nodes = nodes_by_id(graph)
    return [e for e in incoming(graph, node_id) if e["source"] in nodes and is_reference(e)]


def sources(graph: dict) -> list[dict]:
    """Source nodes, top to bottom as drawn."""
    out = [n for n in graph.get("nodes", []) if n["type"] == "source"]
    return sorted(out, key=lambda n: ((n.get("position") or {}).get("y", 0), (n.get("position") or {}).get("x", 0)))


def multi_source(graph: dict) -> bool:
    return len(sources(graph)) > 1


def node_title(node: dict | None) -> str:
    if node is None:
        return ""
    return str((node.get("data") or {}).get("title") or node["type"].title()).strip()


def lineage_source(graph: dict, node_id: str) -> str | None:
    """The source whose pages reach this node through material connections."""
    nodes = nodes_by_id(graph)
    seen: set[str] = set()
    cur: str | None = node_id
    while cur and cur not in seen and cur in nodes:
        if nodes[cur]["type"] == "source":
            return cur
        seen.add(cur)
        e = material_edge(graph, cur)
        cur = e["source"] if e else None
    return None


def step_data(node: dict) -> dict:
    """Step settings with defaults filled in."""
    d = dict(node.get("data") or {})
    d.setdefault("title", "Step")
    d.setdefault("system", "")
    d.setdefault("instructions", "")
    d.setdefault("model", "sonnet")
    d["max_tokens"] = int(d.get("max_tokens") or 1500)
    d.setdefault("thinking", "off")
    out = dict(d.get("output") or {})
    out.setdefault("type", "text")
    out.setdefault("fields", [])
    d["output"] = out
    d.setdefault("track_pages", True)
    exp = d.get("expected_output")
    d["expected_output"] = float(exp) if exp else round(0.6 * d["max_tokens"])
    return d


def has_prompt(d: dict) -> bool:
    return bool((d.get("system") or "").strip() or (d.get("instructions") or "").strip())


def thinking_label(level: str) -> str:
    return level if level in THINKING_LEVELS else "off"


def profile_key(flow_id: str | None, node_id: str, model: str, thinking: str) -> str:
    return f"{flow_id or 'adhoc'}:{node_id}:{model}:{thinking_label(thinking)}"


def meaning(graph: dict | None) -> dict:
    """A graph without its layout: what runs, not where the blocks sit. Two graphs with the same meaning
    behave the same, so moving a block does not make a draft differ from a saved version."""
    g = graph or {}
    return {
        "nodes": sorted(({"id": n.get("id"), "type": n.get("type"), "data": n.get("data") or {}}
                         for n in g.get("nodes") or []), key=lambda n: str(n["id"])),
        "edges": sorted(({"source": e.get("source"), "target": e.get("target"), "data": e.get("data") or {}}
                         for e in g.get("edges") or []), key=lambda e: (str(e["source"]), str(e["target"]))),
        "inputs": g.get("inputs") or [],
    }


def windows(n: int, size: int, overlap: int) -> list[list[int]]:
    """Index groups for n consecutive items. 150 items at size 4, overlap 1 gives 50 windows."""
    size = max(1, int(size))
    overlap = max(0, min(int(overlap), size - 1))
    if n <= 0:
        return []
    step = size - overlap
    out = []
    start = 0
    while True:
        out.append(list(range(start, min(start + size, n))))
        if start + size >= n:
            break
        start += step
    return out


def window_count(n: int, size: int, overlap: int) -> int:
    size = max(1, int(size))
    overlap = max(0, min(int(overlap), size - 1))
    if n <= 0:
        return 0
    if n <= size:
        return 1
    return 1 + math.ceil((n - size) / (size - overlap))


# ---------------------------------------------------------------- output contract

def json_schema(fields: list[dict]) -> dict:
    props: dict[str, Any] = {}
    required = []
    for f in fields:
        name = (f.get("name") or "").strip()
        if not name:
            continue
        t = f.get("type", "string")
        desc = (f.get("description") or "").strip()
        if t == "number":
            s: dict[str, Any] = {"type": "number"}
        elif t == "boolean":
            s = {"type": "boolean"}
        elif t == "enum":
            s = {"type": "string", "enum": [str(v) for v in (f.get("values") or [])]}
        elif t == "list":
            s = {"type": "array", "items": {"type": "string"}}
        elif t == "table":
            cols = [c for c in (f.get("columns") or []) if str(c).strip()]
            s = {"type": "array", "items": {"type": "object",
                                            "properties": {str(c): {"type": ["string", "number", "null"]} for c in cols},
                                            "required": [str(c) for c in cols]}}
        else:
            s = {"type": "string"}
        if desc:
            s["description"] = desc
        props[name] = s
        required.append(name)
    return {"type": "object", "properties": props, "required": required}


def rule_matches(rule: dict, data: dict | None) -> bool:
    if not rule or not isinstance(data, dict):
        return False
    v = data.get(rule.get("field", ""))
    op = rule.get("op", "equals")
    target = rule.get("value")
    def norm(x: Any) -> str:           # yes/no and true/false compare equal, whichever side they are on
        k = str(x).strip().lower()
        return {"yes": "true", "no": "false"}.get(k, k)
    if op == "equals":
        return v is not None and norm(v) == norm(target)
    if op == "not_equals":
        return v is None or norm(v) != norm(target)
    if op == "in":
        opts = target if isinstance(target, list) else [s for s in str(target or "").split(",")]
        return v is not None and norm(v) in {norm(o) for o in opts}
    if op == "contains":
        if isinstance(v, list):
            return norm(target) in {norm(x) for x in v}
        return v is not None and norm(target) in norm(v)
    if op == "is_true":
        return v is True or norm(v) in ("true", "1")
    if op == "is_false":
        return v is False or norm(v) in ("false", "0")
    try:
        if op == "greater_than":
            return float(v) > float(target)
        if op == "less_than":
            return float(v) < float(target)
    except (TypeError, ValueError):
        return False
    return False


def describe_rule(rule: dict | None) -> str:
    if not rule or not rule.get("field"):
        return "no rule"
    op = {"equals": "is", "not_equals": "is not", "in": "is one of", "contains": "contains", "is_true": "is true",
          "is_false": "is false", "greater_than": ">", "less_than": "<"}.get(rule.get("op", "equals"), "is")
    if rule.get("op") in ("is_true", "is_false"):
        return f"{rule['field']} {op}"
    return f"{rule['field']} {op} {rule.get('value', '')}"


# ---------------------------------------------------------------- value inputs

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}\n]+?)\s*\}\}")


def value_key(name: Any) -> str:
    """Names match without regard to case or spacing: {{ tolerance }} is the input Tolerance."""
    return " ".join(str(name or "").split()).lower()


def value_inputs(graph: dict) -> list[dict]:
    """The flow's declared value inputs, with defaults filled in. `default` is None when there is none."""
    out = []
    for i in graph.get("inputs") or []:
        if not isinstance(i, dict):
            continue
        t = i.get("type") if i.get("type") in VALUE_TYPES else "text"
        default = i.get("default")
        if default == "" or default == []:
            default = None
        out.append({"name": " ".join(str(i.get("name") or "").split()), "type": t,
                    "choices": [str(c).strip() for c in (i.get("choices") or []) if str(c).strip()],
                    "default": default, "description": str(i.get("description") or "").strip()})
    return out


def placeholders(text: Any) -> list[str]:
    return [m.group(1) for m in _PLACEHOLDER.finditer(text)] if isinstance(text, str) else []


def _rule_texts(rule: dict | None) -> list[str]:
    v = (rule or {}).get("value")
    return [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str)]


def value_uses(graph: dict) -> list[tuple[str, str, str | None, str | None]]:
    """Every {{Name}} in the flow: (key, name as written, node id, edge id)."""
    out = []
    for n in graph.get("nodes", []):
        if n["type"] != "step":
            continue
        d = n.get("data") or {}
        for text in (d.get("system"), d.get("instructions")):
            out += [(value_key(p), p, n["id"], None) for p in placeholders(text)]
    for e in graph.get("edges", []):
        for text in _rule_texts((e.get("data") or {}).get("rule")):
            out += [(value_key(p), p, e["target"], e["id"]) for p in placeholders(text)]
    return out


def coerce_value(inp: dict, raw: Any, max_chars: int = 20000) -> Any:
    """`raw` as a value of the input's type, or ValueError saying what is wrong with it."""
    name, t = inp["name"], inp["type"]
    bad = ValueError(f'Input "{name}" must be {VALUE_TYPE_LABEL[t]}.')
    if t == "number":
        if isinstance(raw, bool):
            raise bad
        if isinstance(raw, (int, float)):
            v = float(raw)
        else:
            try:
                v = float(str(raw).strip().replace(",", ""))
            except ValueError:
                raise bad from None
        if not math.isfinite(v):
            raise bad
        return int(v) if v == int(v) else v
    if t == "yesno":
        if isinstance(raw, bool):
            return raw
        k = str(raw).strip().lower()
        if k in ("yes", "true", "1", "y"):
            return True
        if k in ("no", "false", "0", "n"):
            return False
        raise bad
    if t == "choice":
        for c in inp["choices"]:
            if value_key(c) == value_key(raw):
                return c
        raise ValueError(f'Input "{name}" must be one of: {", ".join(inp["choices"])}.')
    if t == "json":
        v = raw
        if isinstance(raw, str):
            try:
                v = json.loads(raw)
            except json.JSONDecodeError:
                raise ValueError(f'Input "{name}" is not valid JSON.') from None
        if len(json.dumps(v, ensure_ascii=False)) > max_chars:
            raise ValueError(f'Input "{name}" is longer than {max_chars:,} characters. Send long content as a file.')
        return v
    if isinstance(raw, (dict, list)):
        raise bad
    v = str(raw)
    if len(v) > max_chars:
        raise ValueError(f'Input "{name}" is longer than {max_chars:,} characters. Send long content as a file.')
    return v


def resolve_values(graph: dict, given: dict | None, max_chars: int = 20000) -> dict[str, Any]:
    """The value of every declared input for one run: what was sent, else the default.
    Raises ValueError naming every input that is missing, wrong, or not declared."""
    given = given or {}
    if not isinstance(given, dict):
        raise ValueError("values must be an object of input name to value")
    declared = value_inputs(graph)
    sent = {value_key(k): v for k, v in given.items()}
    errors: list[str] = []
    out: dict[str, Any] = {}
    known = {value_key(i["name"]) for i in declared}
    for k in given:
        if value_key(k) not in known:
            errors.append(f'This flow has no input named "{k}".')
    for inp in declared:
        raw = sent.get(value_key(inp["name"]))
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raw = inp["default"]
            if raw is None:
                errors.append(f'Input "{inp["name"]}" is required and has no default.')
                continue
        try:
            out[inp["name"]] = coerce_value(inp, raw, max_chars)
        except ValueError as e:
            errors.append(str(e))
    if errors:
        raise ValueError(" ".join(errors))
    return out


def render_value(v: Any) -> str:
    """A value as it is written into a prompt or a rule."""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def apply_values(graph: dict, values: dict[str, Any]) -> dict:
    """A copy of the graph with every {{Name}} replaced by its value. Unknown names are left as written."""
    by_key = {value_key(k): render_value(v) for k, v in values.items()}
    if not by_key:
        return graph

    def fill(text: Any) -> Any:
        if not isinstance(text, str) or "{{" not in text:
            return text
        return _PLACEHOLDER.sub(lambda m: by_key.get(value_key(m.group(1)), m.group(0)), text)

    g = copy.deepcopy(graph)
    for n in g.get("nodes", []):
        if n["type"] == "step":
            d = n.setdefault("data", {})
            for f in ("system", "instructions"):
                if f in d:
                    d[f] = fill(d[f])
    for e in g.get("edges", []):
        rule = (e.get("data") or {}).get("rule")
        if rule and "value" in rule:
            rule["value"] = [fill(x) for x in rule["value"]] if isinstance(rule["value"], list) else fill(rule["value"])
    return g


def _validate_values(graph: dict, nodes: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    declared = value_inputs(graph)
    seen: set[str] = set()
    for inp in declared:
        name, k = inp["name"], value_key(inp["name"])
        if not name:
            out.append(problem("A flow input has no name."))
            continue
        if "{" in name or "}" in name:
            out.append(problem(f"The input name {name} cannot contain braces."))
        if k in seen:
            out.append(problem(f"Two flow inputs are both named {name}. Give each its own name."))
        seen.add(k)
        if inp["type"] == "choice" and not inp["choices"]:
            out.append(problem(f"The input {name} needs its list of choices."))
        elif inp["default"] is not None:
            try:
                coerce_value(inp, inp["default"])
            except ValueError as e:
                out.append(problem(f"The default is not valid. {e}"))
    used: set[str] = set()
    reported: set[tuple] = set()
    for k, written, node_id, edge_id in value_uses(graph):
        used.add(k)
        if k not in seen and (k, node_id, edge_id) not in reported:
            reported.add((k, node_id, edge_id))
            title = node_title(nodes.get(node_id)) or "A step"
            where = f"The filter into {title}" if edge_id else title
            out.append(problem(f"{where} uses {{{{{written}}}}}, but the flow has no input with that name. "
                               f"Add it under Inputs.", node_id, edge_id))
    for inp in declared:
        if inp["name"] and value_key(inp["name"]) not in used:
            out.append(problem(f"The input {inp['name']} is not used by any step.", level="warning"))
    return out


# ---------------------------------------------------------------- validation

def problem(message: str, node_id: str | None = None, edge_id: str | None = None, level: str = "error") -> dict:
    return {"message": message, "node_id": node_id, "edge_id": edge_id, "level": level}


def validate(graph: dict, models: list[str]) -> list[dict]:
    """Everything that would stop this flow from running, in plain words."""
    out: list[dict] = []
    nodes = nodes_by_id(graph)
    if not nodes:
        return [problem("The flow is empty. Add a source, a step and an output.")]
    sources = [n for n in nodes.values() if n["type"] == "source"]
    outputs = [n for n in nodes.values() if n["type"] == "output"]
    steps = [n for n in nodes.values() if n["type"] == "step"]
    if len(sources) == 0:
        out.append(problem("Add a source."))
    if len(sources) > 1:
        seen_titles: dict[str, str] = {}
        for n in sources:
            t = node_title(n).lower()
            if not str((n.get("data") or {}).get("title") or "").strip():
                out.append(problem("Each source needs a name when a flow has several.", n["id"]))
            elif t in seen_titles:
                out.append(problem(f"Two sources are both named {node_title(n)}. Give each its own name.", n["id"]))
            seen_titles[t] = n["id"]
    if not steps:
        out.append(problem("Add at least one step."))
    if not outputs:
        out.append(problem("Add an output."))

    for e in graph.get("edges", []):
        if e["source"] not in nodes or e["target"] not in nodes:
            out.append(problem("A connection points at a block that no longer exists.", edge_id=e["id"]))

    for n in nodes.values():
        title = (n.get("data") or {}).get("title") or n["type"].title()
        inc = [e for e in incoming(graph, n["id"]) if e["source"] in nodes]
        if n["type"] == "source":
            if inc:
                out.append(problem(f"{title} is a source and cannot receive a connection.", n["id"]))
            if not outgoing(graph, n["id"]):
                out.append(problem(f"{title} is not connected to a step.", n["id"]))
            continue
        refs = [e for e in inc if is_reference(e)]
        mats = [e for e in inc if not is_reference(e)]
        if len(inc) == 0:
            out.append(problem(f"{title} has no input. Connect something to it.", n["id"]))
            continue
        if n["type"] == "output":
            if len(inc) > 1 or refs:
                out.append(problem(f"{title} has {len(inc)} inputs. An output takes one, from a step.", n["id"]))
            elif nodes[inc[0]["source"]]["type"] != "step":
                out.append(problem(f"{title} must be fed by a step.", n["id"]))
            continue
        pairs = [e["source"] for e in inc]
        if len(set(pairs)) != len(pairs):
            out.append(problem(f"{title} is connected to the same block twice. Remove one connection.", n["id"]))
            continue
        if len(mats) == 0:
            out.append(problem(f"{title} has references but nothing to work through. Set one connection to Input.",
                               n["id"], refs[0]["id"]))
            continue
        if len(mats) > 1:
            out.append(problem(f"{title} has {len(mats)} inputs to work through. A step works through one. "
                               f"Set the others to Reference.", n["id"], mats[1]["id"]))
            continue
        for r in refs:
            if nodes[r["source"]]["type"] == "output":
                out.append(problem(f"{title} cannot use an output block as a reference.", n["id"], r["id"]))
        e = mats[0]
        src = nodes[e["source"]]

        # step
        d = step_data(n)
        if not has_prompt(d):
            out.append(problem(f"{title} needs a prompt", n["id"]))
        if d["model"] not in models:
            out.append(problem(f"{title} uses a model that is not configured ({d['model']}).", n["id"]))
        if d["max_tokens"] < 1:
            out.append(problem(f"{title} needs a max output above zero.", n["id"]))
        if d["thinking"] not in THINKING_LEVELS:
            out.append(problem(f"{title} has an unknown thinking setting.", n["id"]))
        if d["output"]["type"] == "schema":
            names = [(f.get("name") or "").strip() for f in d["output"]["fields"]]
            if not any(names):
                out.append(problem(f"{title} has a schema output with no fields.", n["id"]))
            if len(set(x for x in names if x)) != len([x for x in names if x]):
                out.append(problem(f"{title} has two schema fields with the same name.", n["id"]))
            for f in d["output"]["fields"]:
                if f.get("type") == "enum" and not f.get("values"):
                    out.append(problem(f"{title}: field {f.get('name')} needs its allowed values.", n["id"]))
        if not outgoing(graph, n["id"]):
            out.append(problem(f"{title} goes nowhere. Connect it to a step or an output.", n["id"], level="warning"))

        ed = edge_data(e, src["type"])
        ins = ed["instruction"]
        if ins == "fold":
            out.append(problem("Fold is not available yet. Use Map or Reduce.", n["id"], e["id"]))
        elif ins not in INSTRUCTIONS:
            out.append(problem(f"Unknown instruction on the connection into {title}.", n["id"], e["id"]))
        if ins == "map":
            if int(ed["window"]) < 1:
                out.append(problem(f"The window into {title} must be at least 1.", n["id"], e["id"]))
            if int(ed["overlap"]) >= int(ed["window"]):
                out.append(problem(f"The overlap into {title} must be smaller than the window.", n["id"], e["id"]))
        if ins == "filter":
            if src["type"] != "step":
                out.append(problem(f"The filter into {title} needs an earlier step to read a field from.", n["id"], e["id"]))
            else:
                sd = step_data(src)
                rule = ed.get("rule") or {}
                fields = [(f.get("name") or "").strip() for f in sd["output"]["fields"]]
                if sd["output"]["type"] != "schema":
                    out.append(problem(f"The filter into {title} needs {sd['title']} to have a schema output.", n["id"], e["id"]))
                elif not rule.get("field"):
                    out.append(problem(f"The filter into {title} needs a rule.", n["id"], e["id"]))
                elif rule["field"] not in fields:
                    out.append(problem(f"The filter into {title} uses a field {sd['title']} does not output ({rule['field']}).", n["id"], e["id"]))
                elif rule.get("op") not in ("is_true", "is_false") and rule.get("value") in (None, "", []):
                    out.append(problem(f"The filter into {title} needs a value to compare with.", n["id"], e["id"]))
        if ed["consume"] in ("outputs", "both") and src["type"] == "source":
            out.append(problem(f"{title} reads earlier outputs, but it is connected to the source.", n["id"], e["id"]))

    out += _validate_values(graph, nodes)

    # cycles
    if _has_cycle(graph, nodes):
        out.append(problem("The flow loops back on itself. Remove the connection that closes the loop."))
    return out


def _has_cycle(graph: dict, nodes: dict[str, dict]) -> bool:
    state: dict[str, int] = {}

    def visit(nid: str) -> bool:
        if state.get(nid) == 1:
            return True
        if state.get(nid) == 2:
            return False
        state[nid] = 1
        for e in outgoing(graph, nid):
            if e["target"] in nodes and visit(e["target"]):
                return True
        state[nid] = 2
        return False

    return any(visit(n) for n in nodes)


def topo_order(graph: dict) -> list[str]:
    nodes = nodes_by_id(graph)
    order: list[str] = []
    seen: set[str] = set()

    def visit(nid: str) -> None:
        if nid in seen:
            return
        seen.add(nid)
        for e in incoming(graph, nid):
            if e["source"] in nodes:
                visit(e["source"])
        order.append(nid)

    for n in nodes:
        visit(n)
    return order


def prune_to(graph: dict, node_id: str) -> dict:
    """The part of the flow needed to run one step: the step, everything before it, and an output for it."""
    nodes = nodes_by_id(graph)
    if node_id not in nodes:
        raise ValueError("that step is not in the flow")
    keep: set[str] = set()
    todo = [node_id]
    while todo:                       # the step, its material chain, and everything its references need
        cur = todo.pop()
        if cur in keep or cur not in nodes:
            continue
        keep.add(cur)
        todo.extend(e["source"] for e in incoming(graph, cur))
    target = nodes[node_id]
    pos = target.get("position") or {"x": 0, "y": 0}
    out_fmt = "table" if (target.get("data") or {}).get("output", {}).get("type") == "schema" else "text"
    out = {"id": "out_step_test", "type": "output", "position": {"x": pos["x"] + 300, "y": pos["y"] + 10},
           "data": {"title": f"{(target.get('data') or {}).get('title', 'Step')} output", "format": out_fmt}}
    pruned = {"nodes": [n for n in graph["nodes"] if n["id"] in keep] + [out],
              "edges": [e for e in graph["edges"] if e["source"] in keep and e["target"] in keep]
                       + [{"id": "e_step_test", "source": node_id, "target": "out_step_test", "data": {}}]}
    used = {u[0] for u in value_uses(pruned)}        # only the inputs this part of the flow reads
    pruned["inputs"] = [i for i in graph.get("inputs") or [] if value_key(i.get("name")) in used]
    return pruned


# ---------------------------------------------------------------- estimate

def estimate(graph: dict, pages: int | dict[str, int], cfg: Section, flow_id: str | None = None,
             profiles: dict[str, dict] | None = None, keep_ratios: dict[str, float] | None = None,
             page_tokens: dict[str, float] | None = None) -> dict:
    """Calls, tokens and cost for one run. `pages` is the page count of the document, or a
    {source node id: pages} map when the flow has several sources.

    Learned profiles are used where a step has them; otherwise the step's own settings.
    A filter's keep ratio comes from the last run of this flow when there is one, else 25%.
    `page_tokens` gives the input tokens per page for sources that are not PDFs ({source node id: tokens}).
    """
    page_tokens = page_tokens or {}
    src_of: dict[str, str] = {}             # the source each node's material comes from
    profiles = profiles or {}
    keep_ratios = keep_ratios or {}
    nodes = nodes_by_id(graph)
    by_source = pages if isinstance(pages, dict) else {}
    default_pages = 150 if isinstance(pages, dict) else int(pages)
    items: dict[str, int] = {}
    src_pages: dict[str, int] = {}          # pages of the source each node's material comes from
    per_node: dict[str, dict] = {}
    total = {"calls": 0, "output_tokens": 0.0, "input_tokens": 0.0, "cached_tokens": 0.0, "cost": 0.0}
    assumed = False
    for nid in topo_order(graph):
        n = nodes[nid]
        if n["type"] == "source":
            items[nid] = src_pages[nid] = int(by_source.get(nid, default_pages))
            src_of[nid] = nid
            per_node[nid] = {"items_out": items[nid]}
            continue
        e = material_edge(graph, nid)
        if e is None or e["source"] not in items:
            continue
        src = nodes[e["source"]]
        n_in = items[e["source"]]
        doc_pages = src_pages[nid] = src_pages.get(e["source"], default_pages)
        src_of[nid] = src_of.get(e["source"], "")
        if n["type"] == "output":
            items[nid] = n_in
            per_node[nid] = {"items_in": n_in, "items_out": n_in}
            continue
        d = step_data(n)
        ed = edge_data(e, src["type"])
        ins = ed["instruction"]
        kept = n_in
        if ins == "reduce":
            calls = 1 if n_in > 0 else 0
        elif ins == "filter":
            ratio = keep_ratios.get(nid)
            if ratio is None:
                ratio = 0.25
                assumed = True
            kept = max(1, round(n_in * ratio)) if n_in else 0
            calls = kept
        else:
            calls = window_count(n_in, ed["window"], ed["overlap"])
        m = cfg.models.get(d["model"]) or next(iter(cfg.models.values()))
        pdf_page = float(m.get("input_tokens_per_page", 1728))
        per_page = float(page_tokens.get(src_of[nid]) or pdf_page)
        prof = profiles.get(profile_key(flow_id, nid, d["model"], d["thinking"])) or {}
        learned = (prof.get("n") or 0) >= 3
        out_per = prof["out_mean"] if learned else d["expected_output"]
        static_tokens = text_tokens(d["system"]) + text_tokens(d["instructions"]) + 150
        if ed["consume"] in ("pages", "both"):
            pages_per = doc_pages / max(1, calls) if ins == "reduce" else (1 if ins == "filter" else
                                                                             min(int(ed["window"]), max(1, n_in)))
            dyn = pages_per * per_page
        else:
            dyn = 0.0
        if ed["consume"] in ("outputs", "both") and src["type"] == "step":
            up = per_node.get(src["id"], {}).get("out_per", 800)
            per_call_items = n_in if ins == "reduce" else (1 if ins == "filter" else min(int(ed["window"]), max(1, n_in)))
            dyn += per_call_items * up
        ref_tokens = 0.0                     # sent whole with every call of this step
        for r in reference_edges(graph, nid):
            rn = nodes[r["source"]]
            if rn["type"] == "source":
                ref_tokens += items.get(rn["id"], 0) * float(page_tokens.get(rn["id"]) or pdf_page)
            elif rn["id"] in per_node:
                ref_tokens += per_node[rn["id"]].get("items_out", 0) * per_node[rn["id"]].get("out_per", 800)
        dyn += ref_tokens
        cacheable = static_tokens >= float(m.get("cache_min_tokens", 1024)) and calls >= 2
        price = m.pricing
        if cacheable:
            in_cost = (static_tokens * price.cache_write + (calls - 1) * static_tokens * price.cache_read
                       + calls * dyn * price.input) / 1e6
            cached = (calls - 1) * static_tokens
        else:
            in_cost = calls * (static_tokens + dyn) * price.input / 1e6
            cached = 0.0
        out_tokens = calls * out_per
        cost = in_cost + out_tokens * price.output / 1e6
        items[nid] = 1 if ins == "reduce" else calls
        per_node[nid] = {"items_in": n_in, "items_kept": kept if ins == "filter" else None, "calls": calls,
                         "items_out": items[nid], "out_per": out_per, "output_tokens": out_tokens, "cost": cost,
                         "model": d["model"], "learned": learned, "instruction": ins,
                         "window": ed["window"], "overlap": ed["overlap"],
                         "reference_tokens": ref_tokens, "input_per_call": static_tokens + dyn}
        total["calls"] += calls
        total["output_tokens"] += out_tokens
        total["input_tokens"] += calls * (static_tokens + dyn)
        total["cached_tokens"] += cached
        total["cost"] += cost
    total["per_node"] = per_node
    total["pages"] = sum(v for k, v in items.items() if nodes[k]["type"] == "source")
    total["assumed_filter_ratio"] = assumed
    return total


def text_tokens(text: str | None) -> float:
    """Rough token count for planning. The ledger corrects itself from real usage."""
    return len(text or "") / 3.6
