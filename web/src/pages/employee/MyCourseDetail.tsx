import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { employeeApi } from "../../api/employee";

export default function MyCourseDetail() {
  const { courseId: courseIdParam } = useParams<{ courseId: string }>();
  const courseId = Number(courseIdParam);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [startError, setStartError] = useState<string | null>(null);

  const { data: course, isLoading, error } = useQuery({
    queryKey: ["my-course", courseId],
    queryFn: () => employeeApi.courseDetail(courseId),
  });

  const startMutation = useMutation({
    mutationFn: () => employeeApi.startCourse(courseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["my-course", courseId] });
      queryClient.invalidateQueries({ queryKey: ["my-courses"] });
    },
    onError: (e: any) => setStartError(e?.response?.data?.detail ?? "Failed to start course"),
  });

  if (isLoading) return <div className="center"><div className="spinner" /></div>;
  if (error) return (
    <div>
      <Link to="/my/courses" style={{ color: "var(--text-muted)" }}>← My Courses</Link>
      <div style={{ color: "var(--danger)", marginTop: 16 }}>Unable to load course. You may not have access.</div>
    </div>
  );
  if (!course) return null;

  const isLocked = course.state === "locked";
  const isStartable = !isLocked && !course.enrollment_id;
  const isEnrolled = !!course.enrollment_id;

  const sectionStatus = (s: typeof course.sections[0] & { has_started?: boolean; scorm_pct?: number | null }) => {
    if (s.completed_at) return { label: "Complete", color: "var(--success)" };
    if (s.locked) return { label: "Locked", color: "var(--text-muted)" };
    if (s.has_started) return { label: "In Progress", color: "var(--primary)" };
    if (s.content_done && !s.has_quiz) return { label: "In Progress", color: "var(--primary)" };
    if (s.content_done && s.has_quiz) return { label: "Quiz Pending", color: "var(--warning)" };
    return { label: "Not Started", color: "var(--text-muted)" };
  };

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link to="/my/courses" style={{ color: "var(--text-muted)" }}>← My Courses</Link>
          <h1>{course.title}</h1>
        </div>
        {course.deadline_at && (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Due {new Date(course.deadline_at).toLocaleDateString()}
          </span>
        )}
      </div>

      {isLocked && (
        <div className="card" style={{ marginBottom: 24, borderColor: "var(--border)", background: "var(--bg-elevated)" }}>
          <p style={{ color: "var(--text-muted)" }}>🔒 {course.lock_reason ?? "This course is locked."}</p>
        </div>
      )}

      {(course.intro || course.description) && (
        <div className="card" style={{ marginBottom: 24, padding: "24px" }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 16px", borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
            About this Course
          </h2>
          {course.intro && (
            <div style={{
              fontSize: 14,
              fontStyle: "italic",
              color: "var(--text-muted)",
              lineHeight: 1.6,
              marginBottom: course.description ? 16 : 0,
              paddingLeft: 12,
              borderLeft: "3px solid var(--accent)"
            }}>
              {course.intro}
            </div>
          )}
          {course.description && (
            <div style={{
              fontSize: 14,
              color: "var(--text)",
              lineHeight: 1.7,
              whiteSpace: "pre-wrap"
            }}>
              {course.description}
            </div>
          )}
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>Sections</h2>
          {!isLocked && (
            <span className={`badge ${
              course.state === "completed" ? "badge-green" :
              course.state === "failed" ? "badge-red" :
              course.state === "in_progress" ? "badge-blue" : "badge-gray"
            }`}>
              {course.state.replace("_", " ")}
            </span>
          )}
        </div>

        {course.sections.length === 0 && (
          <p style={{ color: "var(--text-muted)" }}>No sections in this course yet.</p>
        )}

        {course.sections.map((s, idx) => {
          const status = sectionStatus(s);
          const canOpen = isEnrolled && !s.locked;
          const firstItem = s.content_items[0];

          return (
            <div key={s.id} style={{
              padding: "14px 0",
              borderBottom: idx < course.sections.length - 1 ? "1px solid var(--border)" : "none",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {/* Step number */}
                <span style={{
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  width: 28, height: 28, borderRadius: "50%",
                  background: s.completed_at ? "var(--success)" : s.locked ? "var(--bg-elevated)" : "var(--primary)",
                  color: s.completed_at || (!s.locked) ? "#fff" : "var(--text-muted)",
                  fontSize: 12, fontWeight: 600, flexShrink: 0,
                }}>
                  {s.completed_at ? "✓" : s.order_index + 1}
                </span>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, display: "flex", alignItems: "center", gap: 8 }}>
                    {s.title}
                    {s.has_quiz && (
                      <span className="badge badge-gray" style={{ fontSize: 10 }}>Quiz</span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2, display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {s.content_items.map((ci) => (
                      <span key={ci.id} className={`badge ${ci.type === "video" ? "badge-blue" : "badge-gray"}`} style={{ fontSize: 10 }}>
                        {ci.type}
                      </span>
                    ))}
                  </div>
                  {/* SCORM progress bar — only for in-progress SCORM sections */}
                  {!s.completed_at && !s.locked && (s as any).scorm_pct != null && (
                    <div style={{ marginTop: 6 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{
                          flex: 1,
                          height: 5,
                          borderRadius: 3,
                          background: "var(--bg-elevated)",
                          border: "1px solid var(--border)",
                          overflow: "hidden",
                        }}>
                          <div style={{
                            height: "100%",
                            width: `${(s as any).scorm_pct}%`,
                            background: (s as any).scorm_pct >= 100 ? "var(--success)" : "var(--primary)",
                            borderRadius: 3,
                            transition: "width 0.4s ease",
                          }} />
                        </div>
                        <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)", flexShrink: 0 }}>
                          {(s as any).scorm_pct}%
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Status + action */}
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                  <span style={{ fontSize: 11, color: status.color, fontWeight: 500 }}>{status.label}</span>
                  {canOpen && !s.locked && (
                    <Link
                      to={`/my/courses/${courseId}/enrollments/${course.enrollment_id}/sections/${s.id}`}
                      style={{ textDecoration: "none" }}
                    >
                      <button className="btn-secondary" style={{ padding: "5px 12px", fontSize: 12 }}>
                        {s.content_done && s.has_quiz && !s.quiz_passed ? "Take Quiz" :
                         s.completed_at ? "Review" : "Open"}
                      </button>
                    </Link>
                  )}
                  {s.locked && <span style={{ color: "var(--text-muted)", fontSize: 16 }}>🔒</span>}
                </div>
              </div>
            </div>
          );
        })}

        {/* Start course CTA */}
        {isStartable && !isLocked && (
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
            {startError && (
              <p style={{ color: "var(--danger)", fontSize: 12, marginBottom: 10 }}>{startError}</p>
            )}
            <button
              className="btn-primary"
              disabled={startMutation.isPending}
              onClick={() => startMutation.mutate()}
            >
              {startMutation.isPending ? "Starting…" : "Start Course"}
            </button>
            {course.duration_days && (
              <span style={{ marginLeft: 12, fontSize: 12, color: "var(--text-muted)" }}>
                {course.duration_days}-day deadline from start
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
