import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { usersApi, disciplinesApi, levelsApi } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

const EMPTY = { name: "", email: "", password: "", role: "employee", discipline_id: "", level_id: "" };

export default function NewEmployee() {
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [err, setErr] = useState("");

  const { data: disciplines } = useQuery({ queryKey: ["disciplines"], queryFn: () => disciplinesApi.list() });
  const { data: levels } = useQuery({ queryKey: ["levels"], queryFn: () => levelsApi.list() });

  const createMut = useMutation({
    mutationFn: () => usersApi.create({
      name: form.name,
      email: form.email,
      password: form.password,
      role: form.role as "admin" | "employee",
      discipline_id: form.discipline_id ? Number(form.discipline_id) : undefined,
      level_id: form.level_id ? Number(form.level_id) : undefined,
    }),
    onSuccess: (u) => navigate(`/admin/employees/${u.id}`),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const F = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [field]: e.target.value }));

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link to="/admin/employees" style={{ color: "var(--text-muted)" }}>← Employees</Link>
          <h1>New Employee</h1>
        </div>
      </div>
      <div className="card" style={{ maxWidth: 520 }}>
        <div className="form-group">
          <label>Full Name *</label>
          <input value={form.name} onChange={F("name")} placeholder="Jane Smith" />
        </div>
        <div className="form-group">
          <label>Email *</label>
          <input type="email" value={form.email} onChange={F("email")} placeholder="jane@company.com" />
        </div>
        <div className="form-group">
          <label>Temporary Password *</label>
          <input type="password" value={form.password} onChange={F("password")} placeholder="Min 8 characters" />
        </div>
        <div className="form-group">
          <label>Role</label>
          <select value={form.role} onChange={F("role")}>
            <option value="employee">Employee</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div className="form-group">
          <label>Discipline</label>
          <select value={form.discipline_id} onChange={F("discipline_id")}>
            <option value="">— None —</option>
            {disciplines?.items.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label>Level</label>
          <select value={form.level_id} onChange={F("level_id")}>
            <option value="">— None —</option>
            {levels?.items.sort((a, b) => a.rank - b.rank).map((l) => <option key={l.id} value={l.id}>{l.code} — {l.name}</option>)}
          </select>
        </div>
        {err && <p className="error-msg" style={{ marginBottom: 12 }}>{err}</p>}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-primary" onClick={() => createMut.mutate()}
            disabled={createMut.isPending || !form.name || !form.email || form.password.length < 8}>
            {createMut.isPending ? "Creating…" : "Create Employee"}
          </button>
          <Link to="/admin/employees">
            <button className="btn-ghost">Cancel</button>
          </Link>
        </div>
      </div>
    </div>
  );
}
