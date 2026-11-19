import { useEffect, useState } from "react";
import { api, Flow, fmtAgo, navigate } from "./lib";
import { Icon, toast, TopBar } from "./ui";

export default function Flows() {
  const [flows, setFlows] = useState<Flow[] | null>(null);

  const load = () => api<Flow[]>("/api/flows").then(setFlows).catch((e) => toast(e.message, true));
  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      const f = await api<Flow>("/api/flows", { json: { name: "Untitled flow" } });
      navigate(`/flows/${f.flow_id}`);
    } catch (e: any) { toast(e.message, true); }
  };
  const duplicate = async (id: string) => {
    try {
      const f = await api<Flow>(`/api/flows/${id}/duplicate`, { method: "POST" });
      navigate(`/flows/${f.flow_id}`);
    } catch (e: any) { toast(e.message, true); }
  };
  const remove = async (f: Flow) => {
    if (!window.confirm(`Delete "${f.name}"? Its past runs stay in Activity.`)) return;
    try {
      await api(`/api/flows/${f.flow_id}`, { method: "DELETE" });
      toast(`${f.name} deleted`);
    } catch (e: any) { toast(e.message, true); }
    load();
  };

  return (
    <div className="screen">
      <TopBar crumbs={<span>Document Engine</span>} title={<h1>Flows</h1>}>
        <button className="btn primary" onClick={create}><Icon name="plus" />New flow</button>
      </TopBar>
      <div className="page">
        <div className="page-head">
          <div>
            <h1>Flows</h1>
            <p>A flow is a set of steps applied to one or more files: PDFs, images or text files. Each step is a model call, and the connection into it
              says how it is applied: over windows of pages, once over everything, or only to pages that match a rule.</p>
          </div>
        </div>
        {flows === null ? <p className="empty">Loading flows…</p> : null}
        {flows && flows.length === 0 ? <p className="empty">No flows yet. Create one to get started.</p> : null}
        <div className="cards">
          {(flows || []).map((f) => (
            <div key={f.flow_id} className="card" role="button" tabIndex={0}
              onClick={() => navigate(`/flows/${f.flow_id}`)}
              onKeyDown={(e) => e.key === "Enter" && navigate(`/flows/${f.flow_id}`)}>
              <div className="row">
                <h3>{f.name}</h3>
                {f.is_sample ? <span className="pill gray">Sample</span> : null}
              </div>
              <p>{f.description || "No description."}</p>
              <div className="meta">
                <span>{f.version ? `v${f.version}` : "Draft"}{!f.published_version ? "" : f.published_version === f.version ? " · Published" : ` · v${f.published_version} is published`}</span>
                <span>{f.nodes || 0} block{f.nodes === 1 ? "" : "s"}</span>
                <span>{f.runs || 0} runs</span>
                <span>Last run {fmtAgo(f.last_run)}</span>
              </div>
              <div className="row" onClick={(e) => e.stopPropagation()}>
                <span className="hint">Edited {fmtAgo(f.updated_at)}</span>
                <span style={{ display: "flex", gap: 4 }}>
                  <button className="btn small ghost" onClick={() => duplicate(f.flow_id)}><Icon name="copy" />Duplicate</button>
                  {!f.is_sample ? (
                    <button className="btn small ghost danger" onClick={() => remove(f)}><Icon name="trash" />Delete</button>
                  ) : null}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
