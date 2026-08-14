import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { employeeGroupsApi } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

export default function GroupTargets({ courseId }: { courseId: number }) {
  const qc = useQueryClient();
  const [err, setErr] = useState("");
  const [selectedGroupId, setSelectedGroupId] = useState<number | "">("");
  const key = ["course-target-groups", courseId];

  const { data: targetGroups } = useQuery({
    queryKey: key,
    queryFn: () => employeeGroupsApi.listCourseTargets(courseId),
  });

  const { data: allGroups } = useQuery({
    queryKey: ["employee-groups"],
    queryFn: () => employeeGroupsApi.list(),
  });

  const addMut = useMutation({
    mutationFn: (groupId: number) => employeeGroupsApi.addCourseTarget(courseId, groupId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: key }); setSelectedGroupId(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const removeMut = useMutation({
    mutationFn: (targetGroupId: number) => employeeGroupsApi.removeCourseTarget(courseId, targetGroupId),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const targetedIds = new Set((targetGroups ?? []).map((t) => t.group_id));
  const availableGroups = (allGroups ?? []).filter((g) => !targetedIds.has(g.id));

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <h3 style={{ marginBottom: 4, fontSize: 14, fontWeight: 600 }}>Employee Groups</h3>
      <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16 }}>
        On top of department + level targets and individually-added employees — target a whole{" "}
        <a href="/admin/employee-groups" target="_blank" rel="noreferrer">dynamic group</a>. Membership
        (and therefore who sees this course) updates automatically as people join, transfer, or leave.
      </p>

      {err && <div style={{ color: "var(--danger)", fontSize: 12, marginBottom: 12 }}>{err}</div>}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        {targetGroups?.map((tg) => (
          <span key={tg.id} className="badge badge-gray" style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12 }}>
            {tg.group_name} <span style={{ color: "var(--text-muted)" }}>({tg.member_count} member{tg.member_count === 1 ? "" : "s"})</span>
            <button onClick={() => removeMut.mutate(tg.id)} style={{ background: "none", border: "none", color: "var(--danger)", padding: 0, cursor: "pointer" }}>✕</button>
          </span>
        ))}
        {targetGroups?.length === 0 && (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No groups targeted yet.</span>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <select
          value={selectedGroupId}
          onChange={(e) => setSelectedGroupId(e.target.value ? Number(e.target.value) : "")}
          style={{ minWidth: 220 }}
        >
          <option value="" disabled>Choose a group to add…</option>
          {availableGroups.map((g) => (
            <option key={g.id} value={g.id}>{g.name} ({g.member_count})</option>
          ))}
        </select>
        <button
          className="btn-primary"
          style={{ padding: "6px 14px" }}
          disabled={!selectedGroupId || addMut.isPending}
          onClick={() => selectedGroupId && addMut.mutate(selectedGroupId)}
        >
          Add
        </button>
      </div>
      {availableGroups.length === 0 && allGroups && allGroups.length > 0 && (
        <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 8 }}>All existing groups are already targeted at this course.</p>
      )}
      {allGroups && allGroups.length === 0 && (
        <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 8 }}>
          No groups exist yet — create one on the <a href="/admin/employee-groups" target="_blank" rel="noreferrer">Employee Groups</a> page.
        </p>
      )}
    </div>
  );
}
