import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analyticsApi, CourseStudentProgress, CourseScormStat } from "../../api/admin";

interface CourseDrilldownProps {
  courseId: number;
  onClose: () => void;
}

export default function CourseDrilldown({ courseId, onClose }: CourseDrilldownProps) {
  const [drillTab, setDrillTab] = useState<"students" | "scorm">("students");

  const { data: detail, isLoading } = useQuery({
    queryKey: ["analytics", "courses", courseId],
    queryFn: () => analyticsApi.courseDetail(courseId),
  });

  const formatTime = (sec: number) => {
    if (sec < 60) return `${sec}s`;
    const mins = Math.floor(sec / 60);
    const secs = Math.round(sec % 60);
    return `${mins}m ${secs}s`;
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "—";
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
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
              {isLoading ? "Loading Course Details..." : detail?.title}
            </h2>
            <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 12 }}>
              Course ID: {courseId} • Status: {detail?.status || "..."}
            </p>
          </div>
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
                  onClick={() => setDrillTab("students")}
                  style={{
                    background: "none",
                    border: "none",
                    borderBottom: drillTab === "students" ? "2px solid var(--accent)" : "2px solid transparent",
                    color: drillTab === "students" ? "var(--accent)" : "var(--text-muted)",
                    padding: "12px 4px",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer"
                  }}
                >
                  Enrolled Students ({detail.students.length})
                </button>
                <button
                  onClick={() => setDrillTab("scorm")}
                  style={{
                    background: "none",
                    border: "none",
                    borderBottom: drillTab === "scorm" ? "2px solid var(--accent)" : "2px solid transparent",
                    color: drillTab === "scorm" ? "var(--accent)" : "var(--text-muted)",
                    padding: "12px 4px",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer"
                  }}
                >
                  SCORM Item Engagement ({detail.scorm_stats.length})
                </button>
              </div>

              {/* Modal Body */}
              <div style={{
                padding: 24,
                overflowY: "auto",
                flex: 1
              }}>
                {drillTab === "students" ? (
                  <div className="table-wrapper">
                    <table>
                      <thead>
                        <tr>
                          <th>Student Name</th>
                          <th>Email</th>
                          <th>Enrollment Status</th>
                          <th style={{ textAlign: "right" }}>Progress</th>
                          <th style={{ textAlign: "right" }}>Quiz Score</th>
                          <th>Start Date</th>
                          <th>Completion Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.students.length === 0 ? (
                          <tr>
                            <td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: 16 }}>
                              No students enrolled in this course yet.
                            </td>
                          </tr>
                        ) : (
                          detail.students.map((s: CourseStudentProgress) => (
                            <tr key={s.user_id}>
                              <td style={{ fontWeight: 600 }}>{s.name}</td>
                              <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{s.email}</td>
                              <td>
                                <span className={`badge ${s.status === "completed" ? "badge-green" : s.status === "in_progress" ? "badge-blue" : "badge-gray"
                                  }`}>
                                  {s.status.replace("_", " ")}
                                </span>
                              </td>
                              <td style={{ textAlign: "right", fontWeight: 600 }}>{s.progress}%</td>
                              <td style={{ textAlign: "right", color: "var(--text-muted)" }}>
                                {s.quiz_score !== null ? `${s.quiz_score}%` : "—"}
                              </td>
                              <td style={{ fontSize: 12 }}>{formatDate(s.started_at)}</td>
                              <td style={{ fontSize: 12 }}>{formatDate(s.completed_at)}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="table-wrapper">
                    <table>
                      <thead>
                        <tr>
                          <th>SCORM Element Title</th>
                          <th style={{ textAlign: "center" }}>Completed</th>
                          <th style={{ textAlign: "center" }}>In Progress</th>
                          <th style={{ textAlign: "center" }}>Not Attempted</th>
                          <th style={{ textAlign: "right" }}>Avg. Time Spent</th>
                          <th style={{ textAlign: "right" }}>Quiz Statistics</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.scorm_stats.length === 0 ? (
                          <tr>
                            <td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: 16 }}>
                              No SCORM progress data found for this course.
                            </td>
                          </tr>
                        ) : (
                          detail.scorm_stats.map((sc: CourseScormStat) => (
                            <tr key={sc.sco_identifier}>
                              <td style={{ fontWeight: 600 }}>{sc.title}</td>
                              <td style={{ textAlign: "center", color: sc.completed_count > 0 ? "var(--success)" : "var(--text-muted)", fontWeight: 600 }}>
                                {sc.completed_count}
                              </td>
                              <td style={{ textAlign: "center", color: sc.in_progress_count > 0 ? "var(--warning)" : "var(--text-muted)", fontWeight: 600 }}>
                                {sc.in_progress_count}
                              </td>
                              <td style={{ textAlign: "center", color: "var(--text-muted)" }}>
                                {sc.not_attempted_count}
                              </td>
                              <td style={{ textAlign: "right", fontWeight: 500 }}>{formatTime(sc.avg_time_sec)}</td>
                              <td style={{ textAlign: "right", fontStyle: sc.is_quiz ? "normal" : "italic" }}>
                                {sc.is_quiz ? (
                                  <span style={{ fontSize: 10 }}>
                                    Passed: <strong style={{ color: "var(--success)" }}>{sc.passed_count}</strong> | Failed: <strong style={{ color: "var(--danger)" }}>{sc.failed_count}</strong> (Avg: <strong>{sc.avg_score}%</strong>)
                                  </span>
                                ) : (
                                  <span style={{ color: "var(--text-muted)" }}></span>
                                )}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
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
