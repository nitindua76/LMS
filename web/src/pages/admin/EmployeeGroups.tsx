import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { employeeGroupsApi, disciplinesApi, levelsApi, RuleInput, RuleOperator, EmployeeGroupSummary } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

// Fields a rule can target, grouped by whether they need a free-text value,
// a dropdown (backed by disciplines/levels), or a CPF (the hierarchy ops).
const TEXT_FIELDS: { field: string; label: string }[] = [
  { field: "posting", label: "Posting" },
  { field: "location", label: "Location" },
  { field: "designation", label: "Designation" },
  { field: "gender", label: "Gender" },
];

const OPERATOR_LABELS: Record<RuleOperator, string> = {
  equals: "is exactly",
  contains: "contains",
  in_list: "is one of (comma-separated)",
  is_direct_report_of: "reports directly to CPF",
  is_in_subtree_of: "is anywhere under CPF in the reporting chain",
};

function emptyRule(): RuleInput {
  return { field: "discipline_id", operator: "equals", value: "" };
}

function RuleEditor({
  rule, onChange, onRemove, disciplines, levels,
}: {
  rule: RuleInput;
  onChange: (r: RuleInput) => void;
  onRemove: () => void;
  disciplines: { id: number; name: string }[];
  levels: { id: number; code: string; name: string }[];
}) {
  const isHierarchyOp = rule.operator === "is_direct_report_of" || rule.operator === "is_in_subtree_of";
  const kind = isHierarchyOp ? "hierarchy" : rule.field === "discipline_id" ? "discipline"
    : rule.field === "level_id" ? "level" : "text";

  return (
    <div className="rule-row">
      <select
        value={isHierarchyOp ? "__hierarchy__" : rule.field}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "__hierarchy__") {
            onChange({ field: "", operator: "is_direct_report_of", value: rule.value });
          } else {
            onChange({ field: v, operator: "equals", value: "" });
          }
        }}
      >
        <option value="discipline_id">Department</option>
        <option value="level_id">Level</option>
        {TEXT_FIELDS.map((f) => <option key={f.field} value={f.field}>{f.label}</option>)}
        <option value="__hierarchy__">Reporting hierarchy</option>
      </select>

      {kind === "hierarchy" ? (
        <>
          <select value={rule.operator} onChange={(e) => onChange({ ...rule, operator: e.target.value as RuleOperator })}>
            <option value="is_direct_report_of">{OPERATOR_LABELS.is_direct_report_of}</option>
            <option value="is_in_subtree_of">{OPERATOR_LABELS.is_in_subtree_of}</option>
          </select>
          <input
            placeholder="CPF number, e.g. 55257"
            value={rule.value}
            onChange={(e) => onChange({ ...rule, value: e.target.value })}
            style={{ width: 160 }}
          />
        </>
      ) : kind === "discipline" ? (
        <select value={rule.value} onChange={(e) => onChange({ ...rule, operator: "equals", value: e.target.value })}>
          <option value="" disabled>Choose department…</option>
          {disciplines.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      ) : kind === "level" ? (
        <select value={rule.value} onChange={(e) => onChange({ ...rule, operator: "equals", value: e.target.value })}>
          <option value="" disabled>Choose level…</option>
          {levels.map((l) => <option key={l.id} value={l.id}>{l.code} ({l.name})</option>)}
        </select>
      ) : (
        <>
          <select value={rule.operator} onChange={(e) => onChange({ ...rule, operator: e.target.value as RuleOperator })}>
            <option value="equals">{OPERATOR_LABELS.equals}</option>
            <option value="contains">{OPERATOR_LABELS.contains}</option>
            <option value="in_list">{OPERATOR_LABELS.in_list}</option>
          </select>
          <input
            placeholder="Value…"
            value={rule.value}
            onChange={(e) => onChange({ ...rule, value: e.target.value })}
            style={{ width: 200 }}
          />
        </>
      )}

      <button className="btn-ghost" style={{ padding: "4px 8px" }} onClick={onRemove} title="Remove this condition">✕</button>
    </div>
  );
}

function GroupBuilder({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rules, setRules] = useState<RuleInput[]>([emptyRule()]);
  const [err, setErr] = useState("");
  const { data: disciplines } = useQuery({ queryKey: ["disciplines"], queryFn: () => disciplinesApi.list() });
  const { data: levels } = useQuery({ queryKey: ["levels"], queryFn: () => levelsApi.list() });

  const validRules = rules.filter((r) => r.value.trim() !== "");

  const previewQuery = useQuery({
    queryKey: ["employee-group-preview", JSON.stringify(validRules)],
    queryFn: () => employeeGroupsApi.preview(validRules),
    enabled: validRules.length > 0,
  });

  const createMut = useMutation({
    mutationFn: () => employeeGroupsApi.create({ name: name.trim(), description: description.trim() || undefined, rules: validRules }),
    onSuccess: () => {
      setName(""); setDescription(""); setRules([emptyRule()]); setErr("");
      onCreated();
    },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <h3 style={{ marginBottom: 4, fontSize: 14, fontWeight: 600 }}>Create a Group</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 16, maxWidth: 640, lineHeight: 1.5 }}>
        Membership is calculated live from every employee's current department, level, and reporting hierarchy —
        never a fixed list. New hires and transfers are picked up automatically; nothing to keep in sync.
        Conditions below are all required together (AND).
      </p>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
        <div className="form-group" style={{ margin: 0, flex: 1, minWidth: 220 }}>
          <label>Group name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. GEOPIC Level 3 and above" />
        </div>
        <div className="form-group" style={{ margin: 0, flex: 2, minWidth: 280 }}>
          <label>Description (optional)</label>
          <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What is this group for?" />
        </div>
      </div>

      <div className="rule-list">
        {rules.map((rule, i) => (
          <RuleEditor
            key={i}
            rule={rule}
            onChange={(r) => setRules((prev) => prev.map((p, idx) => (idx === i ? r : p)))}
            onRemove={() => setRules((prev) => prev.filter((_, idx) => idx !== i))}
            disciplines={disciplines?.items ?? []}
            levels={levels?.items ?? []}
          />
        ))}
      </div>
      <button className="btn-ghost" style={{ padding: "4px 10px", fontSize: 12, marginTop: 4 }}
        onClick={() => setRules((prev) => [...prev, emptyRule()])}>
        + Add condition
      </button>

      <div className="group-preview-pill">
        {validRules.length === 0 ? (
          <span style={{ color: "var(--text-muted)" }}>Add at least one condition to see who matches.</span>
        ) : previewQuery.isFetching ? (
          <span style={{ color: "var(--text-muted)" }}>Calculating…</span>
        ) : previewQuery.data ? (
          <>
            <strong>{previewQuery.data.total}</strong> employee{previewQuery.data.total === 1 ? "" : "s"} currently match
            {previewQuery.data.sample.length > 0 && (
              <span style={{ color: "var(--text-muted)" }}>
                {" "}— {previewQuery.data.sample.slice(0, 5).map((m) => m.name).join(", ")}
                {previewQuery.data.total > 5 ? ", …" : ""}
              </span>
            )}
          </>
        ) : null}
      </div>

      {err && <p className="error-msg" style={{ marginTop: 10 }}>{err}</p>}
      <button
        className="btn-primary"
        style={{ marginTop: 12 }}
        disabled={!name.trim() || validRules.length === 0 || createMut.isPending}
        onClick={() => createMut.mutate()}
      >
        {createMut.isPending ? "Creating…" : "Create Group"}
      </button>
    </div>
  );
}

export default function EmployeeGroups() {
  const qc = useQueryClient();
  const [err, setErr] = useState("");

  const { data: groups, isLoading } = useQuery({
    queryKey: ["employee-groups"],
    queryFn: () => employeeGroupsApi.list(),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => employeeGroupsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["employee-groups"] }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div>
      <div className="page-header">
        <h1>Employee Groups</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
          Rule-based groups you can target courses and live sessions at — membership updates automatically as employees join, transfer, or leave.
        </p>
      </div>

      {err && <p className="error-msg" style={{ marginBottom: 16 }}>{err}</p>}

      <GroupBuilder onCreated={() => qc.invalidateQueries({ queryKey: ["employee-groups"] })} />

      <div className="card">
        <h3 style={{ marginBottom: 12, fontSize: 14, fontWeight: 600 }}>Existing Groups</h3>
        {isLoading ? (
          <div className="center"><div className="spinner" /></div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Conditions</th>
                  <th>Members</th>
                  <th style={{ width: 80 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {groups?.map((g: EmployeeGroupSummary) => (
                  <tr key={g.id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{g.name}</div>
                      {g.description && <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{g.description}</div>}
                    </td>
                    <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{g.rule_count}</td>
                    <td>
                      <span className="badge badge-green">{g.member_count}</span>
                    </td>
                    <td>
                      <button className="btn-danger" style={{ padding: "4px 10px" }}
                        onClick={() => { if (confirm(`Delete "${g.name}"? Courses/sessions targeting it will stop including its members.`)) deleteMut.mutate(g.id); }}>
                        Del
                      </button>
                    </td>
                  </tr>
                ))}
                {groups?.length === 0 && (
                  <tr><td colSpan={4} style={{ color: "var(--text-muted)", textAlign: "center" }}>No groups yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
