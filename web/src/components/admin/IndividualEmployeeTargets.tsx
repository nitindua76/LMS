import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { courseTargetUsersApi, usersApi, CsvImportRowResult } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

export default function IndividualEmployeeTargets({ courseId }: { courseId: number }) {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [err, setErr] = useState("");
  const [importResults, setImportResults] = useState<CsvImportRowResult[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const key = ["course-target-users", courseId];

  const { data: targetUsers } = useQuery({
    queryKey: key,
    queryFn: () => courseTargetUsersApi.list(courseId),
  });

  const { data: matches } = useQuery({
    queryKey: ["user-search", "course-target", query],
    queryFn: () => usersApi.list({ search: query, page_size: 8, role: "employee" }),
    enabled: query.trim().length >= 2,
  });

  const addMut = useMutation({
    mutationFn: (userId: number) => courseTargetUsersApi.add(courseId, userId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: key }); setQuery(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const removeMut = useMutation({
    mutationFn: (targetUserId: number) => courseTargetUsersApi.remove(courseId, targetUserId),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const importMut = useMutation({
    mutationFn: (file: File) => courseTargetUsersApi.importCsv(courseId, file),
    onSuccess: (results) => {
      qc.invalidateQueries({ queryKey: key });
      setImportResults(results);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <h3 style={{ marginBottom: 4, fontSize: 14, fontWeight: 600 }}>Individual Employees</h3>
      <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16 }}>
        On top of the department + level targets above — add specific employees regardless of their department or level,
        one at a time or in bulk from a CSV (a single <code>email</code> column).
      </p>

      {err && <div style={{ color: "var(--danger)", fontSize: 12, marginBottom: 12 }}>{err}</div>}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        {targetUsers?.map((tu) => (
          <span key={tu.id} className="badge badge-gray" style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12 }}>
            {tu.name} <span style={{ color: "var(--text-muted)" }}>({tu.email})</span>
            <button onClick={() => removeMut.mutate(tu.id)} style={{ background: "none", border: "none", color: "var(--danger)", padding: 0, cursor: "pointer" }}>✕</button>
          </span>
        ))}
        {targetUsers?.length === 0 && (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No individually-targeted employees yet.</span>
        )}
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ position: "relative" }}>
          <input placeholder="Search employee by name/email…" value={query} onChange={(e) => setQuery(e.target.value)} style={{ width: 260 }} />
          {matches && matches.items.length > 0 && (
            <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 10, background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 4, maxHeight: 180, overflowY: "auto" }}>
              {matches.items.map((u) => (
                <div key={u.id} style={{ padding: "6px 8px", cursor: "pointer", fontSize: 12 }}
                  onClick={() => addMut.mutate(u.id)}>
                  {u.name} <span style={{ color: "var(--text-muted)" }}>({u.email})</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <label className="btn-ghost" style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", margin: 0 }}>
          {importMut.isPending ? "Importing…" : "Import CSV"}
          <input ref={fileInputRef} type="file" accept=".csv" style={{ display: "none" }}
            disabled={importMut.isPending}
            onChange={(e) => { const file = e.target.files?.[0]; if (file) importMut.mutate(file); }} />
        </label>
      </div>

      {importResults && (
        <div style={{ marginTop: 12, fontSize: 12 }}>
          <strong>{importResults.filter((r) => r.status !== "error").length} added</strong>
          {importResults.some((r) => r.status === "error") && (
            <>
              , {importResults.filter((r) => r.status === "error").length} skipped:
              <ul style={{ margin: "4px 0 0", paddingLeft: 20, color: "var(--text-muted)" }}>
                {importResults.filter((r) => r.status === "error").map((r) => (
                  <li key={r.row}>Row {r.row} ({r.email || "—"}): {r.error}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
