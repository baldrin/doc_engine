import { useEffect, useState } from "react";
import { api, ApiError, Flow } from "./lib";
import { Icon, Modal, toast } from "./ui";

interface Contract {
  name: string; flow_id: string; version: number; description: string;
  files: { name: string }[];
  values: { name: string; type: string; required: boolean; default: unknown; choices?: string[]; description: string }[];
  outputs: { name: string; format: string }[];
}
const TYPE: Record<string, string> = { text: "Text", number: "Number", choice: "Choice", yesno: "Yes or no", json: "JSON" };

/** The flow's name as it can be written in an address: "Contract file review" -> contract-file-review. */
export function flowSlug(name: string): string {
  // As the server matches names: letters and digits of any script, everything else a separator.
  return name.normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "");
}
const fileName = (input: string) => (flowSlug(input) || "file") + ".pdf";
const example = (v: Contract["values"][number]): unknown =>
  v.default ?? (v.type === "number" ? 1 : v.type === "yesno" ? true : v.type === "choice" ? v.choices?.[0] ?? "" : v.type === "json" ? {} : "…");
const sh = (s: string) => `'${s.replace(/'/g, `'\\''`)}'`;

function Code({ text, label }: { text: string; label: string }) {
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); toast("Copied"); } catch { toast("Could not copy. Select the text instead.", true); }
  };
  return (
    <div className="code-box">
      <div className="code-head"><span>{label}</span><button className="btn small ghost" onClick={copy}><Icon name="copy" />Copy</button></div>
      <pre>{text}</pre>
    </div>
  );
}

/** How to run the published version of a flow from code: what it needs and commands to copy. */
export default function ApiPanel({ flow, dirty, onClose, onUnpublished }: {
  flow: Flow; dirty: boolean; onClose: () => void; onUnpublished: (f: Flow) => void;
}) {
  const [c, setC] = useState<Contract | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "none">("loading");
  useEffect(() => {
    api<Contract>(`/api/v1/flows/${flow.flow_id}`).then((r) => { setC(r); setState("ok"); })
      .catch((e) => { if (!(e instanceof ApiError)) toast(e.message, true); setState("none"); });
  }, [flow.flow_id, flow.published_version]);

  const unpublish = async () => {
    if (!window.confirm(`Unpublish "${flow.name}"? Callers will no longer be able to start it. Jobs already started carry on.`)) return;
    try { onUnpublished(await api<Flow>(`/api/flows/${flow.flow_id}/unpublish`, { method: "POST" })); toast("Unpublished"); }
    catch (e: any) { toast(e.message, true); }
  };

  const origin = window.location.origin;
  let body = null;
  if (state === "loading") body = <p className="hint">Loading…</p>;
  else if (state === "none" || !c) {
    body = <p className="hint">This flow is not published, so it cannot be run from code yet. Choose <strong>Publish</strong> in the
      top bar. Publishing makes the flow as it is now available under its name.</p>;
  } else {
    const url = `${origin}/api/v1/flows/${encodeURI(flowSlug(c.name)) || c.flow_id}/jobs`;
    const vals = Object.fromEntries(c.values.map((v) => [v.name, example(v)]));
    const submit = [`curl -X POST ${sh(url)}`,
      ...c.files.map((f) => `  -F ${sh(`${c.files.length === 1 ? "file" : f.name}=@${fileName(f.name)}`)}`),
      ...(c.values.length ? [`  -F ${sh(`values=${JSON.stringify(vals)}`)}`] : [])].join(" \\\n");
    const stale = dirty || flow.version !== flow.published_version;
    body = (
      <>
        <p className="hint">Callers run <strong>version {c.version}</strong> of this flow by its name{c.name !== flow.name ? <>, which is still <strong>{c.name}</strong> until you publish again</> : null}.
          {stale ? " Changes made since then are not live until you publish again." : " It matches what is on the canvas."}</p>
        <div className="api-needs">
          <div><span className="caps">Files</span>
            {c.files.map((f) => <div key={f.name} className="api-row"><strong>{f.name}</strong><span>a PDF, an image or a text file</span></div>)}
          </div>
          <div><span className="caps">Values</span>
            {c.values.length === 0 ? <div className="api-row"><span>None</span></div> : null}
            {c.values.map((v) => (
              <div key={v.name} className="api-row"><strong>{v.name}</strong>
                <span>{TYPE[v.type] || v.type}{v.choices?.length ? `: ${v.choices.join(", ")}` : ""} · {v.required ? "required" : `default ${typeof v.default === "boolean" ? (v.default ? "yes" : "no") : JSON.stringify(v.default)}`}</span></div>
            ))}
          </div>
        </div>
        <Code label="1. Start a job. The reply holds the job id." text={submit} />
        <Code label="2. Check its status until it is done." text={`curl ${sh(`${origin}/api/v1/jobs/JOB_ID`)}`} />
        <Code label="3. Fetch the results." text={`curl ${sh(`${origin}/api/v1/jobs/JOB_ID/results`)}`} />
        <p className="hint">Replace the file names with your own files and JOB_ID with the id from step 1. A file already stored can be
          sent by its id instead. The full reference is in <code>docs/api</code> in the repository.</p>
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button className="btn danger" onClick={unpublish}>Unpublish</button>
        </div>
      </>
    );
  }
  return <Modal title={`Run "${flow.name}" from code`} onClose={onClose} wide>{body}</Modal>;
}
