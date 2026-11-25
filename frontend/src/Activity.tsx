import { useEffect, useMemo, useState } from "react";
import { api, ApiError, Doc, docSize, Flow, fmtClock, fmtInt, fmtWhen, inputsFor, Job, navigate, Quota, useConfig, useInterval, ValueInput } from "./lib";
import { loadValues, missingValues, saveValues, Values, ValuesForm, valuesToSend } from "./Values";
import { ModelGauges } from "./Run";
import { Icon, Modal, toast, TopBar } from "./ui";

export default function Activity() {
  const cfg = useConfig();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [flows, setFlows] = useState<Flow[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [flowId, setFlowId] = useState("");
  const [sources, setSources] = useState<{ id: string; title: string; hint?: string }[]>([]);
  const [docBy, setDocBy] = useState<Record<string, string>>({});
  const [needed, setNeeded] = useState<ValueInput[]>([]);       // the chosen flow's value inputs
  const [runs, setRuns] = useState<{ version: number | null; published: boolean } | null>(null);   // which version will run
  const [values, setValues] = useState<Values>({});
  const [nInt, setNInt] = useState(1);
  const [nBulk, setNBulk] = useState(0);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api<Job[]>("/api/jobs?limit=80").then(setJobs).catch(() => {});
  useEffect(() => {
    load();
    api<Flow[]>("/api/flows").then((f) => { setFlows(f); setFlowId((c) => c || f[0]?.flow_id || ""); });
    api<Doc[]>("/api/documents").then(setDocs);
    const es = new EventSource("/api/stream?job_id=-");
    es.addEventListener("quota", (m) => setQuota(JSON.parse((m as MessageEvent).data)));
    return () => es.close();
  }, []);
  // The sources of the chosen flow: each needs a document.
  useEffect(() => {
    if (!flowId) return;
    let stale = false;
    setRuns(null);
    // The version that will run: the published one, else the latest saved one, else the draft.
    api<{ version: number | null; published: boolean; graph: Flow["graph"] }>(`/api/flows/${flowId}/runnable`).then((f) => {
      if (stale) return;
      setRuns({ version: f.version, published: f.published });
      setSources(f.graph.nodes.filter((n) => n.type === "source").sort((a, b) => a.position.y - b.position.y)
        .map((n) => ({ id: n.id, title: n.data?.title || "File", hint: n.data?.default_document })));
      setNeeded(inputsFor(f.graph));
      setValues(loadValues(flowId));
    }).catch(() => { setSources([]); setNeeded([]); });
    return () => { stale = true; };
  }, [flowId]);
  useEffect(() => {
    if (!docs.length) return;
    const has = (id?: string) => (id && docs.some((d) => d.document_id === id) ? id : "");
    // The file chosen for this source in the builder is remembered in the browser; start from that.
    let remembered: Record<string, string> = {};
    try { remembered = JSON.parse(localStorage.getItem(`docs:${flowId}`) || "{}"); } catch { /* storage may be unavailable */ }
    setDocBy((cur) => Object.fromEntries(sources.map((s) => [s.id, has(cur[s.id]) || has(remembered[s.id]) || has(s.hint) || docs.find((d) => d.name === s.title)?.document_id || ""])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sources, docs]);
  const missing = missingValues(needed, values);
  const chosen = sources.length > 0 && sources.every((s) => docBy[s.id]) && missing.length === 0;
  const active = jobs.some((j) => j.state === "queued" || j.state === "running");
  useInterval(load, active ? 1000 : 4000);

  const order = useMemo(() => {
    const live = jobs.filter((j) => j.state === "queued" || j.state === "running")
      .sort((a, b) => (a.priority === b.priority ? a.submitted_at.localeCompare(b.submitted_at) : a.priority === "interactive" ? -1 : 1));
    return Object.fromEntries(live.map((j, i) => [j.job_id, i + 1]));
  }, [jobs]);

  const cancelJob = async (j: Job) => {
    if (!window.confirm(`Cancel "${j.label || j.flow_name}"? Calls already sent will finish and be paid for; their replies are not used.`)) return;
    try {
      await api(`/api/jobs/${j.job_id}/cancel`, { method: "POST" });
      toast("Job cancelled");
    } catch (e: any) { toast(e.message, true); }
    load();
  };
  const submit = async (confirmed = false) => {
    setBusy(true);
    try {
      await api("/api/jobs", { json: { flow_id: flowId, documents: docBy, values: valuesToSend(needed, values), count: nInt, bulk_count: nBulk, confirm_saturation: confirmed } });
      setConfirm(null);
      saveValues(flowId, values);
      toast(`${nInt + nBulk} job${nInt + nBulk === 1 ? "" : "s"} submitted`);
      load();
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 409) setConfirm(e.body?.message || "This can saturate the endpoint.");
      else toast(e.message, true);
    }
    setBusy(false);
  };

  const margin = cfg?.safety_margin ?? 0.05;
  const inFlight = quota?.models.reduce((a, q) => a + q.open_calls, 0) ?? 0;
  const rej60 = quota?.models.reduce((a, q) => a + q.rej_60, 0) ?? 0;
  const waitingInt = quota?.models.reduce((a, q) => a + q.ready_interactive, 0) ?? 0;

  return (
    <div className="screen">
      <TopBar crumbs={<span>Document Engine</span>} title={<h1 style={{ color: "var(--text-hi)" }}>Activity</h1>}
        badge={<span className={"status " + (active ? "running" : "queued")}><i className={active ? "blink" : ""} />{active ? "Working" : "Idle"}</span>} />
      <div className="act">
        <div className="tiles" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
          <div className="tile"><span>Jobs running</span><span className="v">{quota?.jobs.running ?? 0}</span></div>
          <div className="tile"><span>Jobs queued</span><span className="v">{quota?.jobs.queued ?? 0}</span></div>
          <div className="tile"><span>Calls in flight</span><span className="v">{inFlight}</span></div>
          <div className="tile"><span>Rejections, last 60 s</span><span className="v" style={{ color: rej60 ? "var(--red)" : "var(--green)" }}>{rej60}</span></div>
          <div className={"tile" + (waitingInt > 0 ? " lane-on" : "")}><span>Interactive lane</span><span className="t">{waitingInt > 0 ? `${waitingInt} calls waiting` : "Clear"}</span></div>
        </div>

        <div className="act-grid">
          <div style={{ display: "flex", flexDirection: "column", gap: 18, minWidth: 0 }}>
            <div className="panel">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                <span className="caps">Shared quota, by model</span>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>The mark on each bar is the ceiling the scheduler stays under</span>
              </div>
              <div className="models">
                {(quota?.models || []).map((q) => (
                  <div key={q.model} className={"mcard" + (q.hold_s > 0 ? " held" : "")}><ModelGauges q={q} cfg={cfg} margin={margin} /></div>
                ))}
                {!quota ? <span style={{ color: "var(--muted)", fontSize: 13 }}>Connecting…</span> : null}
              </div>
            </div>

            <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ padding: "16px 18px 6px" }}><span className="caps">Jobs</span></div>
              <div style={{ overflowX: "auto" }}>
                <table className="table">
                  <thead><tr><th>Queue</th><th>Job</th><th>Priority</th><th>Status</th><th style={{ minWidth: 150 }}>Progress</th><th className="num">In flight</th><th className="num">Rejections</th><th className="num">Submitted</th><th className="num">Finished</th><th className="num">Time</th><th><span className="sr">Actions</span></th></tr></thead>
                  <tbody>
                    {jobs.map((j) => {
                      const pct = j.state === "done" ? 100 : j.tasks_total ? (j.tasks_done / j.tasks_total) * 100 : 0;
                      const color = j.state === "done" ? "#2F8F63" : j.state === "failed" || j.state === "cancelled" ? "#C44545" : j.priority === "interactive" ? "#A07CFF" : "#4C8DFF";
                      return (
                        <tr key={j.job_id} className="click" onClick={() => navigate(`/runs/${j.job_id}`)}>
                          <td className="mono" style={{ color: "var(--muted)" }}>{order[j.job_id] ? `#${order[j.job_id]}` : ""}</td>
                          <td><div style={{ fontWeight: 600, color: "var(--text-hi)" }}>{j.label || j.flow_name}</div>
                            <div style={{ fontSize: 12, color: "var(--muted)" }}>{j.flow_name} · {j.document_name}</div></td>
                          <td><span className={`badge ${j.priority}`}>{j.priority === "interactive" ? "Interactive" : "Bulk"}</span></td>
                          <td><span className={`status ${j.state}`}><i className={j.state === "running" ? "blink" : ""} />{j.state[0].toUpperCase() + j.state.slice(1)}</span></td>
                          <td><div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div className="prog" style={{ flex: "1 1 auto" }}><div style={{ width: `${pct}%`, background: color }} /></div>
                            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>{fmtInt(j.tasks_done)}/{fmtInt(j.tasks_total)}</span></div></td>
                          <td className="num">{j.in_flight || ""}</td>
                          <td className="num" style={{ color: j.rejections ? "var(--red)" : "var(--muted)" }}>{j.rejections}</td>
                          <td className="num" style={{ whiteSpace: "nowrap" }} title={j.started_at ? `First call started ${fmtWhen(j.started_at)}` : "No call has started yet"}>{fmtWhen(j.submitted_at)}</td>
                          <td className="num" style={{ whiteSpace: "nowrap" }}>{fmtWhen(j.finished_at)}</td>
                          <td className="num">{fmtClock(j.wall_s)}</td>
                          <td onClick={(e) => e.stopPropagation()}>
                            {j.state === "queued" || j.state === "running"
                              ? <button className="btn small ghost danger" onClick={() => cancelJob(j)}><Icon name="stop" />Cancel</button> : null}
                          </td>
                        </tr>
                      );
                    })}
                    {!jobs.length ? <tr><td colSpan={11} style={{ color: "var(--muted)", padding: 20 }}>No jobs yet. Submit one on the right, or start a test run from a flow.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="panel">
            <span className="caps">Submit jobs</span>
            <div className="field"><label htmlFor="a-flow">Flow</label>
              <select id="a-flow" className="select" value={flowId} onChange={(e) => setFlowId(e.target.value)}>
                {flows.map((f) => <option key={f.flow_id} value={f.flow_id}>{f.name}</option>)}
              </select>
              {runs && <p className="hint" style={{ marginTop: 6 }}>{runs.version == null
                ? "Runs the draft: no version of this flow has been saved yet."
                : runs.published ? `Runs v${runs.version}, the published version.`
                : `Runs v${runs.version}, the latest saved version. This flow is not published.`}</p>}</div>
            {sources.map((s) => (
              <div className="field" key={s.id}><label htmlFor={`a-doc-${s.id}`}>{sources.length > 1 ? s.title : "File"}</label>
                <select id={`a-doc-${s.id}`} className="select" value={docBy[s.id] || ""} onChange={(e) => setDocBy((c) => ({ ...c, [s.id]: e.target.value }))}>
                  {!docBy[s.id] ? <option value="">Choose a file</option> : null}
                  {docs.map((d) => <option key={d.document_id} value={d.document_id}>{d.name} · {docSize(d)}</option>)}
                </select></div>
            ))}
            <ValuesForm inputs={needed} values={values} onChange={setValues} />
            <div className="grid2">
              <div className="field"><label htmlFor="a-int">Interactive jobs</label>
                <input id="a-int" className="input" type="number" min={0} max={50} value={nInt} onChange={(e) => setNInt(Math.max(0, Number(e.target.value)))} /></div>
              <div className="field"><label htmlFor="a-bulk">Bulk jobs</label>
                <input id="a-bulk" className="input" type="number" min={0} max={50} value={nBulk} onChange={(e) => setNBulk(Math.max(0, Number(e.target.value)))} /></div>
            </div>
            <p className="hint">All jobs are submitted at the same moment. Interactive jobs go first; within a class, the job submitted earlier goes first.</p>
            <button className="btn primary" style={{ justifyContent: "center" }} disabled={busy || nInt + nBulk < 1 || !flowId || !chosen} onClick={() => submit(false)}>
              <Icon name="play" color="#fff" />Submit {nInt + nBulk} job{nInt + nBulk === 1 ? "" : "s"}
            </button>
            {quota?.worker ? (
              <div className="mini" style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
                <span>Admission <b>{quota.worker.admission_ms.median ?? "-"} ms</b> median</span>
                <span><b>{quota.worker.admission_ms.p95 ?? "-"} ms</b> p95</span>
                <span>Peak in flight <b>{quota.worker.peak_in_flight}</b></span>
              </div>
            ) : null}
          </div>
        </div>
      </div>
      {confirm ? (
        <Modal title="Start a saturating run?" onClose={() => setConfirm(null)}>
          <div className="notice">{confirm}</div>
          <p className="hint">Calls go to {cfg?.gateway} and cost real money.</p>
          <div className="foot">
            <button className="btn" onClick={() => setConfirm(null)}>Cancel</button>
            <button className="btn primary" disabled={busy} onClick={() => submit(true)}>Start {nInt + nBulk} jobs</button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
