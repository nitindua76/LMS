import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analyticsApi, disciplinesApi, levelsApi, CourseAnalyticsSummary, EmployeeAnalyticsSummary } from "../../api/admin";
import CourseDrilldown from "../../components/admin/CourseDrilldown";
import EmployeeDrilldown from "../../components/admin/EmployeeDrilldown";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<"courses" | "employees">("courses");
  const [searchQuery, setSearchQuery] = useState("");
  const [courseStatus, setCourseStatus] = useState("");
  const [disciplineId, setDisciplineId] = useState("");
  const [levelId, setLevelId] = useState("");
  const [drilldownCourseId, setDrilldownCourseId] = useState<number | null>(null);
  const [drilldownEmployeeId, setDrilldownEmployeeId] = useState<number | null>(null);

  // Expander states (allows expanding multiple items concurrently for comparison)
  const [expandedCourses, setExpandedCourses] = useState<Record<number, boolean>>({});
  const [expandedEmployees, setExpandedEmployees] = useState<Record<number, boolean>>({});

  const toggleCourse = (id: number) => {
    setExpandedCourses(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleEmployee = (id: number) => {
    setExpandedEmployees(prev => ({ ...prev, [id]: !prev[id] }));
  };

  // Queries
  const { data: overview, isLoading: loadingOverview } = useQuery({
    queryKey: ["analytics", "overview"],
    queryFn: () => analyticsApi.overview(),
  });

  const { data: courses, isLoading: loadingCourses } = useQuery({
    queryKey: ["analytics", "courses"],
    queryFn: () => analyticsApi.courses(),
  });

  const { data: employees, isLoading: loadingEmployees } = useQuery({
    queryKey: ["analytics", "employees"],
    queryFn: () => analyticsApi.employees(),
  });

  const { data: disciplines } = useQuery({
    queryKey: ["disciplines"],
    queryFn: () => disciplinesApi.list(1, 100),
  });

  const { data: levels } = useQuery({
    queryKey: ["levels"],
    queryFn: () => levelsApi.list(1, 100),
  });

  // Filters
  const filteredCourses = (courses || []).filter((c: CourseAnalyticsSummary) => {
    const matchesSearch = c.title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = courseStatus ? c.status === courseStatus : true;
    return matchesSearch && matchesStatus;
  });

  const filteredEmployees = (employees || []).filter((e: EmployeeAnalyticsSummary) => {
    const matchesSearch = e.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.email.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesDiscipline = disciplineId ? e.discipline === disciplineId : true;
    const matchesLevel = levelId ? e.level === levelId : true;
    return matchesSearch && matchesDiscipline && matchesLevel;
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
    <div style={{ padding: "8px 0" }}>
      <div className="page-header" style={{ marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>Statistical Analytics</h1>
          <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 13 }}>
            Versatile data tools with target audience matrices and inline expanders.
          </p>
        </div>
      </div>

      {/* KPI Overview Grid */}
      {loadingOverview ? (
        <div className="center" style={{ height: 80 }}><div className="spinner" /></div>
      ) : (
        overview && (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: 16,
            marginBottom: 32
          }}>
            {/* Card 1 */}
            <div className="card" style={{
              padding: "16px 20px",
              borderLeft: "4px solid var(--accent)",
              display: "flex",
              flexDirection: "column",
              gap: 4,
              background: "linear-gradient(135deg, var(--bg-surface), var(--bg-elevated))",
              boxShadow: "var(--shadow-sm)"
            }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Enrolled Courses
              </span>
              <span style={{ fontSize: 26, fontWeight: 700, color: "var(--text)" }}>
                {overview.enrolled_courses_count}
              </span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Courses with enrollments</span>
            </div>

            {/* Card 2 */}
            <div className="card" style={{
              padding: "16px 20px",
              borderLeft: "4px solid #3b82f6",
              display: "flex",
              flexDirection: "column",
              gap: 4,
              background: "linear-gradient(135deg, var(--bg-surface), var(--bg-elevated))",
              boxShadow: "var(--shadow-sm)"
            }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Targeted Audience Instances
              </span>
              <span style={{ fontSize: 26, fontWeight: 700, color: "var(--text)" }}>
                {overview.total_targeted_instances}
              </span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Sum of targeted employees</span>
            </div>

            {/* Card 3 */}
            <div className="card" style={{
              padding: "16px 20px",
              borderLeft: "4px solid var(--success)",
              display: "flex",
              flexDirection: "column",
              gap: 4,
              background: "linear-gradient(135deg, var(--bg-surface), var(--bg-elevated))",
              boxShadow: "var(--shadow-sm)"
            }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Active (Published) Courses
              </span>
              <span style={{ fontSize: 26, fontWeight: 700, color: "var(--success)" }}>
                {overview.active_courses_count}
              </span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Live learning tracks</span>
            </div>

            {/* Card 4 */}
            <div className="card" style={{
              padding: "16px 20px",
              borderLeft: "4px solid var(--text-muted)",
              display: "flex",
              flexDirection: "column",
              gap: 4,
              background: "linear-gradient(135deg, var(--bg-surface), var(--bg-elevated))",
              boxShadow: "var(--shadow-sm)"
            }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Closed (Archived) Courses
              </span>
              <span style={{ fontSize: 26, fontWeight: 700, color: "var(--text)" }}>
                {overview.closed_courses_count}
              </span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Archived training</span>
            </div>

            {/* Card 5 */}
            <div className="card" style={{
              padding: "16px 20px",
              borderLeft: "4px solid #f59e0b",
              display: "flex",
              flexDirection: "column",
              gap: 4,
              background: "linear-gradient(135deg, var(--bg-surface), var(--bg-elevated))",
              boxShadow: "var(--shadow-sm)"
            }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Accumulated study time
              </span>
              <span style={{ fontSize: 26, fontWeight: 700, color: "#f59e0b" }}>
                {overview.total_time_spent_hours} hrs
              </span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Total learning hours</span>
            </div>
          </div>
        )
      )}

      {/* Navigation Tabs */}
      <div style={{
        display: "flex",
        borderBottom: "1px solid var(--border)",
        marginBottom: 20,
        gap: 24
      }}>
        <button
          onClick={() => { setActiveTab("courses"); setSearchQuery(""); }}
          style={{
            background: "none",
            border: "none",
            borderBottom: activeTab === "courses" ? "2px solid var(--accent)" : "2px solid transparent",
            color: activeTab === "courses" ? "var(--accent)" : "var(--text-muted)",
            padding: "8px 4px 12px",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
            transition: "all 0.2s"
          }}
        >
          Course Statistics ({courses?.length || 0})
        </button>
        <button
          onClick={() => { setActiveTab("employees"); setSearchQuery(""); }}
          style={{
            background: "none",
            border: "none",
            borderBottom: activeTab === "employees" ? "2px solid var(--accent)" : "2px solid transparent",
            color: activeTab === "employees" ? "var(--accent)" : "var(--text-muted)",
            padding: "8px 4px 12px",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
            transition: "all 0.2s"
          }}
        >
          Employee Statistics ({employees?.length || 0})
        </button>
      </div>

      {/* Filter Toolbar */}
      <div style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 12,
        marginBottom: 16,
        alignItems: "center"
      }}>
        <input
          type="text"
          placeholder={activeTab === "courses" ? "Search by course title..." : "Search by name or email..."}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            flex: "1 1 240px",
            padding: "8px 12px",
            borderRadius: "var(--radius)",
            border: "1px solid var(--border)",
            background: "var(--bg-surface)",
            color: "var(--text)"
          }}
        />

        {activeTab === "courses" ? (
          <select
            value={courseStatus}
            onChange={(e) => setCourseStatus(e.target.value)}
            style={{ width: 160, padding: "8px 12px" }}
          >
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
            <option value="archived">Archived</option>
          </select>
        ) : (
          <>
            <select
              value={disciplineId}
              onChange={(e) => setDisciplineId(e.target.value)}
              style={{ width: 180, padding: "8px 12px" }}
            >
              <option value="">All Departments</option>
              {disciplines?.items.map((d) => (
                <option key={d.id} value={d.name}>{d.name}</option>
              ))}
            </select>

            <select
              value={levelId}
              onChange={(e) => setLevelId(e.target.value)}
              style={{ width: 140, padding: "8px 12px" }}
            >
              <option value="">All Levels</option>
              {levels?.items.map((l) => (
                <option key={l.id} value={l.name}>{l.name}</option>
              ))}
            </select>
          </>
        )}
      </div>

      {/* Statistics Tables */}
      <div className="card" style={{ padding: 0 }}>
        {activeTab === "courses" ? (
          loadingCourses ? (
            <div className="center" style={{ height: 160 }}><div className="spinner" /></div>
          ) : (
            <div className="table-wrapper">
              <table style={{ margin: 0, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    <th style={{ padding: "12px 16px" }}>Course Title</th>
                    <th>Status</th>
                    <th style={{ textAlign: "right" }}>Target Audience</th>
                    <th style={{ textAlign: "right" }}>Completed</th>
                    <th style={{ textAlign: "right" }}>Started</th>
                    <th style={{ textAlign: "right" }}>Not Enrolled</th>
                    <th style={{ width: 80 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCourses.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
                        No courses found matching filters.
                      </td>
                    </tr>
                  ) : (
                    filteredCourses.map((c) => {
                      const isExpanded = !!expandedCourses[c.id];
                      return (
                        <>
                          <tr
                            key={c.id}
                            onClick={() => toggleCourse(c.id)}
                            style={{
                              cursor: "pointer",
                              borderBottom: "1px solid var(--border)",
                              background: isExpanded ? "var(--bg-elevated)" : "transparent",
                              transition: "background-color 0.2s"
                            }}
                            className="hover-row"
                          >
                            <td style={{ padding: "14px 16px", fontWeight: 600 }}>
                              <span
                                onClick={(e) => { e.stopPropagation(); setDrilldownCourseId(c.id); }}
                                style={{ color: "var(--accent)", cursor: "pointer", textDecoration: "underline" }}
                                title="View full course detail"
                              >
                                {c.title}
                              </span>
                            </td>
                            <td>
                              <span className={`badge ${c.status === "published" ? "badge-green" : c.status === "draft" ? "badge-yellow" : "badge-gray"
                                }`}>
                                {c.status}
                              </span>
                            </td>
                            <td style={{ textAlign: "right", fontWeight: 600 }}>{c.target_audience_count}</td>
                            <td style={{ textAlign: "right", color: "var(--success)", fontWeight: 600 }}>{c.completed_count}</td>
                            <td style={{ textAlign: "right", color: "var(--primary)", fontWeight: 600 }}>{c.started_count}</td>
                            <td style={{ textAlign: "right", color: "var(--danger)", fontWeight: 600 }}>{c.not_enrolled_count}</td>
                            <td style={{ textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
                              {isExpanded ? "▲" : "▼"}
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr key={`${c.id}-expanded`} style={{ background: "var(--bg-elevated)" }}>
                              <td colSpan={7} style={{ padding: "20px 24px", borderBottom: "1px solid var(--border)" }}>
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 20 }}>

                                  {/* Left: Students breakdown lists */}
                                  <div>
                                    <h4 style={{ margin: "0 0 12px", fontSize: 13, fontWeight: 700 }}>
                                      Target Employee Breakdown
                                    </h4>
                                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

                                      {/* Completed Box */}
                                      <div style={{ background: "var(--bg-surface)", borderRadius: 6, border: "1px solid var(--border)", padding: 12 }}>
                                        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--success)", marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
                                          <span>Completed</span>
                                          <span>{c.students_completed.length}</span>
                                        </div>
                                        <div style={{ maxHeight: 150, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
                                          {c.students_completed.length === 0 ? (
                                            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>None yet</span>
                                          ) : (
                                            c.students_completed.map(s => (
                                              <div key={s.user_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11 }}>
                                                <span>{s.name} <span style={{ color: "var(--text-muted)", fontSize: 10 }}>({s.email})</span></span>
                                                <span className="badge badge-green" style={{ fontSize: 9 }}>100% • Score: {s.quiz_score ?? "—"}</span>
                                              </div>
                                            ))
                                          )}
                                        </div>
                                      </div>

                                      {/* Started Box */}
                                      <div style={{ background: "var(--bg-surface)", borderRadius: 6, border: "1px solid var(--border)", padding: 12 }}>
                                        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--primary)", marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
                                          <span>Started (In Progress)</span>
                                          <span>{c.students_started.length}</span>
                                        </div>
                                        <div style={{ maxHeight: 150, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
                                          {c.students_started.length === 0 ? (
                                            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>None</span>
                                          ) : (
                                            c.students_started.map(s => (
                                              <div key={s.user_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11 }}>
                                                <span>{s.name} <span style={{ color: "var(--text-muted)", fontSize: 10 }}>({s.email})</span></span>
                                                <span className="badge badge-blue" style={{ fontSize: 9 }}>{s.progress}%</span>
                                              </div>
                                            ))
                                          )}
                                        </div>
                                      </div>

                                      {/* Not Enrolled Box */}
                                      <div style={{ background: "var(--bg-surface)", borderRadius: 6, border: "1px solid var(--border)", padding: 12 }}>
                                        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--danger)", marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
                                          <span>Not Enrolled</span>
                                          <span>{c.students_not_enrolled.length}</span>
                                        </div>
                                        <div style={{ maxHeight: 150, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
                                          {c.students_not_enrolled.length === 0 ? (
                                            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>None</span>
                                          ) : (
                                            c.students_not_enrolled.map(s => (
                                              <div key={s.user_id} style={{ fontSize: 11, color: "var(--text-muted)" }}>
                                                • {s.name} <span style={{ fontSize: 10 }}>({s.email})</span>
                                              </div>
                                            ))
                                          )}
                                        </div>
                                      </div>

                                    </div>
                                  </div>

                                  {/* Right: SCORM modules engagement */}
                                  <div>
                                    <h4 style={{ margin: "0 0 12px", fontSize: 13, fontWeight: 700 }}>
                                      SCORM Element Engagement
                                    </h4>
                                    <div style={{ background: "var(--bg-surface)", borderRadius: 6, border: "1px solid var(--border)", padding: 12 }}>
                                      {c.scorm_stats.length === 0 ? (
                                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No SCORM packages available in this course.</span>
                                      ) : (
                                        <div className="table-wrapper" style={{ maxHeight: 420, overflowY: "auto", margin: 0 }}>
                                          <table style={{ fontSize: 11, margin: 0 }}>
                                            <thead>
                                              <tr>
                                                <th>Title</th>
                                                <th style={{ textAlign: "center" }}>Completed</th>
                                                <th style={{ textAlign: "center" }}>In Progress</th>
                                                <th style={{ textAlign: "center" }}>Not Attempted</th>
                                                <th style={{ textAlign: "right" }}>Avg Time</th>
                                                <th style={{ textAlign: "right" }}>Quiz Statistics</th>
                                              </tr>
                                            </thead>
                                            <tbody>
                                              {c.scorm_stats.map((sc) => (
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
                                                  <td style={{ textAlign: "right" }}>{formatTime(sc.avg_time_sec)}</td>
                                                  <td style={{ textAlign: "right", fontStyle: sc.is_quiz ? "normal" : "italic" }}>
                                                    {sc.is_quiz ? (
                                                      <span style={{ fontSize: 10 }}>
                                                        Passed: <strong style={{ color: "var(--success)" }}>{sc.passed_count}</strong> | Failed: <strong style={{ color: "var(--danger)" }}>{sc.failed_count}</strong> (Avg: <strong>{sc.avg_score}%</strong>)
                                                      </span>
                                                    ) : (
                                                      <span style={{ color: "var(--text-muted)" }}> </span>
                                                    )}
                                                  </td>
                                                </tr>
                                              ))}
                                            </tbody>
                                          </table>
                                        </div>
                                      )}
                                    </div>
                                  </div>

                                </div>
                              </td>
                            </tr>
                          )}
                        </>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )
        ) : (
          loadingEmployees ? (
            <div className="center" style={{ height: 160 }}><div className="spinner" /></div>
          ) : (
            <div className="table-wrapper">
              <table style={{ margin: 0, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    <th style={{ padding: "12px 16px" }}>Employee Name</th>
                    <th>Email</th>
                    <th>Department</th>
                    <th>Level</th>
                    <th style={{ textAlign: "right" }}>Target Courses Completed</th>
                    <th style={{ textAlign: "right" }}>Enrolled (In Progress)</th>
                    <th style={{ textAlign: "right" }}>Not Even Enrolled</th>
                    <th style={{ width: 80 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEmployees.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
                        No employees found matching filters.
                      </td>
                    </tr>
                  ) : (
                    filteredEmployees.map((e) => {
                      const isExpanded = !!expandedEmployees[e.id];
                      return (
                        <>
                          <tr
                            key={e.id}
                            onClick={() => toggleEmployee(e.id)}
                            style={{
                              cursor: "pointer",
                              borderBottom: "1px solid var(--border)",
                              background: isExpanded ? "var(--bg-elevated)" : "transparent",
                              transition: "background-color 0.2s"
                            }}
                            className="hover-row"
                          >
                            <td style={{ padding: "14px 16px", fontWeight: 600 }}>
                              <span
                                onClick={(ev) => { ev.stopPropagation(); setDrilldownEmployeeId(e.id); }}
                                style={{ color: "var(--accent)", cursor: "pointer", textDecoration: "underline" }}
                                title="View full employee detail"
                              >
                                {e.name}
                              </span>
                            </td>
                            <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{e.email}</td>
                            <td>{e.discipline}</td>
                            <td>{e.level}</td>
                            <td style={{ textAlign: "right", color: "var(--success)", fontWeight: 600 }}>{e.completed_targeted_count}</td>
                            <td style={{ textAlign: "right", color: "var(--primary)", fontWeight: 600 }}>{e.enrolled_targeted_count}</td>
                            <td style={{ textAlign: "right", color: "var(--danger)", fontWeight: 600 }}>{e.not_enrolled_targeted_count}</td>
                            <td style={{ textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
                              {isExpanded ? "▲" : "▼"}
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr key={`${e.id}-expanded`} style={{ background: "var(--bg-elevated)" }}>
                              <td colSpan={8} style={{ padding: "20px 24px", borderBottom: "1px solid var(--border)" }}>
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 20 }}>

                                  {/* Left: Target Course Status Checklist */}
                                  <div>
                                    <h4 style={{ margin: "0 0 12px", fontSize: 13, fontWeight: 700 }}>
                                      Target Course Checklist
                                    </h4>
                                    <div style={{ background: "var(--bg-surface)", borderRadius: 6, border: "1px solid var(--border)", padding: 16 }}>
                                      {e.targeted_courses.length === 0 ? (
                                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No target courses assigned for this department/level.</span>
                                      ) : (
                                        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 300, overflowY: "auto" }}>
                                          {e.targeted_courses.map(tc => (
                                            <div key={tc.course_id} style={{
                                              display: "flex",
                                              justifyContent: "space-between",
                                              alignItems: "center",
                                              padding: "6px 8px",
                                              borderBottom: "1px solid var(--border)",
                                              fontSize: 12
                                            }}>
                                              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                                <span style={{ fontWeight: 600 }}>{tc.title}</span>
                                                <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "var(--text-muted)" }}>
                                                  <span style={{
                                                    width: 6,
                                                    height: 6,
                                                    borderRadius: "50%",
                                                    background: tc.is_active ? "var(--success)" : "var(--text-muted)"
                                                  }}></span>
                                                  {tc.is_active ? "Active course" : "Closed / Archived"}
                                                </span>
                                              </div>

                                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                                <span className={`badge ${tc.status === "Completed" ? "badge-green" : tc.status === "Enrolled" ? "badge-blue" : "badge-red"
                                                  }`} style={{ fontSize: 9 }}>
                                                  {tc.status}
                                                </span>
                                                {tc.status === "Enrolled" && (
                                                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
                                                    {tc.progress}%
                                                  </span>
                                                )}
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  </div>

                                  {/* Right: Activity Log Timeline */}
                                  <div>
                                    <h4 style={{ margin: "0 0 12px", fontSize: 13, fontWeight: 700 }}>
                                      Learning Action Timeline
                                    </h4>
                                    <div style={{ background: "var(--bg-surface)", borderRadius: 6, border: "1px solid var(--border)", padding: 16 }}>
                                      {e.timeline.length === 0 ? (
                                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No study activities recorded yet.</span>
                                      ) : (
                                        <div style={{ display: "flex", flexDirection: "column", gap: 12, maxHeight: 300, overflowY: "auto" }}>
                                          {e.timeline.map((t, idx) => (
                                            <div key={idx} style={{ display: "flex", gap: 12, fontSize: 12, borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
                                              <div style={{
                                                fontSize: 9,
                                                fontWeight: 700,
                                                textTransform: "uppercase",
                                                padding: "2px 6px",
                                                borderRadius: 3,
                                                background: t.type === "completion" ? "rgba(16, 185, 129, 0.15)" : "rgba(139, 92, 246, 0.15)",
                                                color: t.type === "completion" ? "var(--success)" : "#8b5cf6",
                                                alignSelf: "flex-start"
                                              }}>
                                                {t.type}
                                              </div>
                                              <div>
                                                <div style={{ fontWeight: 500 }}>{t.event}</div>
                                                <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>{formatDate(t.date)}</div>
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  </div>

                                </div>
                              </td>
                            </tr>
                          )}
                        </>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>

      {drilldownCourseId !== null && (
        <CourseDrilldown courseId={drilldownCourseId} onClose={() => setDrilldownCourseId(null)} />
      )}
      {drilldownEmployeeId !== null && (
        <EmployeeDrilldown employeeId={drilldownEmployeeId} onClose={() => setDrilldownEmployeeId(null)} />
      )}
    </div>
  );
}
