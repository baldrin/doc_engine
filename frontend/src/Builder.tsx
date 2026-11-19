import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  Background, BackgroundVariant, BaseEdge, Connection, Edge, EdgeLabelRenderer, EdgeProps, getBezierPath, Handle,
  MarkerType, MiniMap, Node, NodeProps, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState,
  useReactFlow, useViewport,
} from "@xyflow/react";
import {
  api, ApiError, AppConfig, defaultStep, Doc, EdgeData, Estimate, Field, Flow, fmtCost, fmtInt, fmtK, Graph,
  INSTRUCTION_COLOR, Instruction, isRef, modelLabel, navigate, Problem, ruleText, StepData, uid, useConfig,
  docSize, UPLOAD_ACCEPT, inputsFor, placeholder, placeholdersIn, renamePlaceholder, ValueInput, valueKey,
} from "./lib";
import ApiPanel from "./ApiPanel";
import { Icon, Link, Modal, toast, TopBar } from "./ui";
import { InputsEditor, loadValues, missingValues, saveValues, Values, ValuesForm, valuesToSend } from "./Values";

// ---------------------------------------------------------------- context shared with nodes and edges

interface Ctx {
  cfg: AppConfig | null;
  problems: Problem[];
  cacheable: Record<string, boolean>;   // step id -> its static prompt is long enough to be cached
  estimate: Estimate | null;
  /** The document chosen for a source block (for the estimate and test runs). */
  docFor: (sourceId: string) => Doc | null;
  /** True when the flow has several sources: each is then shown by its input name. */
  multi: boolean;
  selectedEdge: string | null;
  nodeTitle: (id: string) => string;
}
const BuilderCtx = createContext<Ctx>({ cfg: null, problems: [], estimate: null, docFor: () => null, multi: false, selectedEdge: null, cacheable: {}, nodeTitle: () => "" });

type FNode = Node<any>;
type FEdge = Edge<EdgeData>;

function toRF(graph: Graph): { nodes: FNode[]; edges: FEdge[] } {
  return {
    nodes: graph.nodes.map((n) => ({ id: n.id, type: n.type, position: n.position, data: n.data || {} })),
    edges: graph.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, type: "flow", data: e.data || {} })),
  };
}
function toGraph(nodes: FNode[], edges: FEdge[], inputs: ValueInput[] = []): Graph {
  return {
    inputs,
    nodes: nodes.map((n) => ({ id: n.id, type: n.type as any, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) }, data: n.data })),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target, data: (e.data || {}) as EdgeData })),
  };
}

// ---------------------------------------------------------------- nodes

function FlowNode({ id, type, data, selected }: NodeProps<FNode>) {
  const { cfg, problems, docFor, multi } = useContext(BuilderCtx);
  const doc = type === "source" ? docFor(id) : null;
  const mine = problems.filter((p) => p.node_id === id && p.level === "error");
  const isStep = type === "step";
  const d = data as StepData & { format?: string };
  const cls = ["fnode", `t-${type}`, selected ? "selected" : "", mine.length && !selected ? "problem" : ""].join(" ");
  const short = mine[0]?.message.replace(d.title || "", "").trim().replace(/^[:,]?\s*/, "");
  return (
    <div className={cls}>
      {type !== "source" ? <Handle type="target" position={Position.Left} className="port" /> : null}
      <div className="kind">
        <span>
          <Icon name={type === "source" ? "doc" : type === "output" ? "flag" : "step"} />
          {type === "source" ? "SOURCE" : type === "output" ? "OUTPUT" : selected ? "STEP · SELECTED" : "STEP"}
        </span>
        {mine.length ? <span role="img" aria-label={mine[0].message}><Icon name="warn" size={16} color="var(--warn-text)" /></span> : null}
      </div>
      <span className="name">{type === "source" && !multi ? doc?.name || d.title : d.title}</span>
      {type === "source" ? (
        <div className="chips">
          {multi && doc ? <span className="chip clip" title={doc.name}>{doc.name}</span> : null}
          <span className="chip">{doc ? `${doc.pages} page${doc.pages === 1 ? "" : "s"}` : "No file"}</span>
          {doc ? <span className="chip">{doc.kind === "image" ? "Image" : doc.kind === "text" ? "Text" : "PDF"}</span> : null}
        </div>
      ) : null}
      {isStep && mine.length ? <span className="needs">{short ? short[0].toUpperCase() + short.slice(1) : mine[0].message}</span> : null}
      {isStep && !mine.length ? (
        <div className="chips">
          <span className="chip">{modelLabel(cfg, d.model)}</span>
          {d.output?.type === "schema"
            ? <span className="chip schema">Schema: {d.output.fields?.[0]?.name || "fields"}</span>
            : <span className="chip">Text out</span>}
          {d.thinking && d.thinking !== "off" ? <span className="chip">Thinking {d.thinking}</span> : null}
        </div>
      ) : null}
      {type === "output" ? <div className="chips"><span className="chip">{d.format === "table" ? "Table" : "Text"}</span></div> : null}
      {type !== "output" ? <Handle type="source" position={Position.Right} className={"port" + (type === "source" ? " src" : "")} /> : null}
    </div>
  );
}
const nodeTypes = { source: FlowNode, step: FlowNode, output: FlowNode };

function FlowEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, markerEnd, target }: EdgeProps<FEdge>) {
  const { estimate, selectedEdge } = useContext(BuilderCtx);
  const { setEdges } = useReactFlow();
  const [path, lx, ly] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const ref = data?.role === "reference";
  const ins = ref ? undefined : data?.instruction;
  const per = estimate?.per_node?.[target];
  const color = INSTRUCTION_COLOR[ref ? "reference" : ins || "none"];
  let title = "", sub = "";
  if (ref) {
    title = "Reference";
    sub = "whole, on every call";
  } else if (ins === "map") {
    title = `Map ${data?.window ?? 1} / ${data?.overlap ?? 0}`;
    sub = per ? `${fmtInt(per.items_in)} → ${fmtInt(per.calls)} item${per.calls === 1 ? "" : "s"}` : "over windows";
  } else if (ins === "reduce") {
    title = "Reduce";
    sub = per ? `${fmtInt(per.items_in)} → 1 item` : "many in, one out";
  } else if (ins === "filter") {
    title = "Filter";
    const v = data?.rule?.value ? String(data.rule.value) : ruleText(data?.rule);
    sub = per ? `${v} · ${fmtInt(per.items_in)} → ${per.learned || !estimate?.assumed_filter_ratio ? "" : "~"}${fmtInt(per.items_kept)}` : v;
  }
  const select = () => setEdges((es) => es.map((e) => ({ ...e, selected: e.id === id })));
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd}
        style={{ stroke: color.line, strokeWidth: ref ? 1.75 : 2, strokeDasharray: ref ? "2 5" : ins === "filter" ? "6 4" : undefined }} />
      <EdgeLabelRenderer>
        {ins || ref ? (
          <button className={"edge-chip nodrag nopan" + (selectedEdge === id ? " on" : "")} onClick={select}
            style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly}px)`, borderColor: color.line }}>
            <span className="t" style={{ color: color.text }}>{title}</span>
            <span className="s">{sub}</span>
          </button>
        ) : per ? (
          <span className="edge-note" style={{ transform: `translate(-50%, -150%) translate(${lx}px, ${ly}px)` }}>
            {per.items_in === 1 ? "1 item" : `${fmtInt(per.items_in)} items`}
          </span>
        ) : null}
      </EdgeLabelRenderer>
    </>
  );
}
const edgeTypes = { flow: FlowEdge };

// ---------------------------------------------------------------- library

const TEMPLATES: Record<string, () => { type: "source" | "step" | "output"; data: any }> = {
  source: () => ({ type: "source", data: { title: "File", kind: "single" } }),
  blank: () => ({ type: "step", data: defaultStep("New step") }),
  classify: () => ({
    type: "step",
    data: {
      ...defaultStep("Classify page type"), model: "haiku", max_tokens: 300, expected_output: 40,
      system: "You classify single pages of a scanned document by type. Read the whole page, then choose the one type that best describes it, using the title and layout first and the content second. If nothing fits, choose other.",
      instructions: "Classify this page.",
      output: { type: "schema", fields: [{ name: "page_type", type: "enum", description: "The type of this page", values: ["letter", "report", "form", "table", "other"] }] },
    },
  }),
  summarize: () => ({
    type: "step",
    data: {
      ...defaultStep("Summarize window"), max_tokens: 1500, expected_output: 900,
      system: "You are given a small group of consecutive pages from a longer document. Other analysts receive the neighbouring pages and a later step combines everyone's notes, so your notes must stand on their own. Report what the pages say, in short plain statements, one fact per statement. Keep numbers and dates exact. Do not add anything the pages do not say. If part of a page cannot be read, say so.",
      instructions: "Write notes on the pages you were given.",
    },
  }),
  output: () => ({ type: "output", data: { title: "Output", format: "text" } }),
};

function Library({ onAdd, onInstruction, activeIns, canSetIns }: {
  onAdd: (key: string) => void; onInstruction: (i: Instruction) => void; activeIns?: string; canSetIns: boolean;
}) {
  const [q, setQ] = useState("");
  const show = (label: string) => !q || label.toLowerCase().includes(q.toLowerCase());
  const item = (key: string, icon: string, label: string) => show(label) ? (
    <button key={key} className="lib-item" draggable onDragStart={(e) => { e.dataTransfer.setData("application/de-block", key); e.dataTransfer.effectAllowed = "copy"; }}
      onClick={() => onAdd(key)} title="Drag onto the canvas, or click to add">
      <Icon name={icon} size={16} color="var(--text-2)" />{label}
    </button>
  ) : null;
  const ins = (key: Instruction | "fold", icon: string, label: string, desc: string) => show(label) ? (
    <button key={key} className={"lib-ins" + (activeIns === key ? " on" : "")} disabled={key === "fold" || !canSetIns}
      onClick={() => key !== "fold" && onInstruction(key)}
      title={key === "fold" ? "Fold is designed but not available yet" : canSetIns ? `Apply ${label} to the selected connection` : "Select a step or a connection first"}>
      <span className="name" style={{ color: INSTRUCTION_COLOR[key].text }}><Icon name={icon} size={16} />{label}{key === "fold" ? <span className="chip" style={{ marginLeft: "auto" }}>Soon</span> : null}</span>
      <span className="desc">{desc}</span>
    </button>
  ) : null;
  return (
    <aside className="library" aria-label="Block library">
      <div className="field">
        <label htmlFor="lib-search">Library</label>
        <input id="lib-search" className="input" type="search" placeholder="Search blocks" value={q} onChange={(e) => setQ(e.target.value)}
          style={{ background: "var(--surface-2)" }} />
      </div>
      <div className="lib-group"><span className="caps">Sources</span>{item("source", "doc", "File: PDF, image or text")}</div>
      <div className="lib-group"><span className="caps">Steps</span>
        {item("blank", "plus", "Blank step")}{item("classify", "bookmark", "Classify page type")}{item("summarize", "bookmark", "Summarize window")}
      </div>
      <div className="lib-group"><span className="caps">Instructions</span>
        {ins("map", "map", "Map", "Run over windows of items")}
        {ins("fold", "fold", "Fold", "Each call gets the last output")}
        {ins("reduce", "reduce", "Reduce", "Many in, exactly one out")}
        {ins("filter", "filter", "Filter", "Keep items that match a rule")}
      </div>
      <div className="lib-group"><span className="caps">Output</span>{item("output", "flag", "Output")}</div>
      <p className="hint">Drag a block onto the canvas, or press <kbd>/</kbd> to quick add. Drag from one block's dot to another to connect them.</p>
    </aside>
  );
}

// ---------------------------------------------------------------- properties panel

function SchemaEditor({ fields, onChange, cfg }: { fields: Field[]; onChange: (f: Field[]) => void; cfg: AppConfig | null }) {
  const set = (i: number, patch: Partial<Field>) => onChange(fields.map((f, k) => (k === i ? { ...f, ...patch } : f)));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {fields.map((f, i) => (
        <div className="schema-field" key={i}>
          <div className="schema-row">
            <input className="input" aria-label="Field name" placeholder="field_name" value={f.name} onChange={(e) => set(i, { name: e.target.value.replace(/\s+/g, "_") })} />
            <select className="select" aria-label="Field type" value={f.type} onChange={(e) => set(i, { type: e.target.value })}>
              {(cfg?.field_types || ["string"]).map((t) => <option key={t} value={t}>{t === "enum" ? "one of" : t}</option>)}
            </select>
            <button className="icon-btn" aria-label="Remove field" onClick={() => onChange(fields.filter((_, k) => k !== i))}><Icon name="x" /></button>
          </div>
          <input className="input" aria-label="Description" placeholder="What this field holds" value={f.description || ""} onChange={(e) => set(i, { description: e.target.value })} />
          {f.type === "enum" ? (
            <input className="input" aria-label="Allowed values" placeholder="Allowed values, comma separated" defaultValue={(f.values || []).join(", ")}
              onBlur={(e) => set(i, { values: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
          ) : null}
          {f.type === "table" ? (
            <input className="input" aria-label="Columns" placeholder="Columns, comma separated" defaultValue={(f.columns || []).join(", ")}
              onBlur={(e) => set(i, { columns: e.target.value.split(",").map((s) => s.trim().replace(/\s+/g, "_")).filter(Boolean) })} />
          ) : null}
        </div>
      ))}
      <button className="btn small" style={{ alignSelf: "flex-start", borderStyle: "dashed" }}
        onClick={() => onChange([...fields, { name: "", type: "string", description: "" }])}>+ Add field</button>
    </div>
  );
}

interface RefInfo { id: string; title: string; fromSource: boolean }

function StepPanel({ node, inEdge, upstream, refs, setRole, removeEdge, cfg, tab, setTab, update, updateEdge, onTest, onDone, estimate, titleRef, inputs, onManageInputs }: {
  inputs: ValueInput[]; onManageInputs: () => void;
  node: FNode; inEdge: FEdge | null; upstream: FNode | null; cfg: AppConfig | null; tab: string; setTab: (t: string) => void;
  refs: RefInfo[]; setRole: (edgeId: string, role: "material" | "reference") => void; removeEdge: (edgeId: string) => void;
  update: (patch: Partial<StepData>) => void; updateEdge: (patch: Partial<EdgeData>) => void; onTest: () => void; onDone: () => void;
  estimate: Estimate | null; titleRef: React.RefObject<HTMLInputElement>;
}) {
  const d = node.data as StepData;
  const model = cfg?.models.find((m) => m.key === d.model);
  const ed = (inEdge?.data || {}) as EdgeData;
  const ins = ed.instruction || "map";
  const per = estimate?.per_node?.[node.id];
  const fromSource = upstream?.type === "source";
  const consume = fromSource ? "pages" : ed.consume || (ins === "filter" ? "pages" : "outputs");
  // Whether the static prompt is long enough to be cached: the server's answer, by the planner's own rule.
  const cacheable = !!useContext(BuilderCtx).cacheable[node.id];
  const upFields: Field[] = upstream?.type === "step" ? (upstream.data.output?.fields || []) : [];
  const receives = !inEdge ? "Not connected yet"
    : ins === "reduce" ? `Receives ${per ? fmtInt(per.items_in) : "all"} ${fromSource ? "pages" : "outputs"} through Reduce`
    : ins === "filter" ? `Receives the items that pass the filter${per ? ` (about ${fmtInt(per.items_kept)})` : ""}`
    : (ed.window ?? 1) === 1 ? `Receives one ${fromSource ? "page" : "item"} at a time through Map`
    : `Receives windows of ${ed.window} ${fromSource ? "pages" : "items"} through Map`;
  // Inserting a flow input: {{Name}} goes in at the cursor of the prompt block last worked in.
  const sysRef = useRef<HTMLTextAreaElement>(null);
  const insRef = useRef<HTMLTextAreaElement>(null);
  const lastBlock = useRef<"system" | "instructions">("instructions");
  const touched = useRef(new Set<string>());
  useEffect(() => { touched.current = new Set(); lastBlock.current = "instructions"; }, [node.id]);
  const named = inputs.filter((i) => i.name.trim());
  const insert = (name: string) => {
    const key = lastBlock.current;
    const el = key === "system" ? sysRef.current : insRef.current;
    const text = (d[key] || "") as string;
    // At the cursor when the block has been worked in; otherwise at the end, on its own after a space.
    const pos = el && touched.current.has(key) ? Math.min(el.selectionStart ?? text.length, text.length) : text.length;
    const tag = (pos === text.length && text && !/\s$/.test(text) ? " " : "") + placeholder(name);
    update({ [key]: text.slice(0, pos) + tag + text.slice(pos) } as Partial<StepData>);
    setTimeout(() => { el?.focus(); el?.setSelectionRange(pos + tag.length, pos + tag.length); }, 0);
  };
  const offNote = model?.thinking_off === "effort_low" ? "This model always thinks. Off sends the lowest effort." : "";

  const modelRow = (
    <div className="grid2">
      <div className="field">
        <label htmlFor="m-model">Model</label>
        <select id="m-model" className="select" value={d.model} onChange={(e) => update({ model: e.target.value })}>
          {(cfg?.models || []).map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="m-max">Max output tokens</label>
        <input id="m-max" className="input" type="number" min={1} value={d.max_tokens} onChange={(e) => update({ max_tokens: Number(e.target.value) })} />
      </div>
    </div>
  );
  const contract = (
    <div className="field">
      <span className="label">Output contract</span>
      <div className="seg">
        <button aria-pressed={d.output.type === "text"} onClick={() => update({ output: { ...d.output, type: "text" } })}>Text</button>
        <button aria-pressed={d.output.type === "schema"} onClick={() => { update({ output: { ...d.output, type: "schema" } }); setTab("Output"); }}>Schema</button>
      </div>
    </div>
  );
  const track = (
    <label className="toggle" htmlFor="m-cite">
      <span><strong>Track source pages</strong><span>Every output knows which pages it covers</span></span>
      <input id="m-cite" type="checkbox" checked={d.track_pages !== false} onChange={(e) => update({ track_pages: e.target.checked })} />
    </label>
  );

  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span className="caps">Step</span>
        <input ref={titleRef} className="title-input" style={{ fontSize: 20, maxWidth: "100%" }} aria-label="Step name" value={d.title}
          onChange={(e) => update({ title: e.target.value })} />
        <span className="sub">{receives}</span>
      </div>
      <div className="tabs" role="tablist" aria-label="Step settings">
        {["Prompt", "Model", "Input", "Output"].map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>

      {tab === "Prompt" ? (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="label">Prompt blocks</span>
              <span className={"cache-tag" + (cacheable ? "" : " off")} title={cacheable ? "The static prompt is long enough to be cached and reused by every call of this step." : "Short prompts are not cached. Calls still work."}>
                {cacheable ? "Cache ready" : "Too short to cache"}
              </span>
            </div>
            <div className="block">
              <div className="bh"><strong>System</strong><span>Static</span></div>
              <label className="sr" htmlFor="p-sys">System prompt</label>
              <textarea id="p-sys" ref={sysRef} onFocus={() => { lastBlock.current = "system"; touched.current.add("system"); }} rows={5} value={d.system} placeholder="Who the model is and how it should work" onChange={(e) => update({ system: e.target.value })} />
            </div>
            <div className="block">
              <div className="bh"><strong>Instructions</strong><span>Static</span></div>
              <label className="sr" htmlFor="p-ins">Instructions</label>
              <textarea id="p-ins" ref={insRef} onFocus={() => { lastBlock.current = "instructions"; touched.current.add("instructions"); }} rows={3} value={d.instructions} placeholder="What to do with each input" onChange={(e) => update({ instructions: e.target.value })} />
            </div>
            <div className="insert-row">
              {named.length ? <span>Insert a flow input:</span> : <span>No flow inputs yet.</span>}
              {named.map((i) => <button key={i.name} title={`Insert ${placeholder(i.name)} where the cursor is`} onMouseDown={(e) => e.preventDefault()} onClick={() => insert(i.name)}>{i.name}</button>)}
              <button className="link" onClick={onManageInputs}>{named.length ? "Manage inputs" : "Add one"}</button>
            </div>
            <div className="inserted">
              <span>Inserted from {upstream ? (fromSource ? "the source" : upstream.data.title) : "the input"}:</span>
              {consume !== "outputs" ? <span className="pill">pages</span> : null}
              {consume !== "pages" ? <span className="pill">outputs</span> : null}
            </div>
            {refs.length ? (
              <div className="inserted">
                <span>References, whole on every call:</span>
                {refs.map((r) => <span className="pill gray" key={r.id}>{r.title}{r.fromSource ? " (whole file)" : ""}</span>)}
              </div>
            ) : null}
          </div>
          {modelRow}
          {contract}
          {track}
        </>
      ) : null}

      {tab === "Model" ? (
        <>
          {modelRow}
          <div className="field">
            <span className="label">Thinking</span>
            <div className="seg">
              {(cfg?.thinking_levels || ["off"]).map((t) => (
                <button key={t} aria-pressed={(d.thinking || "off") === t} onClick={() => update({ thinking: t })}>{t[0].toUpperCase() + t.slice(1)}</button>
              ))}
            </div>
            <p className="hint">Thinking counts against max output and the output quota. {offNote}</p>
          </div>
          <div className="field">
            <label htmlFor="m-exp">Expected output tokens per call</label>
            <input id="m-exp" className="input" type="number" min={1} placeholder={`${Math.round(0.6 * d.max_tokens)} (60% of max)`}
              value={d.expected_output ?? ""} onChange={(e) => update({ expected_output: e.target.value ? Number(e.target.value) : null })} />
            <p className="hint">The scheduler counts each call in flight at this size until it has seen three real calls of this step.
              {per?.learned ? ` Learned so far: about ${fmtInt(per.out_per)} tokens.` : ""}</p>
          </div>
          {model ? (
            <p className="hint">{model.label}: {fmtK(model.otpm)} output and {fmtK(model.itpm)} input tokens per minute.
              ${model.pricing.input} in, ${model.pricing.output} out per million tokens.</p>
          ) : null}
        </>
      ) : null}

      {tab === "Input" ? (
        <>
        {!inEdge ? <p className="empty">{refs.length ? "This step has references but nothing to work through. Choose one below as its input, or connect another block." : "Connect something to this step first. Drag from another block's right dot to this block's left dot."}</p> : (
          <>
            <div className="ref-row">
              <span className="who"><Icon name={fromSource ? "doc" : "step"} size={15} />{upstream?.data.title || "Input"}</span>
              <span className="what">Works through this</span>
            </div>
            <div className="field">
              <span className="label">Instruction</span>
              <div className="seg">
                {(["map", "reduce", "filter"] as Instruction[]).map((i) => (
                  <button key={i} aria-pressed={ins === i} disabled={i === "filter" && fromSource}
                    title={i === "filter" && fromSource ? "A filter reads a field from an earlier step" : ""}
                    onClick={() => updateEdge({ instruction: i, consume: undefined })}>{i[0].toUpperCase() + i.slice(1)}</button>
                ))}
              </div>
              <p className="hint">{ins === "map" ? "One call per window of consecutive items."
                : ins === "reduce" ? "One call that receives every item at once."
                : "Keeps the items whose earlier output matches the rule, then makes one call per kept item."}</p>
            </div>
            {ins === "map" ? (
              <div className="grid2">
                <div className="field"><label htmlFor="e-win">Window size</label>
                  <input id="e-win" className="input" type="number" min={1} value={ed.window ?? 1} onChange={(e) => { const w = Math.max(1, Number(e.target.value)); updateEdge({ window: w, overlap: Math.min(ed.overlap ?? 0, w - 1) }); }} /></div>
                <div className="field"><label htmlFor="e-ov">Overlap</label>
                  <input id="e-ov" className="input" type="number" min={0} max={Math.max(0, (ed.window ?? 1) - 1)} value={ed.overlap ?? 0} onChange={(e) => updateEdge({ overlap: Math.min(Math.max(0, Number(e.target.value)), Math.max(0, (ed.window ?? 1) - 1)) })} /></div>
              </div>
            ) : null}
            {ins === "map" && fromSource && per && per.items_in <= (ed.window ?? 1) && (ed.window ?? 1) > 1 ? (
              <p className="hint">The file chosen now has {fmtInt(per.items_in)} page{per.items_in === 1 ? "" : "s"}, so it fits in one call and these two settings change nothing for it. They apply when the flow runs on a longer file.</p>
            ) : null}
            {ins === "filter" ? (
              <div className="field">
                <span className="label">Keep items where</span>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <select className="select" aria-label="Field" value={ed.rule?.field || ""} onChange={(e) => updateEdge({ rule: { op: "equals", ...ed.rule, field: e.target.value } })}>
                    <option value="">Choose a field</option>
                    {upFields.map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}
                  </select>
                  <select className="select" aria-label="Comparison" value={ed.rule?.op || "equals"} onChange={(e) => updateEdge({ rule: { field: "", ...ed.rule, op: e.target.value } })}>
                    {(cfg?.rule_ops || ["equals"]).map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
                  </select>
                </div>
                {ed.rule?.op !== "is_true" && ed.rule?.op !== "is_false" ? (() => {
                  const f = upFields.find((x) => x.name === ed.rule?.field);
                  return f?.type === "enum" && ed.rule?.op !== "in" ? (
                    <select className="select" aria-label="Value" value={ed.rule?.value ?? ""} onChange={(e) => updateEdge({ rule: { field: "", op: "equals", ...ed.rule, value: e.target.value } })}>
                      <option value="">Choose a value</option>
                      {(f.values || []).map((v) => <option key={v} value={v}>{v}</option>)}
                      {named.length ? <optgroup label="Sent with each run">{named.map((i) => <option key={i.name} value={placeholder(i.name)}>Input: {i.name}</option>)}</optgroup> : null}
                    </select>
                  ) : (
                    <input className="input" aria-label="Value" placeholder="Value" value={ed.rule?.value ?? ""} onChange={(e) => updateEdge({ rule: { field: "", op: "equals", ...ed.rule, value: e.target.value } })} />
                  );
                })() : null}
                {named.length && ed.rule?.op !== "is_true" && ed.rule?.op !== "is_false" ? (
                  <div className="insert-row">
                    <span>Or compare with a flow input:</span>
                    {named.map((i) => <button key={i.name} onClick={() => updateEdge({ rule: { field: "", op: "equals", ...ed.rule, value: placeholder(i.name) } })}>{i.name}</button>)}
                  </div>
                ) : null}
                {upstream?.type === "step" && upstream.data.output?.type !== "schema" ? (
                  <p className="hint" style={{ color: "var(--warn-text)" }}>{upstream.data.title} needs a schema output for a filter to read.</p>
                ) : null}
              </div>
            ) : null}
            {!fromSource ? (
              <div className="field">
                <span className="label">What each call receives</span>
                <div className="seg">
                  <button aria-pressed={consume === "outputs"} onClick={() => updateEdge({ consume: "outputs" })}>Earlier outputs</button>
                  <button aria-pressed={consume === "pages"} onClick={() => updateEdge({ consume: "pages" })}>Their pages</button>
                  <button aria-pressed={consume === "both"} onClick={() => updateEdge({ consume: "both" })}>Both</button>
                </div>
              </div>
            ) : <p className="hint">This step reads pages straight from the file.</p>}
            {per ? <p className="hint">For this file: {fmtInt(per.items_in)} items in, {fmtInt(per.calls)} calls, about {fmtK(per.output_tokens)} output tokens.</p> : null}
          </>
        )}
          <div className="field">
            <span className="label">References</span>
            {refs.map((r) => (
              <div className="ref-row" key={r.id}>
                <span className="who" title={`${r.title}: ${r.fromSource ? "the whole file" : "its finished output"}`}><Icon name={r.fromSource ? "doc" : "step"} size={15} /><span>{r.title}</span></span>
                <button className="btn small" title="Work through this instead. The current input becomes a reference." onClick={() => setRole(r.id, "material")}>Make input</button>
                <button className="icon-btn" aria-label={`Remove reference ${r.title}`} onClick={() => removeEdge(r.id)}><Icon name="x" /></button>
              </div>
            ))}
            <p className="hint">{refs.length
              ? `A reference is sent whole with every call of this step, and the step waits for it. Name it in the prompt, for example "the reference named ${refs[0].title}".${per?.reference_tokens ? ` About ${fmtK(per.reference_tokens)} input tokens per call.` : ""}`
              : "None. Connect a second block to this step to give every call something extra to read: another step's finished output, or a whole file."}</p>
          </div>
        </>
      ) : null}

      {tab === "Output" ? (
        <>
          {contract}
          {d.output.type === "schema" ? (
            <div className="field">
              <span className="label">Fields</span>
              <SchemaEditor fields={d.output.fields || []} cfg={cfg} onChange={(fields) => update({ output: { ...d.output, fields } })} />
              <p className="hint">The reply must be one JSON object with these fields. A reply that does not match is retried.</p>
            </div>
          ) : <p className="hint">The step returns plain text. Choose Schema to get named fields that a filter or a table can use.</p>}
          {track}
        </>
      ) : null}

      <div style={{ display: "flex", gap: 8, marginTop: "auto", flexWrap: "wrap" }}>
        <button className="btn" style={{ flex: "1 1 120px", justifyContent: "center", height: 38 }} onClick={onTest}>Test this step</button>
        <button className="btn primary" style={{ flex: "1 1 120px", justifyContent: "center", height: 38 }} onClick={onDone}>Done</button>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- dialogs

function DocPicker({ docs, value, onChange, onUploaded, label = "File" }: { docs: Doc[]; value: string; onChange: (id: string) => void; onUploaded: (d: Doc) => void; label?: string }) {
  const pickId = `doc-pick-${label.replace(/\W+/g, "-")}`;
  const [busy, setBusy] = useState(false);
  const upload = async (file: File) => {
    setBusy(true);
    try {
      const d = await api<Doc>(`/api/documents?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file, headers: { "Content-Type": "application/octet-stream" } });
      onUploaded(d);
      toast(`${d.name} uploaded (${docSize(d)})`);
    } catch (e: any) { toast(e.message, true); }
    setBusy(false);
  };
  return (
    <div className="field">
      <label htmlFor={pickId}>{label}</label>
      <div style={{ display: "flex", gap: 8 }}>
        <select id={pickId} className="select" style={{ minWidth: 0 }} value={value} onChange={(e) => onChange(e.target.value)}>
          {!value ? <option value="">Choose a file</option> : null}
          {docs.map((d) => <option key={d.document_id} value={d.document_id}>{d.name} · {docSize(d)}{d.is_sample ? " · sample" : ""}</option>)}
        </select>
        <label className="btn" style={{ flex: "0 0 auto" }}>
          <Icon name="upload" />{busy ? "Uploading…" : "Upload file"}
          <input type="file" title="A PDF, an image or a text file" accept={UPLOAD_ACCEPT} className="sr" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </label>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the builder

function BuilderInner({ flowId }: { flowId: string }) {
  const cfg = useConfig();
  const rf = useReactFlow();
  const { zoom } = useViewport();
  const [flow, setFlow] = useState<Flow | null>(null);
  const [name, setName] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<FNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<FEdge>([]);
  const [inputs, setInputs] = useState<ValueInput[]>([]);                // the flow's value inputs
  const [docs, setDocs] = useState<Doc[]>([]);
  const [docBy, setDocBy] = useState<Record<string, string>>({});      // source block id -> document id
  const [problems, setProblems] = useState<Problem[]>([]);
  const [cacheBy, setCacheBy] = useState<Record<string, boolean>>({});
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [tab, setTab] = useState("Prompt");
  const [menu, setMenu] = useState<{ x: number; y: number; id: string; edge?: boolean } | null>(null);
  const [showProblems, setShowProblems] = useState(false);
  const [dialog, setDialog] = useState<null | { kind: "run"; only?: string } | { kind: "outputs"; id: string } | { kind: "quick" } | { kind: "api" }>(null);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState<"saved" | "saving" | "error">("saved");
  const [ready, setReady] = useState(false);
  const skip = useRef({ save: true, dirty: true });
  const titleRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setReady(false);
    skip.current = { save: true, dirty: true };
    api<Flow>(`/api/flows/${flowId}`).then((f) => {
      setFlow(f);
      setName(f.name);
      const r = toRF(f.graph);
      setNodes(r.nodes);
      setEdges(r.edges);
      setInputs(f.graph.inputs || []);
      setDirty(f.version === 0 || !!f.draft_differs);
      setTimeout(() => { setReady(true); rf.fitView({ padding: 0.12, maxZoom: 1 }); }, 60);
    }).catch((e) => toast(e.message, true));
    api<Doc[]>("/api/documents").then((d) => {
      setDocs(d);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flowId]);

  // The file for each source, used by the estimate and test runs: the last one chosen for this flow,
  // else the sample the block points at, else a file with exactly the block's name. Otherwise none:
  // a new source starts with no file, so nothing runs on a file nobody picked.
  const sourceNodes = useMemo(() => nodes.filter((n) => n.type === "source").sort((a, b) => a.position.y - b.position.y), [nodes]);
  const sourceKey = sourceNodes.map((n) => n.id).join(",");
  useEffect(() => {
    if (!docs.length || !ready) return;
    let remembered: Record<string, string> = {};
    try { remembered = JSON.parse(localStorage.getItem(`docs:${flowId}`) || "{}"); } catch { /* storage may be unavailable */ }
    const has = (id?: string) => (id && docs.some((d) => d.document_id === id) ? id : "");
    setDocBy((cur) => {
      const next: Record<string, string> = {};
      for (const n of sourceNodes) {
        next[n.id] = has(cur[n.id]) || has(remembered[n.id]) || has(n.data?.default_document)
          || docs.find((d) => d.name === n.data?.title)?.document_id || "";
      }
      return JSON.stringify(next) === JSON.stringify(cur) ? cur : next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docs, sourceKey, flowId, ready]);
  const docKey = JSON.stringify(docBy);
  useEffect(() => {
    if (!Object.keys(docBy).length) return;
    try { localStorage.setItem(`docs:${flowId}`, docKey); } catch { /* storage may be unavailable */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docKey, flowId]);
  const setDoc = useCallback((sourceId: string, documentId: string) => setDocBy((c) => ({ ...c, [sourceId]: documentId })), []);
  const docFor = useCallback((sourceId: string) => docs.find((d) => d.document_id === docBy[sourceId]) || null, [docs, docBy]);
  const multi = sourceNodes.length > 1;
  const pagesBy = useMemo(() => Object.fromEntries(sourceNodes.map((n) => [n.id, docFor(n.id)?.pages || (multi ? 3 : 150)])), [sourceNodes, docFor, multi]);
  const allChosen = sourceNodes.length > 0 && sourceNodes.every((n) => docFor(n.id));
  const addDoc = (d: Doc) => setDocs((ds) => [d, ...ds.filter((x) => x.document_id !== d.document_id)]);

  const graph = useMemo(() => toGraph(nodes, edges, inputs), [nodes, edges, inputs]);
  const graphKey = useMemo(() => JSON.stringify({ n: graph.nodes.map((n) => [n.id, n.type, n.data]), e: graph.edges, i: graph.inputs }), [graph]);
  // Inputs no prompt or rule reads yet, and renaming one wherever it is written.
  const unusedInputs = useMemo(() => {
    const used = new Set<string>();
    graph.nodes.forEach((n) => [n.data?.system, n.data?.instructions].forEach((t) => placeholdersIn(t).forEach((k) => used.add(k))));
    graph.edges.forEach((e) => { const v = e.data?.rule?.value; (Array.isArray(v) ? v : [v]).forEach((t) => placeholdersIn(t).forEach((k) => used.add(k))); });
    return new Set(inputs.filter((i) => !used.has(valueKey(i.name))).map((i) => i.name));
  }, [graph, inputs]);
  const renameInput = useCallback((from: string, to: string) => {
    if (!from.trim() || !to.trim()) return;
    setNodes((ns) => ns.map((n) => (n.type !== "step" ? n : { ...n, data: { ...n.data, system: renamePlaceholder(n.data.system, from, to), instructions: renamePlaceholder(n.data.instructions, from, to) } })));
    setEdges((es) => es.map((e) => (typeof e.data?.rule?.value !== "string" ? e : { ...e, data: { ...e.data, rule: { ...e.data.rule!, value: renamePlaceholder(e.data.rule!.value, from, to) } } })));
  }, [setNodes, setEdges]);
  const deselect = useCallback(() => {
    setNodes((ns) => ns.map((n) => ({ ...n, selected: false })));
    setEdges((es) => es.map((e) => ({ ...e, selected: false })));
  }, [setNodes, setEdges]);
  const posKey = useMemo(() => JSON.stringify(graph.nodes.map((n) => n.position)), [graph]);

  // validate and estimate when the flow's meaning changes (not on every drag)
  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => {
      api<{ problems: Problem[]; cacheable?: Record<string, boolean> }>("/api/validate", { json: { graph } })
        .then((r) => { setProblems(r.problems); setCacheBy(r.cacheable || {}); }).catch(() => {});
      // No figures until every source has a file: an estimate for a file nobody chose would mislead.
      if (allChosen) api<Estimate>("/api/estimate", { json: { graph, flow_id: flowId, pages: pagesBy, documents: docBy } }).then(setEstimate).catch(() => {});
      else setEstimate(null);
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphKey, docKey, docs.length, ready]);

  // autosave the draft
  useEffect(() => {
    if (!ready || !flow) return;
    if (skip.current.save) { skip.current.save = false; return; }
    setSaved("saving");
    const t = setTimeout(() => {
      api(`/api/flows/${flowId}`, { method: "PUT", json: { name, graph } }).then(() => setSaved("saved")).catch(() => setSaved("error"));
    }, 700);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphKey, posKey, name, ready]);
  useEffect(() => {
    if (!ready) return;
    if (skip.current.dirty) { skip.current.dirty = false; return; }
    setDirty(true);
  }, [graphKey, name, ready]);

  const selNode = nodes.find((n) => n.selected) || null;
  const selEdge = edges.find((e) => e.selected) || null;
  const focusNode = selNode || (selEdge ? nodes.find((n) => n.id === selEdge.target) || null : null);
  // The connection a block works through, and the references beside it.
  const inEdge = focusNode ? edges.find((e) => e.target === focusNode.id && !isRef(e)) || null : null;
  const upstream = inEdge ? nodes.find((n) => n.id === inEdge.source) || null : null;
  const refs: RefInfo[] = focusNode ? edges.filter((e) => e.target === focusNode.id && isRef(e)).map((e) => {
    const s = nodes.find((n) => n.id === e.source);
    return { id: e.id, title: s?.data.title || "Block", fromSource: s?.type === "source" };
  }) : [];
  useEffect(() => { if (selEdge && focusNode?.type === "step") setTab("Input"); }, [selEdge?.id]); // eslint-disable-line

  const updateNode = useCallback((id: string, patch: any) => {
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)));
  }, [setNodes]);
  const updateEdge = useCallback((id: string, patch: Partial<EdgeData>) => {
    setEdges((es) => es.map((e) => {
      if (e.id !== id) return e;
      const data: EdgeData = { ...(e.data || {}), ...patch };
      if (patch.instruction === "map") { data.window = data.window ?? 1; data.overlap = data.overlap ?? 0; }
      if (patch.instruction === "filter" && !data.rule) data.rule = { field: "", op: "equals", value: "" };
      return { ...e, data };
    }));
  }, [setEdges]);

  // Which connection a step works through. Making one the input turns the step's other connections into references.
  const setRole = useCallback((edgeId: string, role: "material" | "reference") => {
    setEdges((es) => {
      const me = es.find((e) => e.id === edgeId);
      if (!me) return es;
      const fromSource = nodes.find((n) => n.id === me.source)?.type === "source";
      return es.map((e) => {
        if (e.id === edgeId) {
          const data: EdgeData = role === "reference" ? { role: "reference" }
            : { ...(e.data || {}), role: "material", instruction: e.data?.instruction || (fromSource ? "map" : "reduce"), window: e.data?.window ?? 1, overlap: e.data?.overlap ?? 0 };
          return { ...e, data };
        }
        if (role === "material" && e.target === me.target && !isRef(e)) return { ...e, data: { role: "reference" as const } };
        return e;
      });
    });
  }, [nodes, setEdges]);

  const addBlock = useCallback((key: string, at?: { x: number; y: number }) => {
    const t = TEMPLATES[key]?.();
    if (!t) return;
    if (t.type === "source") {      // a second source needs its own name
      const taken = new Set(nodes.filter((n) => n.type === "source").map((n) => String(n.data.title)));
      let k = taken.size + 1;
      while (taken.has(`File ${k}`)) k++;
      if (taken.size) t.data.title = `File ${k}`;
    }
    // Clicked (not dropped): put it below the lowest block, under the steps, so it never covers one.
    const lowest = nodes.reduce((m, n) => Math.max(m, n.position.y), -Infinity);
    const stepXs = nodes.filter((n) => n.type === (t.type === "output" ? "output" : t.type === "source" ? "source" : "step")).map((n) => n.position.x);
    const pos = at || (nodes.length
      ? { x: stepXs.length ? Math.min(...stepXs) : 340, y: lowest + 150 }
      : { x: 60, y: 200 });
    const id = uid(t.type);
    setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), { id, type: t.type, position: pos, data: t.data, selected: true }]);
    setEdges((es) => es.map((e) => ({ ...e, selected: false })));
    if (t.type === "step") setTab("Prompt");
    if (!at) setTimeout(() => rf.fitView({ padding: 0.12, maxZoom: 1, duration: 250 }), 40);
  }, [nodes, rf, setNodes, setEdges]);

  const onConnect = useCallback((c: Connection) => {
    if (!c.source || !c.target || c.source === c.target) return;
    const src = nodes.find((n) => n.id === c.source), tgt = nodes.find((n) => n.id === c.target);
    if (!src || !tgt) return;
    if (tgt.type === "source") { toast("A source cannot receive a connection."); return; }
    const existing = edges.filter((e) => e.target === c.target);
    if (existing.some((e) => e.source === c.source)) { toast("Those two blocks are already connected."); return; }
    if (tgt.type === "output" && existing.length) { toast("An output takes one input. Remove it first."); return; }
    if (tgt.type === "output" && src.type !== "step") { toast("An output is fed by a step."); return; }
    if (src.type === "output") { toast("An output is the end of a flow."); return; }
    // A step works through one input. Anything else connected to it is a reference.
    const asRef = tgt.type === "step" && existing.some((e) => !isRef(e));
    const data: EdgeData = tgt.type === "output" ? {} : asRef ? { role: "reference" }
      : src.type === "source" ? (docFor(src.id)?.pages === 1 ? { instruction: "map", window: 1, overlap: 0 } : { instruction: "map", window: 4, overlap: 1 })
      : { instruction: "reduce" };
    if (asRef) toast(`${src.data.title} added as a reference for ${tgt.data.title}`);
    setEdges((es) => [...es.map((e) => ({ ...e, selected: false })), { id: uid("e"), source: c.source!, target: c.target!, type: "flow", data, selected: tgt.type === "step" }]);
    setNodes((ns) => ns.map((n) => ({ ...n, selected: false })));
  }, [nodes, edges, setEdges, setNodes, docFor]);

  const duplicate = (id: string) => {
    const n = nodes.find((x) => x.id === id);
    if (!n) return;
    const nid = uid(n.type || "step");
    setNodes((ns) => [...ns.map((x) => ({ ...x, selected: false })),
      { id: nid, type: n.type, position: { x: n.position.x + 30, y: n.position.y + 130 }, data: JSON.parse(JSON.stringify({ ...n.data, title: `${n.data.title} copy` })), selected: true }]);
  };
  const remove = (id: string, edge?: boolean) => {
    if (edge) setEdges((es) => es.filter((e) => e.id !== id));
    else { setNodes((ns) => ns.filter((n) => n.id !== id)); setEdges((es) => es.filter((e) => e.source !== id && e.target !== id)); }
  };
  const select = (id: string) => {
    setNodes((ns) => ns.map((n) => ({ ...n, selected: n.id === id })));
    setEdges((es) => es.map((e) => ({ ...e, selected: false })));
  };
  const focusProblem = (p: Problem) => {
    setShowProblems(false);
    const id = p.node_id || edges.find((e) => e.id === p.edge_id)?.target;
    if (!id) return;
    select(id);
    if (p.edge_id) setTab("Input"); else setTab("Prompt");
    const n = nodes.find((x) => x.id === id);
    if (n) rf.setCenter(n.position.x + 90, n.position.y + 55, { zoom: Math.max(zoom, 0.9), duration: 300 });
  };

  // keyboard
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable;
      if (e.key === "Escape") { setMenu(null); setShowProblems(false); }
      if (typing || dialog) return;
      if (e.key === "/") { e.preventDefault(); setDialog({ kind: "quick" }); }
      if (e.key === "F2" && selNode) { e.preventDefault(); titleRef.current?.focus(); titleRef.current?.select(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d" && selNode) { e.preventDefault(); duplicate(selNode.id); }
      if (e.key.toLowerCase() === "t" && selNode?.type === "step" && !e.ctrlKey && !e.metaKey) setDialog({ kind: "run", only: selNode.id });
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  const errors = problems.filter((p) => p.level === "error");
  const warnings = problems.filter((p) => p.level !== "error");
  const decorated = useMemo(() => edges.map((e) => {
    const color = INSTRUCTION_COLOR[isRef(e) ? "reference" : e.data?.instruction || "none"].line;
    return { ...e, markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 } };
  }), [edges]);
  const ctx: Ctx = useMemo(() => ({
    cfg, problems, estimate, docFor, multi, selectedEdge: selEdge?.id || null, cacheable: cacheBy,
    nodeTitle: (id: string) => nodes.find((n) => n.id === id)?.data.title || "",
  }), [cfg, problems, estimate, docFor, multi, selEdge?.id, nodes, cacheBy]);

  const saveVersion = async (publish: boolean) => {
    try {
      await api(`/api/flows/${flowId}`, { method: "PUT", json: { name, graph } });
      const f = await api<Flow>(`/api/flows/${flowId}/${publish ? "publish" : "versions"}`, { method: "POST" });
      setFlow(f);
      setDirty(false);
      toast(publish ? `Published as v${f.version}` : `Saved as v${f.version}`);
    } catch (e: any) {
      if (e instanceof ApiError && e.body?.problems) { setProblems(e.body.problems); setShowProblems(true); }
      toast(e.message, true);
    }
  };
  const validateNow = async () => {
    const r = await api<{ problems: Problem[] }>("/api/validate", { json: { graph } });
    setProblems(r.problems);
    const errs = r.problems.filter((p) => p.level === "error");
    if (errs.length) { setShowProblems(true); toast(`${errs.length} problem${errs.length > 1 ? "s" : ""} to fix`, true); }
    else if (r.problems.length) { setShowProblems(true); toast(`This flow can run. ${r.problems.length} warning${r.problems.length > 1 ? "s" : ""} to look at.`); }
    else toast("No problems found. This flow can run.");
  };

  const badge = flow ? (
    <span className={"pill" + (!dirty && flow.published_version === flow.version && flow.version ? " green" : "")}>
      {flow.version ? `v${flow.version}` : "New"} · {dirty ? "Draft" : flow.published_version === flow.version && flow.version ? "Published" : "Saved"}
      {flow.published_version && (dirty || flow.published_version !== flow.version) ? ` · v${flow.published_version} is published` : ""}
    </span>
  ) : null;

  return (
    <BuilderCtx.Provider value={ctx}>
      <div className="screen" style={{ height: "100%" }} onClick={() => menu && setMenu(null)}>
        <TopBar
          crumbs={<><Link to="/">Document Engine</Link><span>/</span><Link to="/">Flows</Link></>}
          title={<input className="title-input" aria-label="Flow name" value={name} size={Math.max(6, name.length)} onChange={(e) => setName(e.target.value)} />}
          badge={<>{badge}<span className="hint" aria-live="polite">{saved === "saving" ? "Saving…" : saved === "error" ? "Not saved" : ""}</span></>}
          middle={
            <div className="estimate" title="Estimated from each step's settings, and from real calls once a step has run.">
              <Icon name="chart" color="var(--text-2)" />
              <span>Estimate for</span>
              {multi ? (
                <span title="Choose the file for each source on its block">{sourceNodes.length} files · {fmtInt(estimate?.pages ?? 0)} pages</span>
              ) : !sourceNodes.length ? (
                <span>no source yet</span>
              ) : (
                <select aria-label="File for the estimate" value={docBy[sourceNodes[0]?.id] || ""} onChange={(e) => sourceNodes[0] && setDoc(sourceNodes[0].id, e.target.value)}>
                  {!docBy[sourceNodes[0]?.id] ? <option value="">Choose a file</option> : null}
                  {docs.map((d) => <option key={d.document_id} value={d.document_id}>{docSize(d)} · {d.name}</option>)}
                </select>
              )}
              {sourceNodes.length && !allChosen ? <span>{multi ? "choose a file for every source to see the figures" : "to see the figures"}</span> : <>
                <strong>{estimate ? `${fmtInt(estimate.calls)} calls` : "…"}</strong><span className="dot">·</span>
                <strong>{estimate ? `~${fmtK(estimate.output_tokens)} output tokens` : "…"}</strong><span className="dot">·</span>
                <strong>{estimate ? `about ${fmtCost(estimate.cost)}` : "…"}</strong>
              </>}
            </div>
          }>
          <button className="btn" onClick={validateNow}><Icon name="check" />Validate</button>
          <button className="btn" disabled={errors.length > 0 || !allChosen} title={errors.length ? "Fix the problems first" : !allChosen ? "Choose a file for every source first" : ""} onClick={() => setDialog({ kind: "run" })}><Icon name="play" />Test run</button>
          <button className="btn" onClick={() => saveVersion(false)}>Save version</button>
          <button className="btn" title="How to run this flow from code" onClick={() => setDialog({ kind: "api" })}><Icon name="code" />API</button>
          <button className="btn primary" onClick={() => saveVersion(true)}>Publish</button>
        </TopBar>

        <div className="builder">
          <Library onAdd={(k) => addBlock(k)} canSetIns={!!inEdge && focusNode?.type === "step"} activeIns={inEdge && focusNode?.type === "step" ? inEdge.data?.instruction : undefined}
            onInstruction={(i) => {
              if (!inEdge) return;
              if (i === "filter" && upstream?.type === "source") { toast("A filter reads a field from an earlier step."); return; }
              updateEdge(inEdge.id, { instruction: i, consume: undefined });
              setTab("Input");
            }} />

          <main className="canvas-wrap" aria-label="Flow canvas">
            <div className="canvas" ref={wrapRef}
              onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; }}
              onDrop={(e) => {
                const key = e.dataTransfer.getData("application/de-block");
                if (!key) return;
                e.preventDefault();
                const p = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY });
                addBlock(key, { x: p.x - 90, y: p.y - 55 });
              }}>
              <ReactFlow nodes={nodes} edges={decorated} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
                onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
                onNodeContextMenu={(e, n) => { e.preventDefault(); select(n.id); setMenu({ x: e.clientX, y: e.clientY, id: n.id }); }}
                onEdgeContextMenu={(e, ed) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY, id: ed.id, edge: true }); }}
                onNodeDoubleClick={(_, n) => { select(n.id); setTab("Prompt"); }}
                onPaneClick={() => setMenu(null)}
                deleteKeyCode={["Backspace", "Delete"]} minZoom={0.3} maxZoom={1.6} snapToGrid snapGrid={[10, 10]}
                proOptions={{ hideAttribution: true }} defaultEdgeOptions={{ type: "flow" }}>
                <Background variant={BackgroundVariant.Dots} gap={20} size={1.4} color="var(--dots)" />
                <MiniMap pannable zoomable style={{ width: 132, height: 78, border: "1px solid var(--line-2)", borderRadius: 6, background: "var(--surface-2)" }}
                  nodeColor={(n) => (n.selected ? "var(--accent)" : problems.some((p) => p.node_id === n.id && p.level === "error") ? "var(--warn)" : "var(--faint)")}
                  nodeStrokeWidth={0} maskColor="rgba(47,111,235,0.08)" maskStrokeColor="var(--accent)" maskStrokeWidth={1.5} />
              </ReactFlow>
              {ready && nodes.length === 0 ? (
                <div className="canvas-empty">
                  <strong>This flow is empty</strong>
                  <span>Drag a <b>File</b> source from the library on the left, then a step, then an output. Connect them by dragging from one block's dot to the next.</span>
                  <span>Or press <kbd>/</kbd> to add a block.</span>
                </div>
              ) : null}
              {showProblems && problems.length ? (
                <div className="problem-list" role="list">
                  {problems.map((p, i) => (
                    <button key={i} onClick={() => focusProblem(p)}>
                      <Icon name="warn" color={p.level === "error" ? "var(--warn-text)" : "var(--faint)"} /><span>{p.message}</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="canvas-foot">
              {errors.length ? (
                <button className="problems-btn" onClick={() => (errors.length === 1 ? focusProblem(errors[0]) : setShowProblems((s) => !s))}>
                  <Icon name="warn" color="var(--warn-text)" /><strong>{errors.length} problem{errors.length > 1 ? "s" : ""}</strong><span>{errors[0].message}</span>
                </button>
              ) : warnings.length ? (
                <button className="problems-btn" onClick={() => setShowProblems((s) => !s)}>
                  <Icon name="check" /><strong>This flow can run.</strong>
                  <span>{warnings.length} warning{warnings.length > 1 ? "s" : ""}: {warnings[0].message}</span>
                </button>
              ) : (
                <span className="problems-ok"><Icon name="check" />No problems. This flow can run.</span>
              )}
              <div className="zoom">
                <button aria-label="Zoom out" onClick={() => rf.zoomOut({ duration: 150 })}>−</button>
                <span>{Math.round(zoom * 100)}%</span>
                <button aria-label="Zoom in" onClick={() => rf.zoomIn({ duration: 150 })}>+</button>
                <button className="fit" onClick={() => rf.fitView({ padding: 0.12, maxZoom: 1, duration: 200 })}>Fit</button>
              </div>
            </div>
          </main>

          <aside className="props" aria-label="Properties">
            {focusNode?.type === "step" ? (
              <StepPanel node={focusNode} inEdge={inEdge} upstream={upstream} refs={refs} setRole={setRole} removeEdge={(id) => remove(id, true)} cfg={cfg} tab={tab} setTab={setTab} estimate={estimate} titleRef={titleRef} inputs={inputs} onManageInputs={deselect}
                update={(p) => updateNode(focusNode.id, p)} updateEdge={(p) => inEdge && updateEdge(inEdge.id, p)}
                onTest={() => setDialog({ kind: "run", only: focusNode.id })}
                onDone={() => { setNodes((ns) => ns.map((n) => ({ ...n, selected: false }))); setEdges((es) => es.map((e) => ({ ...e, selected: false }))); }} />
            ) : focusNode?.type === "source" ? (
              <>
                <div><span className="caps">Source</span>
                  <input ref={titleRef} className="title-input" style={{ fontSize: 20, maxWidth: "100%", display: "block", marginTop: 4 }} aria-label="Input name"
                    value={focusNode.data.title} onChange={(e) => updateNode(focusNode.id, { title: e.target.value })} />
                  <span className="sub">{multi ? "The name of this input. Page references use it." : "Every page of the file becomes one item. An image is one page."}</span></div>
                <DocPicker label="File" docs={docs} value={docBy[focusNode.id] || ""} onChange={(id) => setDoc(focusNode.id, id)} onUploaded={(d) => { addDoc(d); setDoc(focusNode.id, d.document_id); }} />
                <p className="hint">Choose a file from the list, or use <strong>Upload file</strong> to add your own: a PDF, an image (PNG, JPEG and others) or a text file.</p>
                <p className="hint">The file chosen here is used for the estimate and for test runs. A published flow can be run on any file.</p>
                <p className="hint"><Link to="/files">Manage files</Link> to see every uploaded file or remove one.</p>
                {multi ? <p className="hint">Every page becomes one item for the step this source feeds. Connected to a step that already has an input, the whole file becomes a reference for that step.</p> : null}
              </>
            ) : focusNode?.type === "output" ? (
              <>
                <div><span className="caps">Output</span>
                  <input ref={titleRef} className="title-input" style={{ fontSize: 20, maxWidth: "100%", display: "block", marginTop: 4 }} aria-label="Output name"
                    value={focusNode.data.title} onChange={(e) => updateNode(focusNode.id, { title: e.target.value })} />
                  <span className="sub">{upstream ? `Collects what ${upstream.data.title} produces` : "Not connected yet"}</span></div>
                <div className="field"><span className="label">Show as</span>
                  <div className="seg">
                    <button aria-pressed={focusNode.data.format !== "table"} onClick={() => updateNode(focusNode.id, { format: "text" })}>Text</button>
                    <button aria-pressed={focusNode.data.format === "table"} onClick={() => updateNode(focusNode.id, { format: "table" })}>Table</button>
                  </div>
                  <p className="hint">A table needs the step before it to have a schema output.</p>
                </div>
              </>
            ) : (
              <>
                <div><span className="caps">Flow</span><h2 style={{ marginTop: 4 }}>{name || "Untitled flow"}</h2>
                  <span className="sub">Select a block or a connection to edit it.</span></div>
                <InputsEditor inputs={inputs} onChange={setInputs} onRename={renameInput} unused={unusedInputs} />
                {estimate ? (
                  <div className="block">
                    <div className="bh"><strong>Estimate by step</strong><span>{multi ? `${sourceNodes.length} files, ` : ""}{estimate.pages} pages</span></div>
                    <table className="table" style={{ fontSize: 12 }}>
                      <tbody>
                        {nodes.filter((n) => n.type === "step" && estimate.per_node[n.id]).map((n) => {
                          const p = estimate.per_node[n.id];
                          return (
                            <tr key={n.id} className="click" onClick={() => select(n.id)}>
                              <td>{n.data.title}</td><td className="num">{fmtInt(p.calls)} call{p.calls === 1 ? "" : "s"}</td><td className="num">{fmtCost(p.cost)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                {estimate?.assumed_filter_ratio ? <p className="hint">A filter's share is assumed to be 25% until the flow has run once.</p> : null}
                <p className="hint">Right click a block for more actions. <kbd>Del</kbd> removes the selection, <kbd>F2</kbd> renames, <kbd>Ctrl D</kbd> duplicates.</p>
              </>
            )}
          </aside>
        </div>

        {menu ? (() => {
          const n = nodes.find((x) => x.id === menu.id);
          const close = (fn: () => void) => () => { setMenu(null); fn(); };
          return (
            <div className="ctx" style={{ left: Math.min(menu.x, window.innerWidth - 236), top: Math.min(menu.y, window.innerHeight - 300) }} onClick={(e) => e.stopPropagation()}>
              <span className="caps">{menu.edge ? "Connection" : n?.data.title}</span>
              {menu.edge ? (() => {
                const ed = edges.find((e) => e.id === menu.id);
                const toStep = ed && nodes.find((x) => x.id === ed.target)?.type === "step";
                return (
                  <>
                    {toStep && ed && isRef(ed) ? <button className="first" onClick={close(() => setRole(menu.id, "material"))}><span>Use as the step's input</span></button> : null}
                    {toStep && ed && !isRef(ed) ? <button className="first" onClick={close(() => setRole(menu.id, "reference"))}><span>Use as a reference</span></button> : null}
                    <button className="del" onClick={close(() => remove(menu.id, true))}><span>Delete connection</span><span className="k">Del</span></button>
                  </>
                );
              })() : (
                <>
                  <button className="first" onClick={close(() => { select(menu.id); setTab("Prompt"); })}><span>Configure</span><span className="k">Double click</span></button>
                  <button onClick={close(() => { select(menu.id); setTimeout(() => { titleRef.current?.focus(); titleRef.current?.select(); }, 30); })}><span>Rename</span><span className="k">F2</span></button>
                  <button onClick={close(() => duplicate(menu.id))}><span>Duplicate</span><span className="k">Ctrl D</span></button>
                  {n?.type === "step" ? <button onClick={close(() => setDialog({ kind: "run", only: menu.id }))}><span>Test this step</span><span className="k">T</span></button> : null}
                  {n?.type === "step" ? <button onClick={close(() => setDialog({ kind: "outputs", id: menu.id }))}><span>View last outputs</span></button> : null}
                  <hr />
                  <button className="del" onClick={close(() => remove(menu.id))}><span>Delete</span><span className="k">Del</span></button>
                </>
              )}
            </div>
          );
        })() : null}

        {dialog?.kind === "quick" ? (
          <Modal title="Add a block" onClose={() => setDialog(null)}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[["blank", "plus", "Blank step"], ["classify", "bookmark", "Classify page type"], ["summarize", "bookmark", "Summarize window"], ["output", "flag", "Output"], ["source", "doc", "File: PDF, image or text"]].map(([k, i, l]) => (
                <button key={k} className="lib-item" onClick={() => { addBlock(k); setDialog(null); }}><Icon name={i} size={16} />{l}</button>
              ))}
            </div>
          </Modal>
        ) : null}
        {dialog?.kind === "run" && flow ? (
          <RunDialog flow={flow} graph={graph} name={name} docs={docs} docBy={docBy} setDoc={setDoc} addDoc={addDoc} only={dialog.only}
            onlyTitle={dialog.only ? nodes.find((n) => n.id === dialog.only)?.data.title : undefined} cfg={cfg} onClose={() => setDialog(null)} />
        ) : null}
        {dialog?.kind === "api" && flow ? <ApiPanel flow={flow} dirty={dirty} onClose={() => setDialog(null)} onUnpublished={setFlow} /> : null}
        {dialog?.kind === "outputs" ? <LastOutputs flowId={flowId} nodeId={dialog.id} title={nodes.find((n) => n.id === dialog.id)?.data.title} onClose={() => setDialog(null)} /> : null}
      </div>
    </BuilderCtx.Provider>
  );
}

function RunDialog({ flow, graph, name, docs, docBy, setDoc, addDoc, only, onlyTitle, cfg, onClose }: {
  flow: Flow; graph: Graph; name: string; docs: Doc[]; docBy: Record<string, string>; setDoc: (sourceId: string, documentId: string) => void;
  addDoc: (d: Doc) => void; only?: string; onlyTitle?: string; cfg: AppConfig | null; onClose: () => void;
}) {
  const [priority, setPriority] = useState("interactive");
  const [est, setEst] = useState<Estimate | null>(null);
  const [busy, setBusy] = useState(false);
  const [values, setValues] = useState<Values>(() => loadValues(flow.flow_id));
  // The sources this run reads: all of them, or the ones the tested step depends on.
  const { sources, needed } = useMemo(() => {
    let keep: Set<string> | null = null;
    if (only) {
      keep = new Set<string>();
      const todo = [only];
      while (todo.length) {
        const id = todo.pop()!;
        if (keep.has(id)) continue;
        keep.add(id);
        graph.edges.filter((e) => e.target === id).forEach((e) => todo.push(e.source));
      }
    }
    return { sources: graph.nodes.filter((n) => n.type === "source" && (!keep || keep.has(n.id))).sort((a, b) => a.position.y - b.position.y),
             needed: inputsFor(graph, keep) };
  }, [graph, only]);
  const missing = missingValues(needed, values);
  const chosen = sources.map((n) => docs.find((d) => d.document_id === docBy[n.id]));
  const ready = sources.length > 0 && chosen.every(Boolean);
  const documents = Object.fromEntries(sources.map((n) => [n.id, docBy[n.id]]));
  const docKey = JSON.stringify(documents);
  useEffect(() => {
    if (!ready) { setEst(null); return; }
    const pages = Object.fromEntries(sources.map((n, i) => [n.id, chosen[i]!.pages]));
    api<Estimate>("/api/estimate", { json: { graph, flow_id: flow.flow_id, pages, documents, only_node: only } }).then(setEst).catch(() => setEst(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docKey, only, ready]);
  const start = async () => {
    setBusy(true);
    try {
      await api(`/api/flows/${flow.flow_id}`, { method: "PUT", json: { name, graph } });
      saveValues(flow.flow_id, values);
      const r = await api<{ job_ids: string[] }>("/api/jobs", {
        json: { flow_id: flow.flow_id, graph, documents, values: valuesToSend(needed, values), priority, count: 1, only_node: only, label: only ? `Step test: ${onlyTitle}` : "Test run" },
      });
      navigate(`/runs/${r.job_ids[0]}`);
    } catch (e: any) { toast(e.message, true); setBusy(false); }
  };
  return (
    <Modal title={only ? `Test "${onlyTitle}"` : "Test run"} onClose={onClose}>
      <p className="hint">{only ? "Runs the flow up to and including this step, then stops." : sources.length > 1 ? "Runs the whole flow through the scheduler, with live progress. Choose one file for each source." : "Runs the whole flow on one file through the scheduler, with live progress."}</p>
      {sources.map((n) => (
        <DocPicker key={n.id} label={sources.length > 1 ? n.data.title : "File"} docs={docs} value={docBy[n.id] || ""} onChange={(id) => setDoc(n.id, id)}
          onUploaded={(d) => { addDoc(d); setDoc(n.id, d.document_id); }} />
      ))}
      <ValuesForm inputs={needed} values={values} onChange={setValues} />
      <div className="field"><span className="label">Priority</span>
        <div className="seg">
          <button aria-pressed={priority === "interactive"} onClick={() => setPriority("interactive")}>Interactive</button>
          <button aria-pressed={priority === "bulk"} onClick={() => setPriority("bulk")}>Bulk</button>
        </div>
        <p className="hint">Interactive jobs go ahead of bulk jobs when the quota is busy.</p>
      </div>
      <div className="estimate" style={{ alignSelf: "flex-start" }}>
        <Icon name="chart" color="var(--text-2)" /><span>This run:</span>
        <strong>{est ? `${fmtInt(est.calls)} calls` : "…"}</strong><span className="dot">·</span>
        <strong>{est ? `~${fmtK(est.output_tokens)} output tokens` : "…"}</strong><span className="dot">·</span>
        <strong>{est ? `about ${fmtCost(est.cost)}` : "…"}</strong>
      </div>
      <p className="hint">Calls go to {cfg?.gateway || "the gateway"} and cost real money.</p>
      <div className="foot">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={busy || !ready || missing.length > 0} title={missing.length ? `Give a value for ${missing.join(", ")}` : ""} onClick={start}><Icon name="play" color="#fff" />{busy ? "Starting…" : "Start"}</button>
      </div>
    </Modal>
  );
}

function LastOutputs({ flowId, nodeId, title, onClose }: { flowId: string; nodeId: string; title?: string; onClose: () => void }) {
  const [data, setData] = useState<{ job_id: string | null; tasks: any[] } | null>(null);
  useEffect(() => { api(`/api/flows/${flowId}/last-outputs?node_id=${encodeURIComponent(nodeId)}`).then(setData).catch(() => setData({ job_id: null, tasks: [] })); }, [flowId, nodeId]);
  return (
    <Modal title={`Last outputs of ${title || "this step"}`} onClose={onClose} wide>
      {!data ? <p className="empty">Loading…</p> : !data.tasks.length ? <p className="empty">This step has not run yet. Start a test run to see its outputs here.</p> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p className="hint">Showing {data.tasks.length} outputs from the latest run. <Link to={`/runs/${data.job_id}`}>Open that run</Link></p>
          {data.tasks.map((t) => (
            <div key={t.task_id}>
              <div className="hint" style={{ marginBottom: 4 }}>Pages {t.pages.join(", ")} · {t.output_tokens} tokens{t.stop_reason === "max_tokens" ? " · cut off at max output" : ""}</div>
              <pre className="raw">{t.output_data ? JSON.stringify(t.output_data, null, 1) : t.output_text}</pre>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

export default function Builder({ flowId }: { flowId: string }) {
  return <ReactFlowProvider><BuilderInner flowId={flowId} /></ReactFlowProvider>;
}
