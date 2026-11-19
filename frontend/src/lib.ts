import { useEffect, useState, useSyncExternalStore } from "react";

// ---------------------------------------------------------------- types

export type NodeType = "source" | "step" | "output";
export type Instruction = "map" | "reduce" | "filter";

export interface Field {
  name: string;
  type: string;
  description?: string;
  values?: string[];
  columns?: string[];
}
export interface StepData {
  title: string;
  system: string;
  instructions: string;
  model: string;
  max_tokens: number;
  expected_output?: number | null;
  thinking: string;
  output: { type: "text" | "schema"; fields: Field[] };
  track_pages: boolean;
}
export interface Rule {
  field: string;
  op: string;
  value?: any;
}
export interface EdgeData {
  /** "material": what the step works through. "reference": sent whole with every call of the step. */
  role?: "material" | "reference";
  instruction?: Instruction;
  window?: number;
  overlap?: number;
  consume?: "pages" | "outputs" | "both";
  rule?: Rule;
  [k: string]: unknown;
}
export interface GNode {
  id: string;
  type: NodeType;
  position: { x: number; y: number };
  data: any;
}
export interface GEdge {
  id: string;
  source: string;
  target: string;
  data: EdgeData;
}
export type ValueType = "text" | "number" | "choice" | "yesno" | "json";
/** A value a caller sends with the documents. Prompts and filter rules refer to it as {{Name}}. */
export interface ValueInput {
  name: string;
  type: ValueType;
  choices?: string[];
  default?: string | number | boolean | null;
  description?: string;
}
export interface Graph {
  nodes: GNode[];
  edges: GEdge[];
  inputs?: ValueInput[];
}
export interface Problem {
  message: string;
  node_id: string | null;
  edge_id: string | null;
  level: "error" | "warning";
}
export interface ModelInfo {
  key: string;
  label: string;
  gateway_name: string;
  itpm: number;
  otpm: number;
  out_capacity: number;
  thinking_off: string;
  pricing: { input: number; output: number; cache_read: number; cache_write: number };
}
export interface AppConfig {
  models: ModelInfo[];
  saturating_jobs: number;
  thinking_levels: string[];
  rule_ops: string[];
  field_types: string[];
  gateway: string;
  capacity_mode: string;
  safety_margin: number;
}
export interface Flow {
  flow_id: string;
  name: string;
  description: string;
  graph: Graph;
  version: number;
  published_version: number | null;
  draft_differs?: boolean;              // the draft has changed since the latest saved version
  is_sample: boolean;
  updated_at: string;
  nodes?: number;
  runs?: number;
  last_run?: string | null;
}
export interface Doc {
  document_id: string;
  name: string;
  pages: number;
  size_bytes: number;
  is_sample: boolean;
  kind?: "pdf" | "image" | "text";
  created_at?: string;
  /** Sent by a caller of the public endpoint. */
  via_api?: boolean;
  /** Runs that used this file, and how many of those have not finished. */
  jobs?: number;
  active?: number;
}
export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
/** "3 pages", or "image" for a picture (always one page). */
export function docSize(d: { pages: number; kind?: string | null }): string {
  return d.kind === "image" ? "image" : `${d.pages} page${d.pages === 1 ? "" : "s"}${d.kind === "text" ? " of text" : ""}`;
}
export const UPLOAD_ACCEPT = "application/pdf,.pdf,image/png,image/jpeg,image/gif,image/webp,image/bmp,image/tiff,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tif,.tiff,text/*,.txt,.md,.csv,.tsv,.json,.xml,.log,.yaml,.yml";
export interface Estimate {
  calls: number;
  output_tokens: number;
  input_tokens?: number;
  cost: number;
  pages: number;
  assumed_filter_ratio?: boolean;
  per_node: Record<string, any>;
}
export interface JobStep {
  node_id: string;
  node_type: NodeType;
  title: string;
  instruction: string | null;
  model: string | null;
  state: string;
  items_in: number | null;
  items_kept: number | null;
  tasks_total: number;
  tasks_done: number;
}
export interface EngineEvent {
  event_id: number;
  ts: string;
  kind: string;
  job_id: string | null;
  node_id: string | null;
  task_id: number | null;
  model: string | null;
  data: any;
}
export interface Job {
  job_id: string;
  flow_id: string | null;
  flow_name: string;
  flow_version: number | null;
  document_id: string;
  document_name: string;
  pages: number;
  documents?: Record<string, { document_id: string; name: string; pages: number }>;
  input_values?: Record<string, unknown>;
  priority: "interactive" | "bulk";
  state: string;
  label: string;
  error: string | null;
  submitted_at: string;
  started_at: string | null;
  finished_at: string | null;
  wall_s: number;
  tasks_total: number;
  tasks_done: number;
  calls: number;
  rejections: number;
  output_tokens: number;
  in_flight: number;
  graph?: Graph;
  steps?: JobStep[];
  events?: EngineEvent[];
  cost?: number;
}
export interface QuotaModel {
  model: string;
  otpm: number;
  itpm: number;
  out_capacity: number;
  out_level: number;
  hold_s: number;
  rejections: number;
  open_output: number;
  open_calls: number;
  out_60: number;
  in_60: number;
  rej_60: number;
  ready: number;
  ready_interactive: number;
  waiting: number;
}
export interface Quota {
  models: QuotaModel[];
  jobs: { running: number; queued: number };
  ts: number;
  worker?: any;
}

// ---------------------------------------------------------------- api

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, body: any) {
    super((body && (body.message || body.error || body.detail)) || `Request failed (${status})`);
    this.status = status;
    this.body = body;
  }
}

export async function api<T = any>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const opts: RequestInit = { ...init };
  if (init && "json" in init) {
    opts.method = opts.method || "POST";
    opts.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
    opts.body = JSON.stringify(init.json);
  }
  const res = await fetch(path, opts);
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

let configCache: Promise<AppConfig> | null = null;
export function loadConfig(): Promise<AppConfig> {
  if (!configCache) configCache = api<AppConfig>("/api/config");
  return configCache;
}
export function useConfig(): AppConfig | null {
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  useEffect(() => {
    loadConfig().then(setCfg).catch(() => setCfg(null));
  }, []);
  return cfg;
}

// ---------------------------------------------------------------- router (history API, no dependency)

const listeners = new Set<() => void>();
function emit() {
  listeners.forEach((l) => l());
}
window.addEventListener("popstate", emit);
export function navigate(to: string, replace = false) {
  if (to === window.location.pathname + window.location.search) return;
  if (replace) window.history.replaceState(null, "", to);
  else window.history.pushState(null, "", to);
  emit();
}
export function usePath(): string {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => window.location.pathname,
  );
}

// ---------------------------------------------------------------- theme (one switch for the whole site)

export type Theme = "light" | "dark";
function startTheme(): Theme {
  try {
    const t = localStorage.getItem("theme");
    if (t === "light" || t === "dark") return t;
  } catch { /* storage may be unavailable */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
let theme: Theme = startTheme();
document.documentElement.dataset.theme = theme;
const themeListeners = new Set<() => void>();
export function setTheme(t: Theme) {
  theme = t;
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("theme", t); } catch { /* storage may be unavailable */ }
  themeListeners.forEach((l) => l());
}
export function useTheme(): Theme {
  return useSyncExternalStore(
    (cb) => {
      themeListeners.add(cb);
      return () => themeListeners.delete(cb);
    },
    () => theme,
  );
}

// ---------------------------------------------------------------- helpers

export const INSTRUCTION_COLOR: Record<string, { line: string; text: string; bright: string }> = {
  // "text" follows the theme (see --ins-* in styles.css); lines read on both backgrounds.
  map: { line: "#2F6FEB", text: "var(--ins-map)", bright: "#4C8DFF" },
  reduce: { line: "#0B8C7D", text: "var(--ins-reduce)", bright: "#2BC4B0" },
  filter: { line: "#C2570C", text: "var(--ins-filter)", bright: "#FF9A3C" },
  fold: { line: "#6B3FC9", text: "var(--ins-fold)", bright: "#A07CFF" },
  reference: { line: "#7A8494", text: "var(--ins-ref)", bright: "#B6C0CE" },
  none: { line: "#9AA3AE", text: "var(--muted)", bright: "#3DD68C" },
};
export const isRef = (e: { data?: EdgeData | null }): boolean => e.data?.role === "reference";

export function uid(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}
export function fmtInt(n: number | null | undefined): string {
  return n == null ? "-" : Math.round(n).toLocaleString("en-US");
}
export function fmtK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return `${Math.round(n)}`;
}
export function fmtCost(n: number): string {
  if (n < 0.01) return "under $0.01";
  return `$${n < 10 ? n.toFixed(2) : n.toFixed(n < 100 ? 1 : 0)}`;
}
export function fmtClock(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
export function fmtSecs(sec: number | null | undefined): string {
  if (sec == null) return "-";
  if (sec < 60) return `${sec.toFixed(sec < 10 ? 1 : 0)} s`;
  return `${Math.floor(sec / 60)} min ${Math.round(sec % 60)} s`;
}
export function fmtAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return `${Math.floor(d / 86400)} d ago`;
}
export function pageRanges(pages: number[]): string {
  if (!pages || !pages.length) return "";
  const ps = [...new Set(pages)].sort((a, b) => a - b);
  const out: string[] = [];
  let start = ps[0];
  let prev = ps[0];
  for (const p of ps.slice(1)) {
    if (p === prev + 1) {
      prev = p;
      continue;
    }
    out.push(prev > start ? `${start} to ${prev}` : `${start}`);
    start = prev = p;
  }
  out.push(prev > start ? `${start} to ${prev}` : `${start}`);
  return out.join(", ");
}
export function modelLabel(cfg: AppConfig | null, key: string | null | undefined): string {
  if (!key) return "";
  const m = cfg?.models.find((x) => x.key === key);
  return (m?.label || key).replace(/^Claude /, "");
}
export function ruleText(rule?: Rule): string {
  if (!rule || !rule.field) return "no rule yet";
  const op: Record<string, string> = {
    equals: "is", not_equals: "is not", in: "is one of", contains: "contains",
    is_true: "is true", is_false: "is false", greater_than: ">", less_than: "<",
  };
  if (rule.op === "is_true" || rule.op === "is_false") return `${rule.field} ${op[rule.op]}`;
  return `${rule.field} ${op[rule.op] || "is"} ${rule.value ?? ""}`.trim();
}
export function windowCount(n: number, size: number, overlap: number): number {
  size = Math.max(1, size);
  overlap = Math.max(0, Math.min(overlap, size - 1));
  if (n <= 0) return 0;
  if (n <= size) return 1;
  return 1 + Math.ceil((n - size) / (size - overlap));
}
export function defaultStep(title = "New step"): StepData {
  return {
    title, system: "", instructions: "", model: "sonnet", max_tokens: 1500, thinking: "off",
    output: { type: "text", fields: [] }, track_pages: true,
  };
}
export function useInterval(fn: () => void, ms: number | null) {
  useEffect(() => {
    if (ms == null) return;
    const t = setInterval(fn, ms);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms]);
}


// ---------------------------------------------------------------- value inputs

export const VALUE_TYPES: { key: ValueType; label: string }[] = [
  { key: "text", label: "Text" }, { key: "number", label: "Number" }, { key: "choice", label: "Choice" },
  { key: "yesno", label: "Yes / no" }, { key: "json", label: "JSON" },
];
export const valueKey = (name: unknown): string => String(name ?? "").trim().split(/\s+/).join(" ").toLowerCase();
export const placeholder = (name: string): string => `{{${name}}}`;
const PLACEHOLDER = /\{\{\s*([^{}\n]+?)\s*\}\}/g;

export function placeholdersIn(text: unknown): string[] {
  return typeof text === "string" ? Array.from(text.matchAll(PLACEHOLDER), (m) => valueKey(m[1])) : [];
}

/** The declared inputs a run needs: all of them, or only those read by the blocks in `keep` (a step test). */
export function inputsFor(graph: Graph, keep?: Set<string> | null): ValueInput[] {
  const declared = (graph.inputs || []).filter((i) => i.name.trim());
  if (!keep) return declared;
  const used = new Set<string>();
  for (const n of graph.nodes) {
    if (n.type !== "step" || !keep.has(n.id)) continue;
    [n.data?.system, n.data?.instructions].forEach((t) => placeholdersIn(t).forEach((k) => used.add(k)));
  }
  for (const e of graph.edges) {
    if (!keep.has(e.target) || !keep.has(e.source)) continue;
    const v = e.data?.rule?.value;
    (Array.isArray(v) ? v : [v]).forEach((t) => placeholdersIn(t).forEach((k) => used.add(k)));
  }
  return declared.filter((i) => used.has(valueKey(i.name)));
}

/** Replaces {{old}} with {{new}} wherever it is written. */
export function renamePlaceholder<T>(text: T, from: string, to: string): T {
  if (typeof text !== "string" || !from.trim() || !to.trim()) return text;
  const k = valueKey(from);
  return text.replace(PLACEHOLDER, (m, name) => (valueKey(name) === k ? placeholder(to) : m)) as unknown as T;
}

export function showValue(v: unknown): string {
  if (v === true) return "yes";
  if (v === false) return "no";
  if (v !== null && typeof v === "object") return JSON.stringify(v);
  return String(v ?? "");
}
