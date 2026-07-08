import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { employeeApi } from "../../api/employee";

export default function MyTeam() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["my-team"],
    queryFn: () => employeeApi.myTeam(),
  });

  if (isLoading) return <div className="center"><div className="spinner" /></div>;
  if (error) return <div style={{ color: "var(--danger)" }}>Failed to load your team.</div>;

  return (
    <div>
      <div className="page-header">
        <h1>My Team</h1>
      </div>

      {data?.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: 48, color: "var(--text-muted)" }}>
          No one currently reports to you.
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
        {data?.map((member) => (
          <Link key={member.id} to={`/my/team/${member.id}`} style={{ textDecoration: "none" }}>
            <div className="card">
              <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{member.name}</h3>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>{member.email}</p>
              <div style={{ display: "flex", gap: 6 }}>
                {member.discipline && <span className="badge badge-gray">{member.discipline.name}</span>}
                {member.level && <span className="badge badge-gray">{member.level.code}</span>}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
