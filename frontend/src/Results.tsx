import { ReactNode, useEffect, useState } from "react";
import { api, fmtSecs, fmtWhen, Job, navigate, pageRanges } from "./lib";
import { Icon, Link, toast, TopBar } from "./ui";

interface OutItem { pages: number[]; text: string | null; data: any; truncated: boolean; input: string | null }
interface Input { node_id: string; input: string; document_id: string; name: string; pages: number; kind?: "pdf" | "image" | "text" | null }

/** One page of a source file: the PDF page, the image, or that page of a text file. */
function PageView({ doc, page }: { doc: Input; page: number }) {
  const url = `/api/documents/${doc.document_id}/pages/${Math.min(page, doc.pages)}`;
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    if (doc.kind !== "text") return;
    let stale = false;
    setText(null);
    fetch(url).then((r) => (r.ok ? r.text() : Promise.reject(new Error("not found")))).then((t) => { if (!stale) setText(t); })
      .catch(() => { if (!stale) setText("This page could not be loaded."); });
    return () => { stale = true; };
  }, [url, doc.kind]);
  if (doc.kind === "image") return <div className="view-img"><img src={url} alt={doc.name} /></div>;
  if (doc.kind === "text") return <pre className="view-text">{text ?? "Loading…"}</pre>;
  return <iframe title={`Page ${page}`} src={`${url}#toolbar=0&view=FitH`} />;
}
/** A page of one of the job's documents: which input, and the page number. */
interface Ref { input: string; page: number }
interface Output { node_id: string; title: string; state: string; format: string; items: OutItem[]; table: { columns: string[]; rows: Record<string, any>[] } | null }
interface Outputs { document_id: string; document_name: string; state: string; multi: boolean; inputs: Input[]; outputs: Output[]; values?: { name: string; text: string }[] }

// [p. 12], [pp. 12-14], and with several documents [Invoice p. 2]
const CITE = /\[(?:([^\[\]]{1,60}?),?\s+)?(?:pp?\.|pages?)\s*([\d,\s\-–to]+)\]/gi;

function firstPage(s: string): number | null {
  const m = s.match(/\d+/);
  return m ? Number(m[0]) : null;
}

interface CiteCtx { onCite: (r: Ref) => void; current: Ref | null; inputs: Input[]; fallback: string }
/** The input a citation names. Unknown or missing names fall back to the item's own input. */
function resolve(name: string | undefined, c: CiteCtx): Input | undefined {
  const want = (name || "").trim().toLowerCase();
  return (want ? c.inputs.find((i) => i.input.toLowerCase() === want || i.name.toLowerCase() === want) : undefined)
    || c.inputs.find((i) => i.input === c.fallback) || c.inputs[0];
}

function inline(text: string, c: CiteCtx, key: string): ReactNode[] {
  const multi = c.inputs.length > 1;
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(CITE)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push(...bold(text.slice(last, idx), `${key}-t${i}`));
    const p = firstPage(m[2]);
    const inp = resolve(m[1], c);
    const on = p != null && inp && c.current?.page === p && c.current.input === inp.input;
    out.push(
      <button key={`${key}-c${i}`} className={"cite" + (on ? " on" : "")} onClick={() => p != null && inp && c.onCite({ input: inp.input, page: p })}
        title={`Open page ${m[2].trim()}${inp ? ` of ${inp.name}` : ""}`}>{multi && inp ? `${inp.input} ` : ""}p. {m[2].trim().replace(/\s*-\s*/g, "–")}</button>,
    );
    last = idx + m[0].length;
    i++;
  }
  if (last < text.length) out.push(...bold(text.slice(last), `${key}-e`));
  return out;
}
function bold(text: string, key: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong> : <span key={`${key}-${i}`}>{part}</span>);
}

/** A small renderer for the headings, bullets and paragraphs models write. */
function Rendered({ text, c }: { text: string; c: CiteCtx }) {
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = () => { if (list.length) { blocks.push(<ul key={`ul${blocks.length}`}>{list}</ul>); list = []; } };
  text.split("\n").forEach((raw, i) => {
    const line = raw.trimEnd();
    const k = `l${i}`;
    if (!line.trim()) { flush(); return; }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) { flush(); blocks.push(h[1].length <= 2 ? <h2 key={k}>{inline(h[2], c, k)}</h2> : <h3 key={k}>{inline(h[2], c, k)}</h3>); return; }
    const b = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (b) { list.push(<li key={k}>{inline(b[1], c, k)}</li>); return; }
    if (/^[A-Z][A-Za-z ,&/]{2,40}:?$/.test(line.trim()) && line.trim().split(" ").length <= 5) { flush(); blocks.push(<h3 key={k}>{line.trim().replace(/:$/, "")}</h3>); return; }
    flush();
    blocks.push(<p key={k}>{inline(line, c, k)}</p>);
  });
  flush();
  return <>{blocks}</>;
}

function csv(table: { columns: string[]; rows: Record<string, any>[] }): string {
  // A cell that a spreadsheet would read as a formula gets a leading apostrophe, so it stays text.
  const esc = (v: any) => {
    const s = String(v ?? "");
    return `"${(/^[=+\-@\t\r]/.test(s) && !/^-?\d+([.,]\d+)?$/.test(s) ? "'" + s : s).replace(/"/g, '""')}"`;
  };
  return [table.columns.map(esc).join(","), ...table.rows.map((r) => table.columns.map((c) => esc(r[c])).join(","))].join("\n");
}

export default function Results({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [data, setData] = useState<Outputs | null>(null);
  const [tab, setTab] = useState(0);
  const [page, setPage] = useState<Ref | null>(null);

  useEffect(() => {
    api<Job>(`/api/jobs/${jobId}?events=false`).then(setJob).catch((e) => toast(e.message, true));
    api<Outputs>(`/api/jobs/${jobId}/outputs`).then(setData).catch((e) => toast(e.message, true));
  }, [jobId]);

  const out = data?.outputs[tab];
  const inputs = data?.inputs || [];
  const multi = inputs.length > 1;
  const shownDoc = page ? inputs.find((i) => i.input === page.input) || inputs[0] : undefined;
  // A table's page cell: "2", "1-3", or with several documents "Invoice 2".
  const cellRef = (v: string): Ref | null => {
    const s = String(v).trim();
    // The input's name first, longest first: a name may itself end in a number ("File 2 3" is page 3 of File 2).
    const named = [...inputs].sort((a, b) => b.input.length - a.input.length).find((i) => s.startsWith(i.input + " "));
    const rest = named ? s.slice(named.input.length).trim() : s;
    if (!/^\d[\d,\s\-–]*$/.test(rest)) return null;
    const p = firstPage(rest);
    const inp = named || inputs[0];
    return p != null && inp ? { input: inp.input, page: p } : null;
  };
  const download = (name: string, body: string, type: string) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([body], { type }));
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="screen" style={{ height: "100%" }}>
      <TopBar
        crumbs={<><Link to="/activity">Activity</Link><span>/</span><Link to={`/runs/${jobId}`}>{job?.label || "Run"}</Link><span>/ Results</span></>}
        title={<h1 title={data?.document_name}>{multi ? inputs.map((i) => i.input).join(", ") : data?.document_name || "Results"}</h1>}
        badge={job ? <span className="pill gray">{job.flow_name}{job.flow_version ? ` · v${job.flow_version}` : ""}</span> : null}>
        <button className="btn" onClick={() => navigate(`/runs/${jobId}`)}>Back to the run</button>
      </TopBar>
      <div className="results">
        <div className="results-main">
          {!data ? <p className="empty">Loading results…</p> : null}
          {data && data.state !== "done" ? <div className="notice">This run is {data.state}. Results shown here may be incomplete.</div> : null}
          {job ? (
            <div className="vals">
              <span>Submitted <b className="mono">{fmtWhen(job.submitted_at)}</b></span><span>·</span>
              <span>Started <b className="mono">{fmtWhen(job.started_at)}</b></span><span>·</span>
              <span>Finished <b className="mono">{fmtWhen(job.finished_at)}</b></span>
              {job.finished_at ? <><span>·</span><span>Took <b className="mono">{fmtSecs(job.wall_s)}</b></span></> : null}
            </div>
          ) : null}
          {data?.values?.length ? (
            <div className="vals"><span>Ran with</span>{data.values.map((v) => <span className="pill gray" key={v.name} title={`${v.name}: ${v.text}`}>{v.name}: {v.text}</span>)}</div>
          ) : null}
          {data && data.outputs.length > 1 ? (
            <div className="out-tabs" role="tablist">
              {data.outputs.map((o, i) => <button key={o.node_id} role="tab" aria-selected={tab === i} onClick={() => setTab(i)}>{o.title}</button>)}
            </div>
          ) : null}
          {out ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <h2 style={{ fontSize: 20 }}>{out.title}</h2>
                <span style={{ display: "flex", gap: 8 }}>
                  {out.format === "table" && out.table ? <button className="btn small" onClick={() => download(`${out.title}.csv`, csv(out.table!), "text/csv")}><Icon name="download" />CSV</button> : null}
                  {out.items.some((i) => i.text) ? <button className="btn small" onClick={() => download(`${out.title}.md`, out.items.map((i) => i.text || "").join("\n\n"), "text/markdown")}><Icon name="download" />Text</button> : null}
                </span>
              </div>
              {!out.items.length ? <p className="empty">This output is empty. No items reached it.</p> : null}
              {out.format === "table" && out.table && out.items.some((i) => i.truncated) ? (
                <div className="notice" style={{ marginBottom: 12 }}>At least one reply behind this table was cut off at the step's max output tokens, so rows may be missing. Raise it and run again.</div>
              ) : null}
              {out.format === "table" && out.table ? (
                <div className="tbl-wrap">
                  <table className="table">
                    <thead><tr>{out.table.columns.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
                    <tbody>
                      {out.table.rows.map((r, i) => (
                        <tr key={i}>
                          {out.table!.columns.map((c) => (
                            <td key={c}>{c === "page" ? (() => {
                              const ref = cellRef(String(r[c]));
                              return <button className={"cite" + (ref && page?.page === ref.page && page.input === ref.input ? " on" : "")} onClick={() => setPage(ref)}>{multi && ref ? `${ref.input} ` : ""}p. {ref ? String(r[c]).replace(ref.input, "").trim() : r[c]}</button>;
                            })() : String(r[c] ?? "")}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : out.items.length ? (
                <div className="doc">
                  {out.items.map((it, i) => (
                    <div key={i}>
                      {out.items.length > 1 ? <div className="item-sep">{it.input ? `${it.input} · pages` : "Pages"} {pageRanges(it.pages)}</div> : null}
                      {it.truncated ? <div className="notice" style={{ marginBottom: 12 }}>This output was cut off at the step's max output. Raise it and run again for the full text.</div> : null}
                      {it.text ? <Rendered text={it.text} c={{ onCite: setPage, current: page, inputs, fallback: it.input || inputs[0]?.input || "" }} /> : <pre className="raw">{JSON.stringify(it.data, null, 1)}</pre>}
                    </div>
                  ))}
                </div>
              ) : null}
              <p className="hint">Select a page reference to see that page of {multi ? "its file" : "the file"} beside the text.</p>
            </>
          ) : null}
        </div>
        {page != null && data && shownDoc ? (
          <aside className="viewer" aria-label="Source page">
            <div className="vh">
              <strong>{multi ? `${shownDoc.input} · ` : ""}{shownDoc.name} · page {Math.min(page.page, shownDoc.pages)}{page.page > shownDoc.pages ? ` (the last page; the text cites page ${page.page})` : ""}</strong>
              <span style={{ display: "flex", gap: 4 }}>
                <button className="btn small" disabled={page.page <= 1} onClick={() => setPage({ ...page, page: Math.min(page.page, shownDoc.pages) - 1 })}>Previous</button>
                <button className="btn small" disabled={page.page >= shownDoc.pages} onClick={() => setPage({ ...page, page: page.page + 1 })}>Next</button>
                <button className="icon-btn" aria-label="Close page" onClick={() => setPage(null)}><Icon name="x" size={16} /></button>
              </span>
            </div>
            <PageView doc={shownDoc} page={page.page} />
          </aside>
        ) : null}
      </div>
    </div>
  );
}
