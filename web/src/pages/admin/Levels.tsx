import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { levelsApi, Level } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

const EMPTY = { code: "", name: "", rank: 1 };

export default function Levels() {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState(EMPTY);
  const [err, setErr] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["levels"],
    queryFn: () => levelsApi.list(),
  });

  const createMut = useMutation({
    mutationFn: () => levelsApi.create({ code: form.code, name: form.name, rank: Number(form.rank) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["levels"] }); setForm(EMPTY); setErr(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const updateMut = useMutation({
    mutationFn: () => levelsApi.update(editId!, { code: editForm.code, name: editForm.name, rank: Number(editForm.rank) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["levels"] }); setEditId(null); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => levelsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["levels"] }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div>
      <div className="page-header">
        <h1>Levels</h1>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginBottom: 12, fontSize: 14, fontWeight: 600 }}>Add Level</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <div style={{ flex: "0 0 100px" }}>
            <label>Code</label>
            <input value={form.code} onChange={(e) => setForm(f => ({ ...f, code: e.target.value }))} placeholder="E5" />
          </div>
          <div style={{ flex: 1 }}>
            <label>Name</label>
            <input value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Senior Engineer" />
          </div>
          <div style={{ flex: "0 0 80px" }}>
            <label>Rank</label>
            <input type="number" min={1} value={form.rank} onChange={(e) => setForm(f => ({ ...f, rank: Number(e.target.value) }))} />
          </div>
          <button className="btn-primary" onClick={() => createMut.mutate()}
            disabled={createMut.isPending || !form.code.trim() || !form.name.trim()}>
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
              <tr><th>Code</th><th>Name</th><th>Rank</th><th style={{ width: 140 }}>Actions</th></tr>
            </thead>
            <tbody>
              {data?.items.sort((a, b) => a.rank - b.rank).map((lv: Level) => (
                <tr key={lv.id}>
                  <td>
                    {editId === lv.id ? (
                      <input value={editForm.code} onChange={(e) => setEditForm(f => ({ ...f, code: e.target.value }))} style={{ maxWidth: 80 }} />
                    ) : <span className="badge badge-blue">{lv.code}</span>}
                  </td>
                  <td>
                    {editId === lv.id ? (
                      <input value={editForm.name} onChange={(e) => setEditForm(f => ({ ...f, name: e.target.value }))} />
                    ) : lv.name}
                  </td>
                  <td>
                    {editId === lv.id ? (
                      <input type="number" value={editForm.rank} onChange={(e) => setEditForm(f => ({ ...f, rank: Number(e.target.value) }))} style={{ maxWidth: 60 }} />
                    ) : lv.rank}
                  </td>
                  <td>
                    {editId === lv.id ? (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn-primary" style={{ padding: "4px 10px" }} onClick={() => updateMut.mutate()}>Save</button>
                        <button className="btn-ghost" style={{ padding: "4px 10px" }} onClick={() => setEditId(null)}>Cancel</button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn-ghost" style={{ padding: "4px 10px" }}
                          onClick={() => { setEditId(lv.id); setEditForm({ code: lv.code, name: lv.name, rank: lv.rank }); }}>Edit</button>
                        <button className="btn-danger" style={{ padding: "4px 10px" }}
                          onClick={() => { if (confirm(`Delete "${lv.code}"?`)) deleteMut.mutate(lv.id); }}>Del</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {data?.items.length === 0 && (
                <tr><td colSpan={4} style={{ color: "var(--text-muted)", textAlign: "center" }}>No levels yet</td></tr>
              )}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}
