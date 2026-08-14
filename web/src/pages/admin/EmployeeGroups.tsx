import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  employeeGroupsApi, disciplinesApi, levelsApi,
  RuleInput, RuleOperator, GroupMatchType, EmployeeGroupSummary, EmployeeGroup,
} from "../../api/admin";
import { getErrorMessage } from "../../api/client";

// Fields a rule can target, grouped by whether they need a free-text value,
// a dropdown (backed by disciplines/levels), or a CPF (the hierarchy ops).
const TEXT_FIELDS: { field: string; label: string }[] = [
  { field: "name", label: "Name" },
  { field: "email", label: "Email" },
  { field: "cpf", label: "CPF number" },
  { field: "posting", label: "Posting" },
  { field: "location", label: "Location" },
  { field: "designation", label: "Designation" },
  { field: "gender", label: "Gender" },
];

const OPERATOR_LABELS: Record<RuleOperator, string> = {
  equals: "is exactly",
  not_equals: "is not",
  contains: "contains",
  not_contains: "does not contain",
  in_list: "is one of (comma-separated)",
  is_empty: "is empty / not set",
  is_not_empty: "is set (any value)",
  is_direct_report_of: "reports directly to CPF",
  is_in_subtree_of: "is anywhere under CPF in the reporting chain",
};

// Operators that don't need a value input at all.
const VALUELESS_OPERATORS: RuleOperator[] = ["is_empty", "is_not_empty"];

const TEXT_OPERATORS: RuleOperator[] = ["equals", "not_equals", "contains", "not_contains", "in_list", "is_empty", "is_not_empty"];
const DROPDOWN_OPERATORS: RuleOperator[] = ["equals", "not_equals", "is_empty", "is_not_empty"];

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
  const needsValue = !VALUELESS_OPERATORS.includes(rule.operator);

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
        <>
          <select value={rule.operator} onChange={(e) => onChange({ ...rule, operator: e.target.value as RuleOperator })}>
            {DROPDOWN_OPERATORS.map((op) => <option key={op} value={op}>{OPERATOR_LABELS[op]}</option>)}
          </select>
          {needsValue && (
            <select value={rule.value} onChange={(e) => onChange({ ...rule, value: e.target.value })}>
              <option value="" disabled>Choose department…</option>
              {disciplines.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          )}
        </>
      ) : kind === "level" ? (
        <>
          <select value={rule.operator} onChange={(e) => onChange({ ...rule, operator: e.target.value as RuleOperator })}>
            {DROPDOWN_OPERATORS.map((op) => <option key={op} value={op}>{OPERATOR_LABELS[op]}</option>)}
          </select>
          {needsValue && (
            <select value={rule.value} onChange={(e) => onChange({ ...rule, value: e.target.value })}>
              <option value="" disabled>Choose level…</option>
              {levels.map((l) => <option key={l.id} value={l.id}>{l.code} ({l.name})</option>)}
            </select>
          )}
        </>
      ) : (
        <>
          <select value={rule.operator} onChange={(e) => onChange({ ...rule, operator: e.target.value as RuleOperator })}>
            {TEXT_OPERATORS.map((op) => <option key={op} value={op}>{OPERATOR_LABELS[op]}</option>)}
          </select>
          {needsValue && (
            <input
              placeholder="Value…"
              value={rule.value}
              onChange={(e) => onChange({ ...rule, value: e.target.value })}
              style={{ width: 200 }}
            />
          )}
        </>
      )}

      <button className="btn-ghost" style={{ padding: "4px 8px" }} onClick={onRemove} title="Remove this condition">✕</button>
    </div>
  );
}

function MatchTypeToggle({ value, onChange }: { value: GroupMatchType; onChange: (v: GroupMatchType) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
      <span style={{ fontSize: 12.5, color: "var(--text-muted)" }}>Conditions must match:</span>
      <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
        <button
          type="button"
          onClick={() => onChange("all")}
          className={value === "all" ? "btn-primary" : "btn-ghost"}
          style={{ padding: "5px 12px", fontSize: 12, borderRadius: 0 }}
        >
          All (AND)
        </button>
        <button
          type="button"
          onClick={() => onChange("any")}
          className={value === "any" ? "btn-primary" : "btn-ghost"}
          style={{ padding: "5px 12px", fontSize: 12, borderRadius: 0 }}
        >
          Any (OR)
        </button>
      </div>
    </div>
  );
}

function GroupBuilder({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [matchType, setMatchType] = useState<GroupMatchType>("all");
  const [rules, setRules] = useState<RuleInput[]>([emptyRule()]);
  const [err, setErr] = useState("");
  const { data: disciplines } = useQuery({ queryKey: ["disciplines"], queryFn: () => disciplinesApi.list() });
  const { data: levels } = useQuery({ queryKey: ["levels"], queryFn: () => levelsApi.list() });

  const validRules = rules.filter((r) => VALUELESS_OPERATORS.includes(r.operator) || r.value.trim() !== "");

  const previewQuery = useQuery({
    queryKey: ["employee-group-preview", JSON.stringify(validRules), matchType],
    queryFn: () => employeeGroupsApi.preview(validRules, matchType),
    enabled: validRules.length > 0,
  });

  const createMut = useMutation({
    mutationFn: () => employeeGroupsApi.create({
      name: name.trim(), description: description.trim() || undefined, match_type: matchType, rules: validRules,
    }),
    onSuccess: () => {
      setName(""); setDescription(""); setMatchType("all"); setRules([emptyRule()]); setErr("");
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

      <MatchTypeToggle value={matchType} onChange={setMatchType} />

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

function GroupRulesEditor({ group, onClose }: { group: EmployeeGroup; onClose: () => void }) {
  const qc = useQueryClient();
  const [matchType, setMatchType] = useState<GroupMatchType>(group.match_type);
  const [rules, setRules] = useState<RuleInput[]>(
    group.rules.length > 0 ? group.rules.map((r) => ({ field: r.field, operator: r.operator, value: r.value })) : [emptyRule()]
  );
  const [err, setErr] = useState("");
  const { data: disciplines } = useQuery({ queryKey: ["disciplines"], queryFn: () => disciplinesApi.list() });
  const { data: levels } = useQuery({ queryKey: ["levels"], queryFn: () => levelsApi.list() });

  const validRules = rules.filter((r) => VALUELESS_OPERATORS.includes(r.operator) || r.value.trim() !== "");

  const previewQuery = useQuery({
    queryKey: ["employee-group-preview", JSON.stringify(validRules), matchType],
    queryFn: () => employeeGroupsApi.preview(validRules, matchType),
    enabled: validRules.length > 0,
  });

  const saveMut = useMutation({
    mutationFn: () => employeeGroupsApi.replaceRules(group.id, validRules, matchType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["employee-groups"] });
      onClose();
    },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
      <MatchTypeToggle value={matchType} onChange={setMatchType} />
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
            <strong>{previewQuery.data.total}</strong> employee{previewQuery.data.total === 1 ? "" : "s"} would match
          </>
        ) : null}
      </div>

      {err && <p className="error-msg" style={{ marginTop: 10 }}>{err}</p>}
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button className="btn-primary" disabled={validRules.length === 0 || saveMut.isPending} onClick={() => saveMut.mutate()}>
          {saveMut.isPending ? "Saving…" : "Save changes"}
        </button>
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}

function GroupMembersModal({ groupId, groupName, onClose }: { groupId: number; groupName: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["employee-group-members", groupId],
    queryFn: () => employeeGroupsApi.members(groupId),
  });

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}
      onClick={onClose}
    >
      <div className="card" style={{ maxWidth: 520, width: "90%", maxHeight: "80vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600 }}>
            {groupName} — {data ? `${data.total} member${data.total === 1 ? "" : "s"}` : "Members"}
          </h3>
          <button className="btn-ghost" style={{ padding: "2px 8px" }} onClick={onClose}>✕</button>
        </div>
        {isLoading ? (
          <div className="center"><div className="spinner" /></div>
        ) : !data || data.members.length === 0 ? (
          <p style={{ fontSize: 12.5, color: "var(--text-muted)" }}>Nobody currently matches this group's conditions.</p>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr><th>Name</th><th>Email</th><th>CPF</th><th>Designation</th></tr>
              </thead>
              <tbody>
                {data.members.map((m) => (
                  <tr key={m.id}>
                    <td>{m.name}</td>
                    <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{m.email}</td>
                    <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{m.cpf ?? "—"}</td>
                    <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{m.designation ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function EmployeeGroups() {
  const qc = useQueryClient();
  const [err, setErr] = useState("");
  const [editingGroupId, setEditingGroupId] = useState<number | null>(null);
  const [viewingMembersOf, setViewingMembersOf] = useState<{ id: number; name: string } | null>(null);

  const { data: groups, isLoading } = useQuery({
    queryKey: ["employee-groups"],
    queryFn: () => employeeGroupsApi.list(),
  });

  const { data: editingGroup } = useQuery({
    queryKey: ["employee-group", editingGroupId],
    queryFn: () => employeeGroupsApi.get(editingGroupId!),
    enabled: editingGroupId !== null,
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
                  <th>Match</th>
                  <th>Conditions</th>
                  <th>Members</th>
                  <th style={{ width: 200 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {groups?.map((g: EmployeeGroupSummary) => (
                  <>
                    <tr key={g.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{g.name}</div>
                        {g.description && <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{g.description}</div>}
                      </td>
                      <td><span className="badge badge-gray" style={{ fontSize: 10 }}>{g.match_type === "any" ? "ANY" : "ALL"}</span></td>
                      <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{g.rule_count}</td>
                      <td>
                        <button
                          className="badge badge-green"
                          style={{ border: "none", cursor: "pointer" }}
                          onClick={() => setViewingMembersOf({ id: g.id, name: g.name })}
                          title="View members"
                        >
                          {g.member_count}
                        </button>
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: 6 }}>
                          <button className="btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
                            onClick={() => setEditingGroupId(editingGroupId === g.id ? null : g.id)}>
                            {editingGroupId === g.id ? "Close" : "Edit rules"}
                          </button>
                          <button className="btn-danger" style={{ padding: "4px 10px", fontSize: 12 }}
                            onClick={() => { if (confirm(`Delete "${g.name}"? Courses/sessions targeting it will stop including its members.`)) deleteMut.mutate(g.id); }}>
                            Del
                          </button>
                        </div>
                      </td>
                    </tr>
                    {editingGroupId === g.id && editingGroup && editingGroup.id === g.id && (
                      <tr>
                        <td colSpan={5}>
                          <GroupRulesEditor group={editingGroup} onClose={() => setEditingGroupId(null)} />
                        </td>
                      </tr>
                    )}
                  </>
                ))}
                {groups?.length === 0 && (
                  <tr><td colSpan={5} style={{ color: "var(--text-muted)", textAlign: "center" }}>No groups yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {viewingMembersOf && (
        <GroupMembersModal
          groupId={viewingMembersOf.id}
          groupName={viewingMembersOf.name}
          onClose={() => setViewingMembersOf(null)}
        />
      )}
    </div>
  );
}
