import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { getErrorMessage } from "../api/client";

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Redirect if already logged in
  if (user) {
    navigate(user.role === "admin" ? "/admin/courses" : "/my/courses", { replace: true });
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      // AuthProvider will update user; App will redirect via RootRedirect
      navigate(email ? "/" : "/login", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--bg)",
      padding: 16,
    }}>
      <div style={{ width: "100%", maxWidth: 380 }}>
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <h1 style={{
            fontSize: 32,
            fontWeight: 800,
            marginBottom: 6,
            letterSpacing: "-0.03em",
            background: "linear-gradient(135deg, var(--accent) 0%, #818cf8 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}>
            LMS
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13.5, fontWeight: 500 }}>
            Learning Management System
          </p>
        </div>
        <div className="card" style={{ padding: "28px 24px" }}>
          <h2 style={{ fontSize: 18, fontWeight: 750, marginBottom: 20, letterSpacing: "-0.02em" }}>Sign in</h2>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                autoFocus
              />
            </div>
            <div className="form-group" style={{ marginBottom: 20 }}>
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>
            {error && <p className="error-msg" style={{ marginBottom: 16 }}>{error}</p>}
            <button
              type="submit"
              className="btn-primary"
              style={{ width: "100%", padding: "10px 0", fontWeight: 600, fontSize: 13.5 }}
              disabled={loading}
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
