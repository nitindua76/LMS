import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { employeeApi, CourseState } from "../../api/employee";

// Courses in one of these states are "done" — hidden by default so the
// list defaults to what still needs action (not started / in progress),
// with a toggle to bring finished/expired courses back into view.
const FINISHED_STATES = new Set(["completed", "failed", "expired"]);

const STATE_BADGE: Record<string, { cls: string; label: string; accent: string }> = {
  locked: { cls: "badge-gray", label: "Locked", accent: "var(--border)" },
  not_started: { cls: "badge-blue", label: "Not Started", accent: "var(--accent)" },
  available: { cls: "badge-blue", label: "Not Started", accent: "var(--accent)" },
  in_progress: { cls: "badge-yellow", label: "In Progress", accent: "var(--warning)" },
  completed: { cls: "badge-green", label: "Completed", accent: "var(--success)" },
  failed: { cls: "badge-red", label: "Failed", accent: "var(--danger)" },
  expired: { cls: "badge-red", label: "Expired", accent: "var(--danger)" },
};

function CourseCard({ course }: { course: CourseState }) {
  const badge = STATE_BADGE[course.state] ?? STATE_BADGE.not_started;
  const locked = course.state === "locked";
  const hasMeta = Boolean(course.duration_days || (course.deadline_at && !locked));

  return (
    <div
      className={`card course-card ${locked ? "is-locked" : "is-active"}`}
      style={{ borderTop: `3px solid ${badge.accent}` }}
    >
      <div className="course-card-badges">
        {course.mandatory
          ? <span className="badge badge-red">Mandatory</span>
          : <span className="badge badge-gray">Optional</span>}
        <span className={`badge ${badge.cls}`}>{badge.label}</span>
      </div>

      <h3 className="course-card-title">{course.title}</h3>

      {course.lock_reason && (
        <p className="course-card-lock">🔒 {course.lock_reason}</p>
      )}

      {hasMeta && (
        <div className="course-card-meta">
          {course.duration_days && <span>{course.duration_days} day{course.duration_days !== 1 ? "s" : ""}</span>}
          {course.duration_days && course.deadline_at && !locked && <span className="course-card-meta-dot" />}
          {course.deadline_at && !locked && (
            <span className="due">Due {new Date(course.deadline_at).toLocaleDateString()}</span>
          )}
        </div>
      )}

      {!locked && (
        <Link to={`/my/courses/${course.course_id}`}>
          <button className="btn-primary course-card-cta">
            {course.state === "in_progress" ? "Continue" : "View course"}
            <span className="arrow">→</span>
          </button>
        </Link>
      )}
    </div>
  );
}

export default function MyCourses() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["my-courses"],
    queryFn: () => employeeApi.myCourses(),
  });
  const [showAll, setShowAll] = useState(false);

  const visible = (data ?? []).filter((c) => showAll || !FINISHED_STATES.has(c.state));
  const hiddenCount = (data?.length ?? 0) - visible.length;
  const mandatory = visible.filter((c) => c.mandatory);
  const optional = visible.filter((c) => !c.mandatory);

  if (isLoading) return <div className="center"><div className="spinner" /></div>;
  if (error) return <div style={{ color: "var(--danger)" }}>Failed to load courses.</div>;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>My Courses</h1>
        {(hiddenCount > 0 || showAll) && (
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: "normal", textTransform: "none", cursor: "pointer" }}>
            <input type="checkbox" style={{ width: "auto" }} checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
            Show completed / expired courses{!showAll && hiddenCount > 0 && ` (${hiddenCount} hidden)`}
          </label>
        )}
      </div>

      {data?.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: 48, color: "var(--text-muted)" }}>
          No courses assigned to you yet.
        </div>
      )}

      {data && data.length > 0 && visible.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: 48, color: "var(--text-muted)" }}>
          Nothing in progress or not-started — all {data.length} assigned course{data.length !== 1 && "s"} are completed/expired.
          Check "Show completed / expired courses" above to see them.
        </div>
      )}

      {mandatory.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase",
            letterSpacing: "0.08em", marginBottom: 16 }}>
            Mandatory ({mandatory.length})
          </h2>
          <div className="course-grid">
            {mandatory.map((c) => <CourseCard key={c.course_id} course={c} />)}
          </div>
        </section>
      )}

      {optional.length > 0 && (
        <section>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase",
            letterSpacing: "0.08em", marginBottom: 16 }}>
            Optional ({optional.length})
          </h2>
          <div className="course-grid">
            {optional.map((c) => <CourseCard key={c.course_id} course={c} />)}
          </div>
        </section>
      )}
    </div>
  );
}
