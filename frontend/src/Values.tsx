import { useState } from "react";
import { placeholder, showValue, ValueInput, VALUE_TYPES, ValueType } from "./lib";
import { Icon } from "./ui";

// ---------------------------------------------------------------- declaring inputs (builder)

function NameField({ value, onCommit }: { value: string; onCommit: (name: string) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => { if (draft !== null && draft.trim() !== value) onCommit(draft.trim().replace(/[{}]/g, "")); setDraft(null); };
  return (
    <input className="input" aria-label="Input name" placeholder="Name, for example Tolerance" value={draft ?? value}
      onChange={(e) => setDraft(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

/** The flow's value inputs. Renaming one also renames it where prompts and rules use it (through `onRename`). */
export function InputsEditor({ inputs, onChange, onRename, unused }: {
  inputs: ValueInput[]; onChange: (inputs: ValueInput[]) => void; onRename: (from: string, to: string) => void; unused: Set<string>;
}) {
  const set = (i: number, patch: Partial<ValueInput>) => onChange(inputs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const add = () => {
    let n = inputs.length + 1;
    while (inputs.some((x) => x.name === `Input ${n}`)) n += 1;
    onChange([...inputs, { name: `Input ${n}`, type: "text", default: null, description: "" }]);
  };
  return (
    <div className="field">
      <span className="label">Inputs</span>
      <p className="hint">Values a caller sends with the files, such as a number, a choice or a short text. Write <code>{"{{Name}}"}</code> in a prompt or a filter rule to use one.</p>
      {inputs.map((inp, i) => (
        <div className="vin" key={i}>
          <div className="vin-head">
            <NameField value={inp.name} onCommit={(name) => { onRename(inp.name, name); set(i, { name }); }} />
            <button className="icon-btn" aria-label={`Remove input ${inp.name}`} onClick={() => onChange(inputs.filter((_, j) => j !== i))}><Icon name="x" /></button>
          </div>
          {inp.type === "choice" ? (
            <input className="input" aria-label="Choices" placeholder="Choices, separated by commas" defaultValue={(inp.choices || []).join(", ")}
              onBlur={(e) => set(i, { choices: e.target.value.split(",").map((c) => c.trim()).filter(Boolean) })} />
          ) : null}
          <div className="vin-default">
            <span>Type</span>
            <select className="select" aria-label="Type" value={inp.type}
              onChange={(e) => set(i, { type: e.target.value as ValueType, default: null })}>
              {VALUE_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </select>
          </div>
          <div className="vin-default">
            <span>Default</span>
            <ValueField input={inp} value={inp.default ?? ""} onChange={(v) => set(i, { default: v === "" ? null : v })} bare allowNone />
          </div>
          <input className="input" aria-label="Description" placeholder="What it is for (shown to the person running the flow)" value={inp.description || ""}
            onChange={(e) => set(i, { description: e.target.value })} />
          <p className="hint">
            {inp.default === null || inp.default === undefined || inp.default === "" ? "No default: every run must supply it." : "Used when a run does not supply it."}
            {inp.name && unused.has(inp.name) ? <span style={{ color: "var(--warn-text)" }}> Not used by any step yet.</span> : null}
          </p>
        </div>
      ))}
      <button className="btn small" style={{ alignSelf: "flex-start" }} onClick={add}><Icon name="plus" />Add an input</button>
    </div>
  );
}

// ---------------------------------------------------------------- supplying values (test run, activity)

export type Values = Record<string, string | boolean>;

/** One control for one input. The value is kept as typed; the server checks and converts it. */
export function ValueField({ input, value, onChange, bare, allowNone }: {
  input: ValueInput; value: unknown; onChange: (v: string | boolean) => void; bare?: boolean; allowNone?: boolean;
}) {
  const id = `v-${input.name.replace(/\W+/g, "-")}${bare ? "-d" : ""}`;
  const hasDefault = input.default !== null && input.default !== undefined && input.default !== "";
  const hint = hasDefault ? `Default: ${showValue(input.default)}` : "Required";
  let control;
  if (input.type === "yesno") {
    const cur = value === true || value === "yes" ? true : value === false || value === "no" ? false : null;
    control = (
      <div className="seg" role="group" aria-label={input.name}>
        <button aria-pressed={cur === true} onClick={() => onChange(true)}>Yes</button>
        <button aria-pressed={cur === false} onClick={() => onChange(false)}>No</button>
        {allowNone ? <button aria-pressed={cur === null} onClick={() => onChange("")}>None</button> : null}
      </div>
    );
  } else if (input.type === "choice") {
    control = (
      <select id={id} className="select" aria-label={bare ? "Default" : undefined} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
        <option value="">{bare ? "None" : hasDefault ? `Default (${showValue(input.default)})` : "Choose"}</option>
        {(input.choices || []).map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    );
  } else if (input.type === "json") {
    const text = typeof value === "string" ? value : value === null || value === undefined ? "" : JSON.stringify(value, null, 1);
    let bad = false;
    if (text.trim()) { try { JSON.parse(text); } catch { bad = true; } }
    control = (
      <>
        <textarea id={id} className="input mono" aria-label={bare ? "Default" : undefined} rows={bare ? 2 : 4} style={{ height: "auto", padding: "8px 10px", fontSize: 12, resize: "vertical" }}
          placeholder={bare ? "None" : hasDefault ? showValue(input.default) : '{"key": "value"}'} value={text} onChange={(e) => onChange(e.target.value)} />
        {bad ? <p className="hint" style={{ color: "var(--warn-text)" }}>This is not valid JSON yet.</p> : null}
      </>
    );
  } else {
    control = (
      <input id={id} className="input" aria-label={bare ? "Default" : undefined} type={input.type === "number" ? "number" : "text"} step="any"
        placeholder={bare ? "None" : hasDefault ? showValue(input.default) : ""} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
    );
  }
  if (bare) return control;
  return (
    <div className="field">
      <label htmlFor={id}>{input.name} <span className="vhint">{hint}</span></label>
      {control}
      {input.description ? <p className="hint">{input.description}</p> : null}
    </div>
  );
}

export function ValuesForm({ inputs, values, onChange }: { inputs: ValueInput[]; values: Values; onChange: (v: Values) => void }) {
  if (!inputs.length) return null;
  return (
    <div className="vform">
      <span className="label">Values</span>
      {inputs.map((inp) => (
        <ValueField key={inp.name} input={inp} value={values[inp.name] ?? ""} onChange={(v) => onChange({ ...values, [inp.name]: v })} />
      ))}
    </div>
  );
}

/** What to send: only what was filled in, so defaults apply to the rest. */
export function valuesToSend(inputs: ValueInput[], values: Values): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  for (const inp of inputs) {
    const v = values[inp.name];
    if (v === undefined || v === "") continue;
    out[inp.name] = v;
  }
  return out;
}

/** The names of required inputs that have no value yet. */
export function missingValues(inputs: ValueInput[], values: Values): string[] {
  return inputs.filter((i) => (i.default === null || i.default === undefined || i.default === "") && (values[i.name] === undefined || values[i.name] === ""))
    .map((i) => i.name);
}

export function loadValues(flowId: string): Values {
  try { return JSON.parse(localStorage.getItem(`values:${flowId}`) || "{}"); } catch { return {}; }
}
export function saveValues(flowId: string, v: Values) {
  try { localStorage.setItem(`values:${flowId}`, JSON.stringify(v)); } catch { /* storage may be unavailable */ }
}

export { placeholder };
