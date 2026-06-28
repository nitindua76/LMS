import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { coursesApi, Course, disciplinesApi, levelsApi } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

const STATUS_BADGE: Record<string, string> = {
  draft: "badge-yellow",
  published: "badge-green",
  archived: "badge-gray",
};

export default function Courses() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [filterStatus, setFilterStatus] = useState("");
  const [err, setErr] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["courses", page, filterStatus],
    queryFn: () => coursesApi.list({ page, page_size: 20, status: filterStatus || undefined }),
  });

  const { data: disciplines } = useQuery({ queryKey: ["disciplines"], queryFn: () => disciplinesApi.list(1, 100) });
  const { data: levels } = useQuery({ queryKey: ["levels"], queryFn: () => levelsApi.list(1, 100) });

  const archiveMut = useMutation({
    mutationFn: (id: number) => coursesApi.archive(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["courses"] }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div>
      <div className="page-header">
        <h1>Courses</h1>
        <Link to="/admin/courses/new">
          <button className="btn-primary">+ New Course</button>
        </Link>
      </div>

      {err && <div style={{ color: "var(--danger)", marginBottom: 12 }}>{err}</div>}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <select value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }} style={{ width: 160 }}>
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
          <option value="archived">Archived</option>
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
                  <th>Title</th>
                  <th>Status</th>
                  <th>Mandatory</th>
                  <th>Target Audience</th>
                  <th>Duration</th>
                  <th>Created</th>
                  <th style={{ width: 160 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((c: Course) => (
                  <tr key={c.id}>
                    <td>
                      <Link to={`/admin/courses/${c.id}`} style={{ color: "var(--accent)" }}>{c.title}</Link>
                    </td>
                    <td><span className={`badge ${STATUS_BADGE[c.status]}`}>{c.status}</span></td>
                    <td>
                      {c.mandatory
                        ? <span className="badge badge-red">Mandatory</span>
                        : <span className="badge badge-gray">Optional</span>}
                    </td>
                    <td>
                      {(() => {
                        if (!c.targets || c.targets.length === 0) {
                          return <span style={{ color: "var(--text-muted)", fontStyle: "italic", fontSize: 11 }}>No targets (Hidden)</span>;
                        }
                        const byDiscipline: Record<string, string[]> = {};
                        c.targets.forEach(t => {
                          const discName = disciplines?.items.find(d => d.id === t.discipline_id)?.name ?? `Dept ${t.discipline_id}`;
                          const lvlCode = levels?.items.find(l => l.id === t.level_id)?.code ?? `L${t.level_id}`;
                          if (!byDiscipline[discName]) byDiscipline[discName] = [];
                          byDiscipline[discName].push(lvlCode);
                        });
                        return (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                            {Object.entries(byDiscipline).map(([disc, lvls]) => (
                              <span key={disc} className="badge badge-gray" style={{ fontSize: 10, padding: "2px 6px" }}>
                                <strong>{disc}</strong> ({lvls.join(", ")})
                              </span>
                            ))}
                          </div>
                        );
                      })()}
                    </td>
                    <td style={{ color: "var(--text-muted)", fontSize: 12 }}>
                      {c.duration_days ? `${c.duration_days}d` : "—"}
                    </td>
                    <td style={{ color: "var(--text-muted)", fontSize: 12 }}>
                      {new Date(c.created_at).toLocaleDateString()}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4 }}>
                        <Link to={`/admin/courses/${c.id}`}>
                          <button className="btn-ghost" style={{ padding: "4px 8px" }}>View</button>
                        </Link>
                        <Link to={`/admin/courses/${c.id}/edit`}>
                          <button className="btn-ghost" style={{ padding: "4px 8px" }}>Edit</button>
                        </Link>
                        {c.status !== "archived" && (
                          <button className="btn-danger" style={{ padding: "4px 8px" }}
                            onClick={() => { if (confirm("Archive this course?")) archiveMut.mutate(c.id); }}>
                            Archive
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {data?.items.length === 0 && (
                  <tr><td colSpan={7} style={{ color: "var(--text-muted)", textAlign: "center" }}>No courses yet</td></tr>
                )}
              </tbody>
            </table>
            </div>
            {totalPages > 1 && (
              <div className="pagination">
                <button className="btn-ghost" style={{ padding: "4px 10px" }} onClick={() => setPage(p => p - 1)} disabled={page === 1}>←</button>
                <span>Page {page} of {totalPages}</span>
                <button className="btn-ghost" style={{ padding: "4px 10px" }} onClick={() => setPage(p => p + 1)} disabled={page >= totalPages}>→</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
