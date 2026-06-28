import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { disciplinesApi, Discipline } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

export default function Disciplines() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [err, setErr] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["disciplines"],
    queryFn: () => disciplinesApi.list(),
  });

  const createMut = useMutation({
    mutationFn: (n: string) => disciplinesApi.create(n),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["disciplines"] }); setName(""); setErr(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => disciplinesApi.update(id, name),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["disciplines"] }); setEditId(null); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => disciplinesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["disciplines"] }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div>
      <div className="page-header">
        <h1>Disciplines</h1>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginBottom: 12, fontSize: 14, fontWeight: 600 }}>Add Discipline</h3>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Computer Science"
            onKeyDown={(e) => e.key === "Enter" && name.trim() && createMut.mutate(name.trim())}
          />
          <button
            className="btn-primary"
            onClick={() => name.trim() && createMut.mutate(name.trim())}
            disabled={createMut.isPending || !name.trim()}
            style={{ whiteSpace: "nowrap" }}
          >
            Add
          </button>
        </div>
        {err && <p className="error-msg" style={{ marginTop: 8 }}>{err}</p>}
      </div>

      <div className="card">
        {isLoading ? (
          <div className="center"><div className="spinner" /></div>
        ) : (
          <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Created</th>
                <th style={{ width: 120 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((d: Discipline) => (
                <tr key={d.id}>
                  <td>
                    {editId === d.id ? (
                      <input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        style={{ maxWidth: 300 }}
                        autoFocus
                      />
                    ) : d.name}
                  </td>
                  <td style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {new Date(d.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    {editId === d.id ? (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn-primary" style={{ padding: "4px 10px" }}
                          onClick={() => updateMut.mutate({ id: d.id, name: editName.trim() })}
                          disabled={!editName.trim()}>Save</button>
                        <button className="btn-ghost" style={{ padding: "4px 10px" }}
                          onClick={() => setEditId(null)}>Cancel</button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn-ghost" style={{ padding: "4px 10px" }}
                          onClick={() => { setEditId(d.id); setEditName(d.name); }}>Edit</button>
                        <button className="btn-danger" style={{ padding: "4px 10px" }}
                          onClick={() => { if (confirm(`Delete "${d.name}"?`)) deleteMut.mutate(d.id); }}>
                          Del
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {data?.items.length === 0 && (
                <tr><td colSpan={3} style={{ color: "var(--text-muted)", textAlign: "center" }}>No disciplines yet</td></tr>
              )}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}
