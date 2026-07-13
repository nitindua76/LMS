import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { employeeApi, CourseState } from "../../api/employee";

// Courses in one of these states are "done" — hidden by default so the
// list defaults to what still needs action (not started / in progress),
// with a toggle to bring finished/expired courses back into view.
const FINISHED_STATES = new Set(["completed", "failed", "expired"]);

const STATE_BADGE: Record<string, { cls: string; label: string }> = {
  locked: { cls: "badge-gray", label: "Locked" },
  not_started: { cls: "badge-blue", label: "Not Started" },
  available: { cls: "badge-blue", label: "Not Started" },
  in_progress: { cls: "badge-yellow", label: "In Progress" },
  completed: { cls: "badge-green", label: "Completed" },
  failed: { cls: "badge-red", label: "Failed" },
  expired: { cls: "badge-red", label: "Expired" },
};

function CourseCard({ course }: { course: CourseState }) {
  const badge = STATE_BADGE[course.state] ?? STATE_BADGE.not_started;
  const locked = course.state === "locked";

  return (
    <div className="card" style={{
      opacity: locked ? 0.65 : 1,
      transition: "opacity 0.1s",
      position: "relative",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {course.mandatory
            ? <span className="badge badge-red">Mandatory</span>
            : <span className="badge badge-gray">Optional</span>}
          <span className={`badge ${badge.cls}`}>{badge.label}</span>
        </div>
        {course.duration_days && (
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{course.duration_days}d</span>
        )}
      </div>
      <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{course.title}</h3>
      {course.lock_reason && (
        <p style={{ fontSize: 12, color: "var(--text-muted)", fontStyle: "italic" }}>
          🔒 {course.lock_reason}
        </p>
      )}
      {course.deadline_at && !locked && (
        <p style={{ fontSize: 11, color: "var(--warning)", marginTop: 4 }}>
          Due: {new Date(course.deadline_at).toLocaleDateString()}
        </p>
      )}
      {!locked && (
        <Link to={`/my/courses/${course.course_id}`}>
          <button className="btn-primary" style={{ marginTop: 12, padding: "6px 14px", fontSize: 13 }}>
            {course.state === "in_progress" ? "Continue" : "View"}
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
            Mandatory
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
            {mandatory.map((c) => <CourseCard key={c.course_id} course={c} />)}
          </div>
        </section>
      )}

      {optional.length > 0 && (
        <section>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase",
            letterSpacing: "0.08em", marginBottom: 16 }}>
            Optional
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
            {optional.map((c) => <CourseCard key={c.course_id} course={c} />)}
          </div>
        </section>
      )}
    </div>
  );
}
