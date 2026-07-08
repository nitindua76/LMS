import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { analyticsApi, EmployeeCourseProgress, EmployeeActivityEvent } from "../../api/admin";

interface EmployeeDrilldownProps {
  employeeId: number;
  onClose: () => void;
}

export default function EmployeeDrilldown({ employeeId, onClose }: EmployeeDrilldownProps) {
  const [drillTab, setDrillTab] = useState<"courses" | "timeline">("courses");

  const { data: detail, isLoading } = useQuery({
    queryKey: ["analytics", "employees", employeeId],
    queryFn: () => analyticsApi.employeeDetail(employeeId),
  });

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "—";
    return new Date(dateStr).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0, 0, 0, 0.6)",
      backdropFilter: "blur(4px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 2000,
      padding: 16
    }}>
      <div className="card" style={{
        maxWidth: 900,
        width: "100%",
        maxHeight: "85vh",
        display: "flex",
        flexDirection: "column",
        padding: 0,
        overflow: "hidden",
        boxShadow: "var(--shadow-lg)",
        background: "var(--bg-surface)"
      }}>
        {/* Modal Header */}
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "20px 24px",
          borderBottom: "1px solid var(--border)"
        }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>
              {isLoading ? "Loading Employee Details..." : detail?.name}
            </h2>
            <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 12 }}>
              {detail?.email} • Dept: {detail?.discipline} • Level: {detail?.level} • Status: {
                detail ? (detail.active ? "Active" : "Inactive") : "..."
              }
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Link to={`/admin/employees/${employeeId}`}>
              <button className="btn-secondary" style={{ fontSize: 12, padding: "6px 12px" }}>
                Full Profile →
              </button>
            </Link>
            <button
              onClick={onClose}
              style={{
                background: "none",
                border: "none",
                fontSize: 24,
                color: "var(--text-muted)",
                cursor: "pointer",
                padding: 4,
                lineHeight: 1
              }}
            >
              &times;
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="center" style={{ padding: 60 }}><div className="spinner" /></div>
        ) : (
          detail && (
            <>
              {/* Modal Tabs */}
              <div style={{
                display: "flex",
                gap: 16,
                padding: "0 24px",
                borderBottom: "1px solid var(--border)",
                background: "var(--bg-elevated)"
              }}>
                <button
                  onClick={() => setDrillTab("courses")}
                  style={{
                    background: "none",
                    border: "none",
                    borderBottom: drillTab === "courses" ? "2px solid var(--accent)" : "2px solid transparent",
                    color: drillTab === "courses" ? "var(--accent)" : "var(--text-muted)",
                    padding: "12px 4px",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer"
                  }}
                >
                  Course Progress ({detail.courses.length})
                </button>
                <button
                  onClick={() => setDrillTab("timeline")}
                  style={{
                    background: "none",
                    border: "none",
                    borderBottom: drillTab === "timeline" ? "2px solid var(--accent)" : "2px solid transparent",
                    color: drillTab === "timeline" ? "var(--accent)" : "var(--text-muted)",
                    padding: "12px 4px",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer"
                  }}
                >
                  Activity Timeline ({detail.timeline.length})
                </button>
              </div>

              {/* Modal Body */}
              <div style={{
                padding: 24,
                overflowY: "auto",
                flex: 1
              }}>
                {drillTab === "courses" ? (
                  <div className="table-wrapper">
                    <table>
                      <thead>
                        <tr>
                          <th>Course Title</th>
                          <th>Status</th>
                          <th style={{ textAlign: "right" }}>Progress</th>
                          <th style={{ textAlign: "right" }}>Quiz Score</th>
                          <th style={{ textAlign: "right" }}>Time Spent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.courses.length === 0 ? (
                          <tr>
                            <td colSpan={5} style={{ textAlign: "center", color: "var(--text-muted)", padding: 16 }}>
                              No courses assigned or enrolled.
                            </td>
                          </tr>
                        ) : (
                          detail.courses.map((c: EmployeeCourseProgress) => (
                            <tr key={c.course_id}>
                              <td style={{ fontWeight: 600 }}>{c.title}</td>
                              <td>
                                <span className={`badge ${
                                  c.status === "completed" ? "badge-green" : c.status === "in_progress" ? "badge-blue" : "badge-gray"
                                }`}>
                                  {c.status.replace("_", " ")}
                                </span>
                              </td>
                              <td style={{ textAlign: "right", fontWeight: 600 }}>{c.progress}%</td>
                              <td style={{ textAlign: "right", color: "var(--text-muted)" }}>
                                {c.quiz_score !== null ? `${c.quiz_score}%` : "—"}
                              </td>
                              <td style={{ textAlign: "right", color: "var(--text-muted)" }}>
                                {c.time_spent_hours > 0 ? `${c.time_spent_hours} hrs` : "—"}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ padding: "8px 0" }}>
                    {detail.timeline.length === 0 ? (
                      <div style={{ textAlign: "center", color: "var(--text-muted)", padding: 16 }}>
                        No learning activities logged yet.
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                        {detail.timeline.map((item: EmployeeActivityEvent, idx: number) => (
                          <div key={idx} style={{
                            display: "flex",
                            gap: 16,
                            alignItems: "flex-start",
                            borderBottom: "1px solid var(--border)",
                            paddingBottom: 12
                          }}>
                            <div style={{
                              padding: "4px 8px",
                              borderRadius: 4,
                              fontSize: 10,
                              fontWeight: 600,
                              textTransform: "uppercase",
                              background: item.type === "completion" ? "rgba(16, 185, 129, 0.15)" : "rgba(139, 92, 246, 0.15)",
                              color: item.type === "completion" ? "var(--success)" : "#8b5cf6",
                              whiteSpace: "nowrap"
                            }}>
                              {item.type}
                            </div>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500 }}>
                                {item.event}
                              </div>
                              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                                {formatDate(item.date)}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )
        )}

        {/* Modal Footer */}
        <div style={{
          padding: "16px 24px",
          borderTop: "1px solid var(--border)",
          display: "flex",
          justifyContent: "flex-end",
          background: "var(--bg-elevated)"
        }}>
          <button className="btn-secondary" onClick={onClose}>Close Detail View</button>
        </div>
      </div>
    </div>
  );
}
