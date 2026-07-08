import { useState, useEffect } from "react";
import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { useTheme } from "../contexts/ThemeContext";
import { employeeApi } from "../api/employee";

export default function EmployeeLayout() {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: team } = useQuery({ queryKey: ["my-team"], queryFn: () => employeeApi.myTeam() });
  const hasReports = !!team && team.length > 0;
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(() => localStorage.getItem("sidebar-collapsed") === "true");

  useEffect(() => setSidebarOpen(false), [location.pathname]);

  const toggleCollapse = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar-collapsed", String(next));
      return next;
    });
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
      <header className="mobile-topbar">
        <button className="hamburger" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
          <span style={{ background: "var(--sidebar-text)" }} />
          <span style={{ background: "var(--sidebar-text)" }} />
          <span style={{ background: "var(--sidebar-text)" }} />
        </button>
        <span style={{ fontWeight: 700, fontSize: 15, color: "var(--sidebar-text)" }}>LMS</span>
      </header>

      {sidebarOpen && (
        <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />
      )}

      <div style={{ display: "flex", flex: 1, minHeight: 0, position: "relative" }}>
        <aside className={`sidebar${sidebarOpen ? " sidebar-open" : ""}${isCollapsed ? " collapsed" : ""}`}>
          <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "0 20px 16px",
            borderBottom: "1px solid var(--sidebar-border)",
            marginBottom: 16,
          }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, color: "var(--sidebar-text)", letterSpacing: "-0.01em" }}>LMS</div>
              <div style={{ fontSize: 11, color: "var(--sidebar-text-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 160 }} title={user?.name || ""}>
                {user?.name}
              </div>
            </div>
            <button className="sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close menu">
              ✕
            </button>
          </div>

          <nav style={{ flex: 1 }}>
            <NavLink
              to="/my/courses"
              style={({ isActive }) => ({
                display: "block",
                padding: "8px 16px",
                margin: "2px 12px",
                borderRadius: "6px",
                color: isActive ? "var(--sidebar-item-active-text)" : "var(--sidebar-text-muted)",
                background: isActive ? "var(--sidebar-item-active-bg)" : "transparent",
                fontSize: "13.5px",
                fontWeight: isActive ? 600 : 500,
                transition: "all 0.15s ease",
              })}
            >
              My Courses
            </NavLink>
            {hasReports && (
              <NavLink
                to="/my/team"
                style={({ isActive }) => ({
                  display: "block",
                  padding: "8px 16px",
                  margin: "2px 12px",
                  borderRadius: "6px",
                  color: isActive ? "var(--sidebar-item-active-text)" : "var(--sidebar-text-muted)",
                  background: isActive ? "var(--sidebar-item-active-bg)" : "transparent",
                  fontSize: "13.5px",
                  fontWeight: isActive ? 600 : 500,
                  transition: "all 0.15s ease",
                })}
              >
                My Team
              </NavLink>
            )}
          </nav>

          {/* Theme Switcher + Logout in a single elegant row */}
          <div style={{
            padding: "12px 16px",
            borderTop: "1px solid var(--sidebar-border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12
          }}>
            <div style={{ display: "flex", background: "var(--bg-elevated)", padding: 2, borderRadius: 6, flex: 1, maxWidth: 110 }}>
              {(["light", "dark", "mixed"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTheme(t)}
                  style={{
                    flex: 1,
                    background: theme === t ? "var(--bg-surface)" : "transparent",
                    color: theme === t ? "var(--text)" : "var(--text-muted)",
                    border: "none",
                    padding: "4px 0",
                    fontSize: 10,
                    borderRadius: 4,
                    fontWeight: theme === t ? 600 : 400,
                    cursor: "pointer",
                    textAlign: "center",
                    transition: "all 0.15s",
                    boxShadow: "none",
                  }}
                  title={`${t.charAt(0).toUpperCase() + t.slice(1)} Theme`}
                >
                  {t === "light" ? "☀️" : t === "dark" ? "🌙" : "🌗"}
                </button>
              ))}
            </div>
            <button className="btn-ghost" style={{ fontSize: 11, padding: "6px 10px", whiteSpace: "nowrap" }} onClick={handleLogout}>
              Log out
            </button>
          </div>
        </aside>

        {/* Floating Sidebar Toggle Button (Desktop only) */}
        <button
          onClick={toggleCollapse}
          className="sidebar-toggle-btn"
          style={{
            position: "absolute",
            left: isCollapsed ? "12px" : "228px",
            top: "20px",
            zIndex: 1000,
            width: "24px",
            height: "24px",
            borderRadius: "50%",
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            color: "var(--text)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            boxShadow: "var(--shadow)",
            transition: "left 0.2s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.2s, background-color 0.2s, color 0.2s",
            fontSize: "12px",
            lineHeight: 1,
            padding: 0,
            fontWeight: "bold",
          }}
          title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          {isCollapsed ? "›" : "‹"}
        </button>

        <main className="layout-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
