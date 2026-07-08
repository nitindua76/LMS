import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { employeeApi } from "../../api/employee";

export default function TeamMemberCourseDetail() {
  const { memberId: memberIdParam, courseId: courseIdParam } = useParams<{ memberId: string; courseId: string }>();
  const memberId = Number(memberIdParam);
  const courseId = Number(courseIdParam);

  const { data: team } = useQuery({ queryKey: ["my-team"], queryFn: () => employeeApi.myTeam() });
  const member = team?.find((m) => m.id === memberId);

  const { data: course, isLoading, error } = useQuery({
    queryKey: ["team-member-course", memberId, courseId],
    queryFn: () => employeeApi.teamMemberCourseDetail(memberId, courseId),
    enabled: Number.isFinite(memberId) && Number.isFinite(courseId),
  });

  if (isLoading) return <div className="center"><div className="spinner" /></div>;
  if (error) return (
    <div>
      <Link to={`/my/team/${memberId}`} style={{ color: "var(--text-muted)" }}>← Back</Link>
      <div style={{ color: "var(--danger)", marginTop: 16 }}>Unable to load this course.</div>
    </div>
  );
  if (!course) return null;

  const sectionStatus = (s: typeof course.sections[0]) => {
    if (s.completed_at) return { label: "Complete", color: "var(--success)" };
    if (s.content_done && s.has_quiz && !s.quiz_passed) return { label: "Quiz Pending", color: "var(--warning)" };
    if (s.content_done) return { label: "In Progress", color: "var(--primary)" };
    return { label: "Not Started", color: "var(--text-muted)" };
  };

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link to={`/my/team/${memberId}`} style={{ color: "var(--text-muted)" }}>← {member?.name ?? "Back"}</Link>
          <h1>{course.title}</h1>
        </div>
        {course.deadline_at && (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Due {new Date(course.deadline_at).toLocaleDateString()}
          </span>
        )}
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>Sections & Scores</h2>
          <span className={`badge ${
            course.state === "completed" ? "badge-green" :
            course.state === "failed" ? "badge-red" :
            course.state === "in_progress" ? "badge-blue" : "badge-gray"
          }`}>
            {course.state.replace("_", " ")}
          </span>
        </div>

        {course.sections.length === 0 && (
          <p style={{ color: "var(--text-muted)" }}>No sections in this course.</p>
        )}

        {course.sections.map((s, idx) => {
          const status = sectionStatus(s);
          return (
            <div key={s.section_id} style={{
              padding: "14px 0",
              borderBottom: idx < course.sections.length - 1 ? "1px solid var(--border)" : "none",
              display: "flex", alignItems: "center", gap: 10,
            }}>
              <span style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                width: 28, height: 28, borderRadius: "50%",
                background: s.completed_at ? "var(--success)" : "var(--primary)",
                color: "#fff", fontSize: 12, fontWeight: 600, flexShrink: 0,
              }}>
                {s.completed_at ? "✓" : s.order_index + 1}
              </span>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500, display: "flex", alignItems: "center", gap: 8 }}>
                  {s.title}
                  {s.has_quiz && <span className="badge badge-gray" style={{ fontSize: 10 }}>Quiz</span>}
                </div>
                {s.has_quiz && (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                    {s.best_score_pct != null
                      ? `Best score: ${s.best_score_pct}% (${s.attempts_used} attempt${s.attempts_used === 1 ? "" : "s"})`
                      : "No quiz attempts yet"}
                  </div>
                )}
                {!s.completed_at && s.content_pct != null && (
                  <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{
                      flex: 1, maxWidth: 160, height: 5, borderRadius: 3,
                      background: "var(--bg-elevated)", border: "1px solid var(--border)", overflow: "hidden",
                    }}>
                      <div style={{
                        height: "100%", width: `${s.content_pct}%`,
                        background: "var(--primary)", borderRadius: 3,
                      }} />
                    </div>
                    <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)" }}>{s.content_pct}% watched</span>
                  </div>
                )}
              </div>

              <span style={{ fontSize: 11, color: status.color, fontWeight: 500, flexShrink: 0 }}>{status.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
