import { useEffect, useState } from "react";
import { api, Doc, docSize, fmtAgo, fmtBytes, UPLOAD_ACCEPT, useInterval } from "./lib";
import { Icon, toast, TopBar } from "./ui";

const KIND = { pdf: "PDF", image: "Image", text: "Text" } as const;

/** Every file the engine holds: upload one, or remove one that was uploaded. */
export default function Files() {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api<Doc[]>("/api/documents?all=true").then((d) => setDocs([...d.filter((x) => !x.is_sample), ...d.filter((x) => x.is_sample)])).catch((e) => toast(e.message, true));
  useEffect(() => {
    load();
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useInterval(load, 5000);      // a file in use becomes removable when its run ends

  const upload = async (files: FileList) => {
    setBusy(true);
    for (const file of Array.from(files)) {
      try {
        const d = await api<Doc>(`/api/documents?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file, headers: { "Content-Type": "application/octet-stream" } });
        toast(d.reused ? `${d.name} is already here (${docSize(d)})` : `${d.name} uploaded (${docSize(d)})`);
      } catch (e: any) { toast(`${file.name}: ${e.message}`, true); }
    }
    setBusy(false);
    load();
  };
  const remove = async (d: Doc) => {
    const used = d.jobs ? ` ${d.jobs} past run${d.jobs === 1 ? "" : "s"} used it: their results stay, but their page views of this file will stop working.` : "";
    if (!window.confirm(`Remove "${d.name}"?${used} This cannot be undone.`)) return;
    try {
      await api(`/api/documents/${d.document_id}`, { method: "DELETE" });
      toast(`${d.name} removed`);
    } catch (e: any) { toast(e.message, true); }
    load();
  };

  const uploaded = (docs || []).filter((d) => !d.is_sample).length;
  return (
    <div className="screen">
      <TopBar crumbs={<span>Document Engine</span>} title={<h1>Files</h1>}>
        <label className="btn primary">
          <Icon name="upload" />{busy ? "Uploading…" : "Upload files"}
          <input type="file" multiple title="PDFs, images or text files" accept={UPLOAD_ACCEPT} className="sr" disabled={busy}
            onChange={(e) => { if (e.target.files?.length) upload(e.target.files); e.target.value = ""; }} />
        </label>
      </TopBar>
      <div className="page">
        <div className="page-head">
          <div>
            <h1>Files</h1>
            <p>The PDFs, images and text files that flows can be tested and run on. A file is chosen on a source block
              in a flow, or when a run is started. Files marked API were sent by a caller of the public endpoint; they are
              listed here only. Sample files come with the engine and cannot be removed.</p>
          </div>
        </div>
        {docs === null ? <p className="empty">Loading files…</p> : null}
        {docs && docs.length === 0 ? <p className="empty">No files yet. Upload one to get started.</p> : null}
        {docs && docs.length ? (
          <table className="table">
            <thead><tr><th>Name</th><th>Type</th><th>Pages</th><th>Size</th><th>Uploaded</th><th>Used in</th><th /></tr></thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.document_id}>
                  <td style={{ overflowWrap: "anywhere" }}>{d.name}{d.is_sample ? <span className="pill gray" style={{ marginLeft: 8 }}>Sample</span> : null}{d.via_api ? <span className="pill gray" style={{ marginLeft: 8 }} title="Sent by a caller of the public endpoint">API</span> : null}</td>
                  <td>{KIND[d.kind || "pdf"]}</td>
                  <td>{d.pages}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{fmtBytes(d.size_bytes)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{d.is_sample ? "" : fmtAgo(d.created_at)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{d.jobs ? `${d.jobs} run${d.jobs === 1 ? "" : "s"}${d.active ? `, ${d.active} not finished` : ""}` : "No runs"}</td>
                  <td style={{ textAlign: "right" }}>
                    {!d.is_sample ? (
                      <button className="btn small ghost danger" disabled={!!d.active} title={d.active ? "In use by a run that has not finished" : ""}
                        aria-label={`Remove ${d.name}`} onClick={() => remove(d)}><Icon name="trash" />Remove</button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {docs && docs.length && !uploaded ? <p className="empty" style={{ marginTop: 16 }}>Only the sample files so far. Files you upload appear here.</p> : null}
      </div>
    </div>
  );
}
