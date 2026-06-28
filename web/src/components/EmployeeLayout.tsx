import { useState, useEffect } from "react";
import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function EmployeeLayout() {
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
        <span style={{ fontWeight: 700, fontSize: 15 }}>LMS</span>
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
              <div style={{ fontWeight: 700, fontSize: 15 }}>LMS</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{user?.name}</div>
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
                padding: "9px 20px",
                color: isActive ? "var(--accent)" : "var(--text-muted)",
                background: isActive ? "rgba(79,142,247,0.08)" : "transparent",
                borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                fontSize: 14,
                fontWeight: isActive ? 600 : 400,
              })}
            >
              My Courses
            </NavLink>
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
