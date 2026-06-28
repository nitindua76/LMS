import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { usersApi, disciplinesApi, levelsApi, User, CsvRowResult } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

export default function Employees() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [filterActive, setFilterActive] = useState<string>("");
  const [csvResults, setCsvResults] = useState<CsvRowResult[] | null>(null);
  const [csvError, setCsvError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["users", page, search, filterActive],
    queryFn: () => usersApi.list({
      page,
      page_size: 20,
      search: search || undefined,
      active: filterActive === "" ? undefined : filterActive === "true",
    }),
  });

  const { data: disciplines } = useQuery({ queryKey: ["disciplines"], queryFn: () => disciplinesApi.list() });
  const { data: levels } = useQuery({ queryKey: ["levels"], queryFn: () => levelsApi.list() });

  const deactivateMut = useMutation({
    mutationFn: (id: number) => usersApi.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
  const activateMut = useMutation({
    mutationFn: (id: number) => usersApi.activate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const csvMut = useMutation({
    mutationFn: (file: File) => usersApi.importCsv(file),
    onSuccess: (results) => {
      setCsvResults(results);
      setCsvError("");
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => setCsvError(getErrorMessage(e)),
  });

  const handleCsvChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) csvMut.mutate(file);
  };

  const getDisciplineName = (id: number | null) =>
    disciplines?.items.find((d) => d.id === id)?.name ?? "—";
  const getLevelCode = (id: number | null) =>
    levels?.items.find((l) => l.id === id)?.code ?? "—";

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div>
      <div className="page-header">
        <h1>Employees</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-ghost" onClick={() => fileRef.current?.click()} disabled={csvMut.isPending}>
            {csvMut.isPending ? "Importing…" : "Import CSV"}
          </button>
          <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={handleCsvChange} />
          <Link to="/admin/employees/new">
            <button className="btn-primary">+ New Employee</button>
          </Link>
        </div>
      </div>

      {csvError && <div className="card" style={{ marginBottom: 16, color: "var(--danger)" }}>{csvError}</div>}
      {csvResults && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <strong>CSV Import Results</strong>
            <button className="btn-ghost" style={{ padding: "2px 8px" }} onClick={() => setCsvResults(null)}>✕</button>
          </div>
          <div style={{ maxHeight: 200, overflow: "auto" }}>
            {csvResults.map((r) => (
              <div key={r.row} style={{ fontSize: 12, color: r.status === "error" ? "var(--danger)" : "var(--success)", padding: "2px 0" }}>
                Row {r.row}: {r.email} — {r.status === "error" ? r.error : "imported"}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          placeholder="Search name or email…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          style={{ maxWidth: 280 }}
        />
        <select value={filterActive} onChange={(e) => { setFilterActive(e.target.value); setPage(1); }} style={{ width: 140 }}>
          <option value="">All status</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </div>

      <div className="card">
        {isLoading ? (
          <div className="center"><div className="spinner" /></div>
        ) : (
          <>
            <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Discipline</th>
                  <th>Level</th>
                  <th>Status</th>
                  <th style={{ width: 140 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((u: User) => (
                  <tr key={u.id}>
                    <td>
                      <Link to={`/admin/employees/${u.id}`} style={{ color: "var(--accent)" }}>{u.name}</Link>
                    </td>
                    <td style={{ color: "var(--text-muted)" }}>{u.email}</td>
                    <td><span className={`badge ${u.role === "admin" ? "badge-blue" : "badge-gray"}`}>{u.role}</span></td>
                    <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{getDisciplineName(u.discipline_id)}</td>
                    <td><span className="badge badge-gray">{getLevelCode(u.level_id)}</span></td>
                    <td>
                      <span className={`badge ${u.active ? "badge-green" : "badge-red"}`}>
                        {u.active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4 }}>
                        <Link to={`/admin/employees/${u.id}`}>
                          <button className="btn-ghost" style={{ padding: "4px 8px" }}>View</button>
                        </Link>
                        {u.active ? (
                          <button className="btn-danger" style={{ padding: "4px 8px" }}
                            onClick={() => { if (confirm("Deactivate user?")) deactivateMut.mutate(u.id); }}>
                            Deactivate
                          </button>
                        ) : (
                          <button className="btn-ghost" style={{ padding: "4px 8px" }}
                            onClick={() => activateMut.mutate(u.id)}>
                            Activate
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {data?.items.length === 0 && (
                  <tr><td colSpan={7} style={{ color: "var(--text-muted)", textAlign: "center" }}>No employees found</td></tr>
                )}
              </tbody>
            </table>
            </div>
            {totalPages > 1 && (
              <div className="pagination">
                <button className="btn-ghost" style={{ padding: "4px 10px" }} onClick={() => setPage(p => p - 1)} disabled={page === 1}>←</button>
                <span>Page {page} of {totalPages} ({data?.total} total)</span>
                <button className="btn-ghost" style={{ padding: "4px 10px" }} onClick={() => setPage(p => p + 1)} disabled={page >= totalPages}>→</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
