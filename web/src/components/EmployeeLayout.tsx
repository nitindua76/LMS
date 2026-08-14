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

  const initials = (user?.name || "")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  const THEME_ICONS: Record<"light" | "dark" | "mixed", JSX.Element> = {
    light: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
    ),
    dark: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="none">
        <path d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 1020.354 15.354z" />
      </svg>
    ),
    mixed: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M12 3a9 9 0 000 18 9 9 0 000-18z" fill="currentColor" fillOpacity="0.35" />
        <path d="M12 3v18M12 3a9 9 0 010 18" />
      </svg>
    ),
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
            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
              {initials && <div className="sidebar-avatar">{initials}</div>}
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 15, color: "var(--sidebar-text)", letterSpacing: "-0.01em" }}>LMS</div>
                <div style={{ fontSize: 11, color: "var(--sidebar-text-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 140 }} title={user?.name || ""}>
                  {user?.name}
                </div>
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
            <NavLink
              to="/my/rooms"
              style={({ isActive }) => ({
                display: "flex",
                alignItems: "center",
                gap: 6,
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
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 7l-7 5 7 5V7z" />
                <rect x="1" y="5" width="15" height="14" rx="2" />
              </svg>
              My Discussion Rooms
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
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: theme === t ? "var(--bg-surface)" : "transparent",
                    color: theme === t ? "var(--text)" : "var(--text-muted)",
                    border: "none",
                    padding: "5px 0",
                    borderRadius: 4,
                    cursor: "pointer",
                    transition: "all 0.15s",
                    boxShadow: "none",
                  }}
                  title={`${t.charAt(0).toUpperCase() + t.slice(1)} Theme`}
                  aria-label={`${t.charAt(0).toUpperCase() + t.slice(1)} theme`}
                >
                  {THEME_ICONS[t]}
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
          className={`sidebar-toggle-btn${isCollapsed ? " is-collapsed" : ""}`}
          style={{
            position: "absolute",
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
