import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { usersApi, disciplinesApi, levelsApi } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

export default function EmployeeDetail() {
  const { id } = useParams<{ id: string }>();
  const userId = Number(id);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [editMode, setEditMode] = useState(false);
  const [resetPw, setResetPw] = useState("");
  const [resetMsg, setResetMsg] = useState("");
  const [err, setErr] = useState("");

  const { data: user, isLoading } = useQuery({
    queryKey: ["user", userId],
    queryFn: () => usersApi.get(userId),
  });
  const { data: disciplines } = useQuery({ queryKey: ["disciplines"], queryFn: () => disciplinesApi.list() });
  const { data: levels } = useQuery({ queryKey: ["levels"], queryFn: () => levelsApi.list() });

  const [form, setForm] = useState({ name: "", email: "", role: "employee", discipline_id: "", level_id: "" });

  const updateMut = useMutation({
    mutationFn: () => usersApi.update(userId, {
      name: form.name,
      email: form.email,
      role: form.role as "admin" | "employee",
      discipline_id: form.discipline_id ? Number(form.discipline_id) : undefined,
      level_id: form.level_id ? Number(form.level_id) : undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["user", userId] }); setEditMode(false); setErr(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const deactivateMut = useMutation({
    mutationFn: () => usersApi.deactivate(userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["user", userId] }),
  });

  const activateMut = useMutation({
    mutationFn: () => usersApi.activate(userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["user", userId] }),
  });

  const resetMut = useMutation({
    mutationFn: () => usersApi.resetPassword(userId, resetPw),
    onSuccess: () => { setResetMsg("Password reset. User must log in again."); setResetPw(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  if (isLoading) return <div className="center"><div className="spinner" /></div>;
  if (!user) return <div>User not found</div>;

  const startEdit = () => {
    setForm({
      name: user.name,
      email: user.email,
      role: user.role,
      discipline_id: user.discipline_id?.toString() ?? "",
      level_id: user.level_id?.toString() ?? "",
    });
    setEditMode(true);
  };

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link to="/admin/employees" style={{ color: "var(--text-muted)" }}>← Employees</Link>
          <h1>{user.name}</h1>
          <span className={`badge ${user.active ? "badge-green" : "badge-red"}`}>
            {user.active ? "Active" : "Inactive"}
          </span>
        </div>
        {!editMode && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn-ghost" onClick={startEdit}>Edit</button>
            {user.active
              ? <button className="btn-danger" onClick={() => { if (confirm("Deactivate?")) deactivateMut.mutate(); }}>Deactivate</button>
              : <button className="btn-ghost" onClick={() => activateMut.mutate()}>Activate</button>
            }
          </div>
        )}
      </div>

      {editMode ? (
        <div className="card" style={{ maxWidth: 520 }}>
          <h3 style={{ marginBottom: 16, fontSize: 14, fontWeight: 600 }}>Edit Employee</h3>
          <div className="form-group">
            <label>Name</label>
            <input value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={form.email} onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} />
          </div>
          <div className="form-group">
            <label>Role</label>
            <select value={form.role} onChange={(e) => setForm(f => ({ ...f, role: e.target.value }))}>
              <option value="employee">Employee</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div className="form-group">
            <label>Discipline</label>
            <select value={form.discipline_id} onChange={(e) => setForm(f => ({ ...f, discipline_id: e.target.value }))}>
              <option value="">— None —</option>
              {disciplines?.items.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label>Level</label>
            <select value={form.level_id} onChange={(e) => setForm(f => ({ ...f, level_id: e.target.value }))}>
              <option value="">— None —</option>
              {levels?.items.sort((a, b) => a.rank - b.rank).map((l) => <option key={l.id} value={l.id}>{l.code} — {l.name}</option>)}
            </select>
          </div>
          {err && <p className="error-msg" style={{ marginBottom: 12 }}>{err}</p>}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn-primary" onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>Save</button>
            <button className="btn-ghost" onClick={() => setEditMode(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="card" style={{ maxWidth: 520, marginBottom: 24 }}>
          <div className="table-wrapper">
          <table>
            <tbody>
              <tr><td style={{ color: "var(--text-muted)", width: 140 }}>Email</td><td>{user.email}</td></tr>
              <tr><td style={{ color: "var(--text-muted)" }}>Role</td><td><span className={`badge ${user.role === "admin" ? "badge-blue" : "badge-gray"}`}>{user.role}</span></td></tr>
              <tr><td style={{ color: "var(--text-muted)" }}>Discipline</td><td>{disciplines?.items.find(d => d.id === user.discipline_id)?.name ?? "—"}</td></tr>
              <tr><td style={{ color: "var(--text-muted)" }}>Level</td><td>{levels?.items.find(l => l.id === user.level_id)?.code ?? "—"}</td></tr>
              <tr><td style={{ color: "var(--text-muted)" }}>Joined</td><td style={{ fontSize: 12 }}>{new Date(user.created_at).toLocaleDateString()}</td></tr>
            </tbody>
          </table>
          </div>
        </div>
      )}

      <div className="card" style={{ maxWidth: 520 }}>
        <h3 style={{ marginBottom: 12, fontSize: 14, fontWeight: 600 }}>Reset Password</h3>
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
          Admin-set temporary password. User will be required to log in again.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="password"
            placeholder="New temporary password"
            value={resetPw}
            onChange={(e) => setResetPw(e.target.value)}
          />
          <button className="btn-primary" onClick={() => resetMut.mutate()} disabled={resetPw.length < 8 || resetMut.isPending}
            style={{ whiteSpace: "nowrap" }}>
            Reset
          </button>
        </div>
        {resetMsg && <p style={{ color: "var(--success)", fontSize: 12, marginTop: 8 }}>{resetMsg}</p>}
      </div>
    </div>
  );
}
