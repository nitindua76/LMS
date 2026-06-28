import { useState, useEffect } from "react";
import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

const NAV = [
  { to: "/admin/courses", label: "Courses" },
  { to: "/admin/employees", label: "Employees" },
  { to: "/admin/disciplines", label: "Disciplines" },
  { to: "/admin/levels", label: "Levels" },
];

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => setSidebarOpen(false), [location.pathname]);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <header className="mobile-topbar">
        <button className="hamburger" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
          <span /><span /><span />
        </button>
        <span style={{ fontWeight: 700, fontSize: 15 }}>LMS Admin</span>
      </header>

      {sidebarOpen && (
        <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />
      )}

      <div style={{ display: "flex", flex: 1 }}>
        <aside className={`sidebar${sidebarOpen ? " sidebar-open" : ""}`}>
          <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            padding: "0 20px 24px",
            borderBottom: "1px solid var(--border)",
            marginBottom: 16,
          }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text)" }}>LMS Admin</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{user?.email}</div>
            </div>
            <button className="sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close menu">
              ✕
            </button>
          </div>
          <nav style={{ flex: 1 }}>
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                style={({ isActive }) => ({
                  display: "block",
                  padding: "9px 20px",
                  color: isActive ? "var(--accent)" : "var(--text-muted)",
                  background: isActive ? "rgba(79,142,247,0.08)" : "transparent",
                  borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                  fontSize: 14,
                  fontWeight: isActive ? 600 : 400,
                  transition: "all 0.1s",
                })}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div style={{ padding: "16px 20px", borderTop: "1px solid var(--border)" }}>
            <button className="btn-ghost" style={{ width: "100%" }} onClick={handleLogout}>
              Log out
            </button>
          </div>
        </aside>

        <main className="layout-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
