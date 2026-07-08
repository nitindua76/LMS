import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { employeeApi, CourseState } from "../../api/employee";

const STATE_BADGE: Record<string, { cls: string; label: string }> = {
  locked: { cls: "badge-gray", label: "Locked" },
  not_started: { cls: "badge-blue", label: "Not Started" },
  available: { cls: "badge-blue", label: "Not Started" },
  in_progress: { cls: "badge-yellow", label: "In Progress" },
  completed: { cls: "badge-green", label: "Completed" },
  failed: { cls: "badge-red", label: "Failed" },
  expired: { cls: "badge-red", label: "Expired" },
};

function TeamCourseCard({ memberId, course }: { memberId: number; course: CourseState }) {
  const badge = STATE_BADGE[course.state] ?? STATE_BADGE.not_started;
  const locked = course.state === "locked";

  return (
    <div className="card" style={{ opacity: locked ? 0.65 : 1 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {course.mandatory
            ? <span className="badge badge-red">Mandatory</span>
            : <span className="badge badge-gray">Optional</span>}
          <span className={`badge ${badge.cls}`}>{badge.label}</span>
        </div>
      </div>
      <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{course.title}</h3>
      {course.lock_reason && (
        <p style={{ fontSize: 12, color: "var(--text-muted)", fontStyle: "italic" }}>🔒 {course.lock_reason}</p>
      )}
      {course.deadline_at && !locked && (
        <p style={{ fontSize: 11, color: "var(--warning)", marginTop: 4 }}>
          Due: {new Date(course.deadline_at).toLocaleDateString()}
        </p>
      )}
      {!locked && course.enrollment_id && (
        <Link to={`/my/team/${memberId}/courses/${course.course_id}`}>
          <button className="btn-secondary" style={{ marginTop: 12, padding: "6px 14px", fontSize: 13 }}>
            View Progress
          </button>
        </Link>
      )}
    </div>
  );
}

export default function TeamMemberCourses() {
  const { memberId: memberIdParam } = useParams<{ memberId: string }>();
  const memberId = Number(memberIdParam);

  const { data: team } = useQuery({ queryKey: ["my-team"], queryFn: () => employeeApi.myTeam() });
  const member = team?.find((m) => m.id === memberId);

  const { data, isLoading, error } = useQuery({
    queryKey: ["team-member-courses", memberId],
    queryFn: () => employeeApi.teamMemberCourses(memberId),
    enabled: Number.isFinite(memberId),
  });

  if (isLoading) return <div className="center"><div className="spinner" /></div>;
  if (error) return (
    <div>
      <Link to="/my/team" style={{ color: "var(--text-muted)" }}>← My Team</Link>
      <div style={{ color: "var(--danger)", marginTop: 16 }}>Unable to load this employee's courses.</div>
    </div>
  );

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link to="/my/team" style={{ color: "var(--text-muted)" }}>← My Team</Link>
          <h1>{member?.name ?? "Courses"}</h1>
        </div>
      </div>

      {data?.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: 48, color: "var(--text-muted)" }}>
          No courses assigned to this employee.
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
        {data?.map((c) => <TeamCourseCard key={c.course_id} memberId={memberId} course={c} />)}
      </div>
    </div>
  );
}
