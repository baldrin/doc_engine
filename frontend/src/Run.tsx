import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  Background, BackgroundVariant, BaseEdge, Edge, EdgeLabelRenderer, EdgeProps, getBezierPath, Handle, Node, NodeProps,
  Position, ReactFlow, ReactFlowProvider,
} from "@xyflow/react";
import {
  api, AppConfig, EngineEvent, fmtClock, fmtInt, fmtK, INSTRUCTION_COLOR, Job, modelLabel, navigate, pageRanges, Quota,
  QuotaModel, useConfig,
} from "./lib";
import { Icon, Link, toast, TopBar } from "./ui";

// ---------------------------------------------------------------- state built from events

interface NState {
  state: "idle" | "run" | "done" | "failed";
  total: number;
  done: number;
  inflight: number;
  kept: number | null;
  itemsIn: number | null;
  tokens: number;
  instruction: string | null;
  window?: number;
  overlap?: number;
}
interface FeedItem { id: string; t: number; text: string; color: string }
interface Rate { t: number; model: string; out: number; inp: number }
interface RState {
  nodes: Record<string, NState>;
  feed: FeedItem[];
  rates: Rate[];
  calls: number;
  planned: number;
  rejections: number;
  inflight: number;
  job: string;
  error: string | null;
  t0: number;
  last: number;
  end: number | null;
  lastId: number;
}
// Theme colours (styles.css). Use mix() where a hex alpha suffix would have been used.
const C = { blue: "var(--blue)", teal: "var(--teal)", orange: "var(--orange)", green: "var(--green)", purple: "var(--purple)", red: "var(--red)" };
const mix = (color: string, pct: number) => `color-mix(in srgb, ${color} ${pct}%, transparent)`;

function initial(job: Job): RState {
  const nodes: Record<string, NState> = {};
  for (const n of job.graph?.nodes || []) {
    nodes[n.id] = { state: "idle", total: 0, done: 0, inflight: 0, kept: null, itemsIn: null, tokens: 0, instruction: null };
  }
  const t0 = new Date(job.submitted_at).getTime() / 1000;
  return { nodes, feed: [], rates: [], calls: 0, planned: 0, rejections: 0, inflight: 0, job: "queued", error: null, t0, last: t0, end: null, lastId: 0 };
}

function apply(s: RState, ev: EngineEvent, titles: Record<string, string>): RState {
  const t = new Date(ev.ts).getTime() / 1000;
  const d = ev.data || {};
  const nid = ev.node_id || "";
  const title = titles[nid] || "Step";
  const nodes = { ...s.nodes };
  const n: NState | undefined = nodes[nid] ? { ...nodes[nid] } : undefined;
  const out: RState = { ...s, nodes, last: Math.max(s.last, t), lastId: Math.max(s.lastId, ev.event_id) };
  const say = (text: string, color: string) => { out.feed = [{ id: `${ev.event_id}`, t, text, color }, ...s.feed].slice(0, 40); };
  switch (ev.kind) {
    case "job_submitted":
      say(`Job submitted · ${d.pages} pages · ${d.priority}`, C.blue);
      break;
    case "job_started":
      out.job = "running";
      break;
    case "step_planned":
      if (n) {
        n.total = d.tasks; n.instruction = d.instruction; n.window = d.window; n.overlap = d.overlap;
        if (d.kept != null) n.kept = d.kept;
        out.planned = s.planned + d.tasks + (d.warmup ? 1 : 0);
        if (d.tasks > 0) say(`${title} · ${fmtInt(d.tasks)} ${d.tasks === 1 ? "task" : "tasks"} scheduled`, C.blue);
      }
      break;
    case "filter_applied":
      if (n) { n.kept = d.kept; say(`Filter · ${d.kept} kept (${d.rule})`, C.orange); }
      break;
    case "task_admitted":
      out.inflight = s.inflight + 1;
      if (out.job === "queued") out.job = "running";
      if (n) {
        n.inflight += 1;
        if (n.state === "idle") n.state = "run";
        if (d.kind === "warmup") say(`${title} · warming the prompt cache`, C.purple);
      }
      break;
    case "task_progress":
      if (n) n.tokens = d.tokens;
      break;
    case "task_done":
      out.inflight = Math.max(0, s.inflight - 1);
      out.calls = s.calls + 1;
      out.rates = [...s.rates, { t, model: ev.model || "", out: d.output_tokens || 0, inp: (d.input_tokens || 0) + (d.cache_write || 0) }];
      if (n) {
        n.inflight = Math.max(0, n.inflight - 1);
        if (d.kind === "warmup") say(`${title} · cache is warm`, C.purple);
        else {
          n.done += 1;
          n.tokens = d.output_tokens || n.tokens;
          const pg = d.pages?.length ? (d.pages.length === 1 ? `page ${d.pages[0]}` : `pages ${pageRanges(d.pages)}`) : "";
          const extra = d.summary ? ` · ${d.summary}` : d.truncated ? " · cut off at max output" : pg && n.total > 1 ? " done" : "";
          say(`${title}${pg && n.total > 1 ? ` · ${pg}` : ""}${extra || (n.total === 1 ? ` · ${fmtInt(d.output_tokens)} tokens` : "")}`, d.truncated ? C.orange : INS(n.instruction));
        }
      }
      break;
    case "task_rejected":
      out.inflight = Math.max(0, s.inflight - 1);
      out.rejections = s.rejections + 1;
      if (n) n.inflight = Math.max(0, n.inflight - 1);
      say(`Gateway rejected a call (${d.limit_type || "limit"}) · ${modelName(ev.model)} paused ${d.hold_s ?? 1} s`, C.red);
      break;
    case "task_retry":
      out.inflight = Math.max(0, s.inflight - 1);
      if (n) n.inflight = Math.max(0, n.inflight - 1);
      say(`${title} · retrying${d.delay_s ? ` in ${d.delay_s} s` : ""} (${d.error || d.outcome})`, C.orange);
      break;
    case "task_failed":
      out.inflight = Math.max(0, s.inflight - 1);
      if (n) { n.inflight = Math.max(0, n.inflight - 1); if (d.kind !== "warmup") n.state = "failed"; }
      say(`${title} · ${d.kind === "warmup" ? "warm-up failed, continuing without the cache" : d.error || "failed"}`, C.red);
      break;
    case "task_recovered":
      out.inflight = Math.max(0, s.inflight - 1);
      if (n) n.inflight = Math.max(0, n.inflight - 1);
      say(`${title} · a lost call was returned to the queue`, C.orange);
      break;
    case "step_done":
      if (n) {
        n.state = "done";
        if (d.source) { n.total = d.items; n.done = d.items; say(`${title} loaded · ${d.items} page${d.items === 1 ? "" : "s"}`, C.blue); }
        else if (d.output) say(`${title} · ready`, C.green);
        else if (d.items > 0) say(`${title} · all ${fmtInt(d.tasks ?? d.items)} done`, C.green);
        else say(`${title} · nothing to do`, C.green);
        if (d.items != null) n.itemsIn = n.itemsIn ?? d.items;
      }
      break;
    case "job_done":
      out.job = "done"; out.end = t;
      say(`Run complete · ${d.rejections ?? out.rejections} rejections`, C.green);
      break;
    case "job_failed":
      out.job = "failed"; out.end = t; out.error = d.error;
      say(`Run failed · ${d.error}`, C.red);
      break;
    case "job_cancelled":
      out.job = "cancelled"; out.end = t; out.error = "Cancelled";
      say("Run cancelled", C.orange);
      break;
  }
  if (n) nodes[nid] = n;
  if (ev.kind === "job_failed" || ev.kind === "job_cancelled") {
    // Calls still in flight when a run ends are discarded and send no event of their own.
    out.inflight = 0;
    for (const id of Object.keys(nodes)) {
      const x = nodes[id];
      if (x.inflight || x.state === "run") nodes[id] = { ...x, inflight: 0, state: x.state === "run" ? "idle" : x.state };
    }
  }
  return out;
}
const INS = (i: string | null) => (i === "reduce" ? C.teal : i === "filter" ? C.orange : C.blue);
const modelName = (m: string | null) => (m ? m[0].toUpperCase() + m.slice(1) : "model");

// ---------------------------------------------------------------- canvas

interface RunCtxT { st: RState; cfg: AppConfig | null; docName: string; pages: number; docs: NonNullable<Job["documents"]>; multi: boolean }
const RunCtx = createContext<RunCtxT | null>(null);

function RunNode({ id, type, data }: NodeProps<Node<any>>) {
  const ctx = useContext(RunCtx)!;
  const n = ctx.st.nodes[id] || { state: "idle", total: 0, done: 0, inflight: 0, tokens: 0, instruction: null };
  const inEdgeIns = n.instruction;
  const color = type === "source" ? C.blue : type === "output" ? C.green : INS(inEdgeIns);
  const single = type === "step" && n.total === 1;
  const pct = n.state === "done" ? 100 : type !== "step" ? 0
    : single ? Math.min(95, (n.tokens / Math.max(1, data.expected_output || data.max_tokens * 0.6)) * 100)
    : n.total ? (n.done / n.total) * 100 : 0;
  const status = n.state === "idle" ? "Waiting"
    : n.state === "failed" ? "Failed"
    : type === "source" ? "Ready"
    : type === "output" ? (n.state === "done" ? "Ready" : "Saving")
    : n.state === "done" ? (n.total === 0 ? "Skipped" : `${fmtInt(n.done)} done`)
    : single ? (n.tokens ? `${fmtInt(n.tokens)} tok` : "Working") : `${fmtInt(n.done)} / ${fmtInt(n.total)}`;
  const sColor = n.state === "idle" ? "var(--faint)" : n.state === "done" ? C.green : n.state === "failed" ? C.red : color;
  return (
    <div className={`rnode t-${type} ${n.state}`} style={{ ["--c" as any]: color, ["--g" as any]: mix(color, 40) }}>
      {type !== "source" ? <Handle type="target" position={Position.Left} className="rport" isConnectable={false} /> : null}
      <div className="top">
        <span className="lab">{type === "source" ? "SOURCE" : type === "output" ? "OUTPUT" : "STEP"}</span>
        {n.state === "run" ? (
          <svg className="spin" aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round"><path d="M12 3a9 9 0 1 1-9 9" /></svg>
        ) : n.state === "done" ? (
          <svg className="pop" role="img" aria-label="Done" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={C.green} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.5 2.5L16 9.5" /></svg>
        ) : n.state === "failed" ? <Icon name="warn" size={15} color={C.red} /> : null}
      </div>
      <span className="name" title={type === "source" ? ctx.docs[id]?.name : undefined}>{type === "source" && !ctx.multi ? ctx.docName : data.title}</span>
      <div className="row">
        <span>{type === "source" ? `${ctx.docs[id]?.pages ?? ctx.pages} page${(ctx.docs[id]?.pages ?? ctx.pages) === 1 ? "" : "s"}` : type === "step" ? modelLabel(ctx.cfg, data.model) : ""}</span>
        <span style={{ color: sColor }}>{status}</span>
      </div>
      <div className="bar"><div className={n.state === "run" ? "shimmer" : ""} style={{ width: `${pct}%`, backgroundColor: n.state === "done" ? "#2F8F63" : n.state === "failed" ? C.red : color }} /></div>
      {type !== "output" ? <Handle type="source" position={Position.Right} className="rport" isConnectable={false} /> : null}
    </div>
  );
}
const nodeTypes = { source: RunNode, step: RunNode, output: RunNode };

function RunEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, target, source }: EdgeProps<Edge<any>>) {
  const ctx = useContext(RunCtx)!;
  const [path, lx, ly] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const tn = ctx.st.nodes[target];
  const sn = ctx.st.nodes[source];
  const ref = data?.role === "reference";      // sent whole with every call of the target step
  const ins: string | undefined = ref ? undefined : data?.instruction;
  const color = ref ? "var(--muted)" : ins ? INS(ins) : C.green;
  const bright = ref ? "var(--ins-ref)" : ins === "reduce" ? "var(--ins-reduce)" : ins === "filter" ? "var(--ins-filter)" : "var(--ins-map)";
  const st = !tn ? "idle" : tn.state === "run" ? "run" : tn.state === "done" ? "done" : "idle";
  const active = st === "run";
  let title = "", line = "";
  if (ref) {
    title = "Reference";
    line = sn?.state !== "done" ? "waiting for it" : st === "idle" ? "ready" : st === "run" ? "on every call" : "used";
  } else if (ins === "map") {
    title = `Map ${data.window ?? 1} / ${data.overlap ?? 0}`;
    line = tn?.total ? `${fmtInt(tn.done)} / ${fmtInt(tn.total)} ${(data.window ?? 1) > 1 ? "windows" : "pages"}` : "waiting";
  } else if (ins === "reduce") {
    title = "Reduce";
    const k = sn?.total ?? 0;
    line = st === "idle" ? `${fmtInt(k) || "many"} → 1` : st === "run" ? `merging ${fmtInt(k)}` : `${fmtInt(k)} → 1 done`;
  } else if (ins === "filter") {
    title = "Filter";
    line = tn?.kept != null ? `${fmtInt(tn.kept)} of ${fmtInt(sn?.total ?? 0)} kept` : "waiting";
  }
  return (
    <>
      <BaseEdge id={id} path={path} style={{ stroke: st === "idle" ? "var(--line-2)" : color, strokeWidth: ref ? 1.75 : 2, strokeDasharray: ref ? "2 6" : undefined, opacity: st === "done" ? 0.7 : 1, filter: active && !ref ? `drop-shadow(0 0 4px ${color})` : "none" }} />
      {active && !ref ? (
        <g>
          <path className="march" d={path} fill="none" stroke="#FFFFFF" strokeOpacity={0.55} strokeWidth={2} />
          {[0, 1, 2, 3].map((i) => (
            <circle key={i} className="flowdot" r={4} fill={color} style={{ filter: `drop-shadow(0 0 5px ${color})` }}>
              <animateMotion dur="1.5s" repeatCount="indefinite" path={path} begin={`${-i * 0.375}s`} />
            </circle>
          ))}
        </g>
      ) : null}
      {ins || ref ? (
        <EdgeLabelRenderer>
          <div className="rchip" style={{
            transform: `translate(-50%, -50%) translate(${lx}px, ${ly}px)`,
            borderColor: st === "run" ? color : st === "done" ? mix(color, 60) : "var(--line-2)",
            boxShadow: st === "run" ? `0 0 14px ${mix(color, 33)}` : "none",
          }}>
            <span className="t" style={{ color: bright }}>{title}</span>
            <span className="s">{line}</span>
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
const edgeTypes = { run: RunEdge };

// ---------------------------------------------------------------- gauges

export function Gauge({ name, value, pct, from, to, mark }: { name: string; value: string; pct: number; from: string; to: string; mark?: number }) {
  return (
    <div className="gauge">
      <div className="gh"><span>{name}</span><span>{value}</span></div>
      <div className="track">
        <div className="fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: `linear-gradient(90deg, ${from}, ${to})`, boxShadow: `0 0 10px ${to}` }} />
        {mark != null ? <div className="mark" style={{ left: `${mark}%` }} /> : null}
      </div>
    </div>
  );
}

export function ModelGauges({ q, cfg, margin }: { q: QuotaModel; cfg: AppConfig | null; margin: number }) {
  const budget = q.out_level + q.open_output;
  return (
    <>
      <div className="model-head">
        <span>{modelLabel(cfg, q.model)}</span>
        <span>{q.hold_s > 0 ? "paused after a rejection" : `${q.open_calls} in flight · ${q.ready} ready`}</span>
      </div>
      <Gauge name="Output tokens per minute" value={`${fmtK(q.out_60)} / ${fmtK(q.otpm)}`} pct={(q.out_60 / q.otpm) * 100} from="#2F6FEB" to="#7FB0FF" mark={(1 - margin) * 100} />
      <Gauge name="Burst budget in use" value={`${fmtK(budget)} / ${fmtK(q.out_capacity)}`} pct={(budget / q.out_capacity) * 100} from="#6B3FC9" to="#A07CFF" />
      <Gauge name="Input tokens per minute" value={`${fmtK(q.in_60)} / ${fmtK(q.itpm)}`} pct={(q.in_60 / q.itpm) * 100} from="#16907F" to="#5ED8C7" mark={(1 - margin) * 100} />
    </>
  );
}

// ---------------------------------------------------------------- the screen

function RunInner({ jobId }: { jobId: string }) {
  const cfg = useConfig();
  const [job, setJob] = useState<Job | null>(null);
  const [st, setSt] = useState<RState | null>(null);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [replay, setReplay] = useState<null | { clock: number; playing: boolean; speed: number }>(null);
  const [now, setNow] = useState(Date.now() / 1000);
  const titles = useRef<Record<string, string>>({});
  const allEvents = useRef<EngineEvent[]>([]);
  const lastSched = useRef(0);

  // load, then follow live
  useEffect(() => {
    let es: EventSource | null = null;
    let closed = false;
    setJob(null); setSt(null); setReplay(null);
    api<Job>(`/api/jobs/${jobId}`).then((j) => {
      if (closed) return;
      titles.current = Object.fromEntries((j.graph?.nodes || []).map((n) => [n.id, n.type === "source" && Object.keys(j.documents || {}).length < 2 ? j.document_name : n.data?.title || n.id]));
      allEvents.current = j.events || [];
      let s = initial(j);
      for (const ev of allEvents.current) s = apply(s, ev, titles.current);
      setJob(j);
      setSt(s);
      es = new EventSource(`/api/stream?job_id=${encodeURIComponent(jobId)}&after=${s.lastId}`);
      es.addEventListener("event", (m) => {
        const ev: EngineEvent = JSON.parse((m as MessageEvent).data);
        if (allEvents.current.some((x) => x.event_id === ev.event_id)) return;
        allEvents.current.push(ev);
        setSt((cur) => (cur ? apply(cur, ev, titles.current) : cur));
      });
      es.addEventListener("quota", (m) => setQuota(JSON.parse((m as MessageEvent).data)));
    }).catch((e) => toast(e.message, true));
    return () => { closed = true; es?.close(); };
  }, [jobId]);

  // the final cost is known only once the job has ended
  useEffect(() => {
    if (st?.job === "done" || st?.job === "failed" || st?.job === "cancelled") {
      api<Job>(`/api/jobs/${jobId}?events=false`).then((j) => setJob((cur) => (cur ? { ...cur, cost: j.cost, state: j.state } : cur))).catch(() => {});
    }
  }, [st?.job, jobId]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 250);
    return () => clearInterval(t);
  }, []);

  // replay clock
  useEffect(() => {
    if (!replay?.playing) return;
    const t = setInterval(() => setReplay((r) => (r ? { ...r, clock: r.clock + 0.05 * r.speed } : r)), 50);
    return () => clearInterval(t);
  }, [replay?.playing]);

  const shown: RState | null = useMemo(() => {
    if (!job || !st) return null;
    if (!replay) return st;
    let s = initial(job);
    const limit = s.t0 + replay.clock;
    for (const ev of allEvents.current) {
      if (new Date(ev.ts).getTime() / 1000 > limit) break;
      s = apply(s, ev, titles.current);
    }
    return s;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job, st, replay?.clock, !!replay]);

  useEffect(() => {
    if (replay?.playing && st?.end && replay.clock > st.end - st.t0 + 0.8) setReplay({ ...replay, playing: false });
  }, [replay, st]);

  // a line in the feed when the scheduler is holding work back
  useEffect(() => {
    if (!quota || !st || replay || st.job !== "running") return;
    const mine = new Set((job?.graph?.nodes || []).map((n) => n.data?.model).filter(Boolean));
    for (const q of quota.models) {
      if (!mine.has(q.model) || q.ready < 1) continue;
      const pct = ((q.out_level + q.open_output) / q.out_capacity) * 100;
      if (pct >= 80 && Date.now() - lastSched.current > 6000) {
        lastSched.current = Date.now();
        const text = q.hold_s > 0 ? `Scheduler · ${modelName(q.model)} paused after a rejection, ${q.ready} tasks waiting`
          : `Scheduler · ${modelName(q.model)} output budget at ${Math.round(pct)}%, holding ${fmtInt(q.ready)} tasks`;
        setSt((cur) => (cur ? { ...cur, feed: [{ id: `s${Date.now()}`, t: Date.now() / 1000, text, color: C.purple }, ...cur.feed].slice(0, 40) } : cur));
        break;
      }
    }
  }, [quota]); // eslint-disable-line

  const rfNodes = useMemo(() => (job?.graph?.nodes || []).map((n) => ({ id: n.id, type: n.type, position: n.position, data: n.data || {}, draggable: false, selectable: false })), [job]);
  const rfEdges = useMemo(() => (job?.graph?.edges || []).map((e) => ({ id: e.id, source: e.source, target: e.target, type: "run", data: e.data || {} })), [job]);

  if (!job || !shown || !st) {
    return <div className="screen"><TopBar crumbs={<span>Document Engine</span>} title={<h1>Loading run…</h1>} /></div>;
  }

  const finished = st.job === "done" || st.job === "failed" || st.job === "cancelled";
  const view = replay ? (shown.end && replay.clock >= shown.end - shown.t0 ? shown.job : shown.job === "queued" ? "queued" : "running") : st.job;
  const clock = replay ? Math.min(replay.clock, (st.end ?? st.last) - st.t0) : (st.end ?? now) - st.t0;
  const complete = view === "done";
  const bad = view === "failed" || view === "cancelled";
  const statusCls = replay && !replay.playing && !complete && !bad ? "paused" : view;
  const statusText = replay && !replay.playing && !complete && !bad ? "Paused" : view === "running" ? "Running" : view === "queued" ? "Queued" : view === "done" ? "Complete" : view === "failed" ? "Failed" : "Cancelled";
  const planned = Math.max(shown.planned, shown.calls);
  const pct = complete ? 100 : planned ? (shown.calls / planned) * 100 : 0;
  const usedModels = [...new Set((job.graph?.nodes || []).filter((n) => n.type === "step").map((n) => n.data.model as string))];
  const margin = cfg?.safety_margin ?? 0.05;
  const tNow = shown.t0 + clock;
  const liveModels: QuotaModel[] = replay || finished || !quota
    ? usedModels.map((m) => {
      const mc = cfg?.models.find((x) => x.key === m);
      const win = shown.rates.filter((r) => r.model === m && r.t > tNow - 60 && r.t <= tNow);
      return {
        model: m, otpm: mc?.otpm || 100000, itpm: mc?.itpm || 1000000, out_capacity: mc?.out_capacity || 42750, out_level: 0, hold_s: 0,
        rejections: 0, open_output: 0, open_calls: 0, out_60: win.reduce((a, r) => a + r.out, 0), in_60: win.reduce((a, r) => a + r.inp, 0),
        rej_60: 0, ready: 0, ready_interactive: 0, waiting: 0,
      };
    })
    : quota.models.filter((q) => usedModels.includes(q.model));
  const lane = !replay && quota ? quota.models.reduce((a, q) => a + q.ready_interactive, 0) : 0;
  const outputs = (job.graph?.nodes || []).filter((n) => n.type === "output").length;
  const multi = Object.keys(job.documents || {}).length > 1;
  const ctx: RunCtxT = { st: shown, cfg, docName: job.document_name, pages: job.pages, docs: job.documents || {}, multi };

  const cancel = async () => {
    if (!window.confirm("Cancel this run? Calls already sent will finish and be paid for; their replies are not used.")) return;
    try { await api(`/api/jobs/${jobId}/cancel`, { method: "POST" }); } catch (e: any) { toast(e.message, true); }
  };

  return (
    <RunCtx.Provider value={ctx}>
      <div className="screen" style={{ height: "100%" }}>
        <TopBar
          crumbs={<><Link to="/activity">Activity</Link><span>/</span>
            {job.flow_id ? <Link to={`/flows/${job.flow_id}`}>{job.flow_name}</Link> : <span>{job.flow_name}</span>}
            <span>· {job.flow_version ? `v${job.flow_version}` : "draft"} · {job.label || "Run"}{replay ? " · Replay" : ""}</span></>}
          title={<h1 style={{ color: "var(--text-hi)" }} title={job.document_name}>{multi ? `${Object.keys(job.documents || {}).length} files · ${job.pages} pages` : job.document_name}</h1>}
          badge={<><span className={`status ${statusCls}`}><i className={view === "running" && statusCls !== "paused" ? "blink" : ""} />{statusText}</span>
            <span className={`badge ${job.priority}`}>{job.priority === "interactive" ? "Interactive" : "Bulk"}</span></>}
          middle={
            <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
              <div className="stat"><span>{replay ? "Replay time" : "Elapsed"}</span><span>{fmtClock(clock)}</span></div>
              <div className="stat"><span>Calls done</span><span>{fmtInt(shown.calls)} / {fmtInt(planned)}</span></div>
            </div>
          }>
          {replay ? (
            <>
              <div className="speed" role="group" aria-label="Replay speed">
                {[1, 2, 8].map((x) => <button key={x} aria-pressed={replay.speed === x} onClick={() => setReplay({ ...replay, speed: x })}>{x}×</button>)}
              </div>
              {!complete && !bad ? <button className="btn" onClick={() => setReplay({ ...replay, playing: !replay.playing })}>{replay.playing ? "Pause" : "Resume"}</button> : null}
              <button className="btn" onClick={() => setReplay(null)}>Exit replay</button>
            </>
          ) : null}
          {!replay && !finished ? <button className="btn" onClick={cancel}><Icon name="stop" />Cancel</button> : null}
          {finished ? <button className="btn" onClick={() => setReplay({ clock: 0, playing: true, speed: replay?.speed || 2 })}><Icon name="fold" />Replay</button> : null}
          {st.job === "done" ? <button className="btn primary" onClick={() => navigate(`/runs/${jobId}/results`)}>View results<Icon name="arrow" color="#fff" /></button> : null}
        </TopBar>

        <div className="overall"><div className={complete || bad ? "" : "shimmer"} style={{ width: `${pct}%`, backgroundColor: complete ? C.green : bad ? C.red : C.blue, boxShadow: `0 0 12px ${complete ? C.green : C.blue}` }} /></div>

        <div className="run-body">
          <main className="run-canvas" aria-label="Flow running">
            <div className="run-flow">
              <ReactFlow nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{ padding: 0.1, maxZoom: 1.15 }}
                nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} zoomOnDoubleClick={false} minZoom={0.3} maxZoom={1.6}
                proOptions={{ hideAttribution: true }}>
                <Background variant={BackgroundVariant.Dots} gap={22} size={1.3} color="rgba(140,160,190,0.22)" />
              </ReactFlow>
              {complete || bad ? (
                <div className={"done-card fadein" + (bad ? " bad" : "")}>
                  {bad ? <Icon name="warn" size={36} color={C.red} /> : (
                    <svg className="pop" aria-hidden="true" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke={C.green} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M7.5 12.5l3 3L17 9" /></svg>
                  )}
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 auto", minWidth: 0 }}>
                    <h3>{complete ? "Run complete" : view === "failed" ? "Run failed" : "Run cancelled"}</h3>
                    <p>{fmtInt(shown.calls)} calls · {shown.rejections} rejections · {fmtClock(clock)}{job.cost != null && !replay ? ` · $${job.cost.toFixed(2)}` : ""}</p>
                    <p>{complete ? `${outputs} output${outputs === 1 ? "" : "s"} ready` : shown.error}</p>
                  </div>
                  {complete && !replay ? <button className="btn primary" onClick={() => navigate(`/runs/${jobId}/results`)}>Results</button> : null}
                </div>
              ) : null}
            </div>
            <div className="legend">
              <span><i style={{ background: C.blue }} />Map</span>
              <span><i style={{ background: C.teal }} />Reduce</span>
              <span><i style={{ background: C.orange }} />Filter</span>
              <span><b style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--blue)", boxShadow: "0 0 8px var(--blue)", display: "block" }} />Items in motion</span>
              <span style={{ marginLeft: "auto" }}>{replay ? "Replay of a recorded run. Times and counts are the real ones." : "Live from the engine's event log."}</span>
            </div>
          </main>

          <aside className="live" aria-label="Live scheduler and events">
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="caps">Scheduler</span>
              <span style={{ fontSize: 12, color: "var(--muted-2)" }}>
                {replay || finished ? "This run's share of the quota" : "One shared quota per model, kept just under the ceiling"}
              </span>
            </div>
            {liveModels.map((q) => (
              <div key={q.model} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {replay || finished || !quota ? (
                  <>
                    <div className="model-head"><span>{modelLabel(cfg, q.model)}</span><span>last 60 s of this run</span></div>
                    <Gauge name="Output tokens per minute" value={`${fmtK(q.out_60)} / ${fmtK(q.otpm)}`} pct={(q.out_60 / q.otpm) * 100} from="#2F6FEB" to="#7FB0FF" mark={(1 - margin) * 100} />
                  </>
                ) : <ModelGauges q={q} cfg={cfg} margin={margin} />}
              </div>
            ))}
            <div className="tiles">
              <div className="tile"><span>In flight</span><span className="v">{shown.inflight}</span></div>
              <div className="tile"><span>Rejections</span><span className="v" style={{ color: shown.rejections ? C.red : C.green }}>{shown.rejections}</span></div>
              <div className={"tile" + (lane > 0 && job.priority === "bulk" ? " lane-on" : "")}><span>Interactive lane</span>
                <span className="t">{job.priority === "interactive" ? (finished || replay ? "Clear" : "This run") : lane > 0 ? "Going first" : "Clear"}</span></div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: "1 1 auto", minHeight: 0 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span className="caps">Live events</span>
                <span className={view === "running" ? "blink" : ""} style={{ width: 7, height: 7, borderRadius: "50%", background: complete ? C.green : bad ? C.red : "var(--blue)" }} />
              </div>
              {shown.feed.length === 0 ? <span style={{ fontSize: 12, color: "var(--faint)" }}>Waiting for the first task…</span> : null}
              <div className="feed">
                {shown.feed.slice(0, 9).map((f) => (
                  <div className="ev" key={f.id}>
                    <span className="tm">{fmtClock(f.t - shown.t0)}</span>
                    <i style={{ background: f.color, boxShadow: `0 0 6px ${f.color}` }} />
                    <span className="tx">{f.text}</span>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </RunCtx.Provider>
  );
}

export default function Run({ jobId }: { jobId: string }) {
  return <ReactFlowProvider><RunInner jobId={jobId} /></ReactFlowProvider>;
}
