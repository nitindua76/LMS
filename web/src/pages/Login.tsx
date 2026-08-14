import { useState, FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { getErrorMessage } from "../api/client";

// Edge paths for the "learning path" constellation. Node states below are
// derived from these same coordinates so lines and dots stay in sync.
const EDGES = {
  n1n2: "M90,60 Q135,90 160,140",
  n2n3: "M160,140 Q150,185 120,230",
  n3n4: "M120,230 Q165,260 200,300",
  n4n5: "M200,300 Q195,350 170,400",
  n5n6: "M170,400 Q215,430 250,470",
  n6n7: "M250,470 Q240,520 220,570",
  n7n8: "M220,570 Q265,590 300,610",
  n4b1: "M200,300 Q245,255 280,220",
  n6b2: "M250,470 Q305,415 352,372",
  n3b3: "M120,230 Q85,280 60,330",
  n2b4: "M160,140 Q290,140 400,150",
};

const COMPLETED_NODES = [
  { cx: 90, cy: 60 },
  { cx: 160, cy: 140 },
  { cx: 120, cy: 230 },
  { cx: 200, cy: 300 },
  { cx: 170, cy: 400 },
];
const LOCKED_NODES = [
  { cx: 220, cy: 570, r: 4.5 },
  { cx: 300, cy: 610, r: 4.5 },
  { cx: 280, cy: 220, r: 4 },
  { cx: 352, cy: 372, r: 4 },
  { cx: 60, cy: 330, r: 4 },
  { cx: 400, cy: 150, r: 4 },
];

function LearningPathGraph() {
  return (
    <svg className="login-graph" viewBox="0 0 520 640" fill="none" aria-hidden="true">
      {/* completed segment */}
      <path d={EDGES.n1n2} stroke="#10b981" strokeOpacity="0.35" strokeWidth="1.5" />
      <path d={EDGES.n2n3} stroke="#10b981" strokeOpacity="0.35" strokeWidth="1.5" />
      <path d={EDGES.n3n4} stroke="#10b981" strokeOpacity="0.35" strokeWidth="1.5" />
      <path d={EDGES.n4n5} stroke="#10b981" strokeOpacity="0.35" strokeWidth="1.5" />
      {/* in-progress segment, animated flow into the active node */}
      <path d={EDGES.n5n6} stroke="#6366f1" strokeOpacity="0.6" strokeWidth="1.5" className="login-edge-flow" />
      {/* locked segment ahead */}
      <path d={EDGES.n6n7} stroke="#4b4f63" strokeOpacity="0.5" strokeWidth="1.3" />
      <path d={EDGES.n7n8} stroke="#4b4f63" strokeOpacity="0.5" strokeWidth="1.3" />
      {/* locked elective branches */}
      <path d={EDGES.n4b1} stroke="#4b4f63" strokeOpacity="0.4" strokeWidth="1.1" strokeDasharray="3 4" />
      <path d={EDGES.n6b2} stroke="#4b4f63" strokeOpacity="0.4" strokeWidth="1.1" strokeDasharray="3 4" />
      <path d={EDGES.n3b3} stroke="#4b4f63" strokeOpacity="0.4" strokeWidth="1.1" strokeDasharray="3 4" />
      <path d={EDGES.n2b4} stroke="#4b4f63" strokeOpacity="0.4" strokeWidth="1.1" strokeDasharray="3 4" />

      {LOCKED_NODES.map((n, i) => (
        <circle key={i} cx={n.cx} cy={n.cy} r={n.r} fill="#1c1e2a" stroke="#4b4f63" strokeWidth="1" />
      ))}

      {COMPLETED_NODES.map((n, i) => (
        <g key={i}>
          <circle cx={n.cx} cy={n.cy} r="9" fill="#10b981" opacity="0.14" />
          <circle cx={n.cx} cy={n.cy} r="5" fill="#10b981" />
        </g>
      ))}

      {/* active node, in progress */}
      <circle cx="250" cy="470" r="16" fill="#6366f1" className="login-node-active" />
      <circle cx="250" cy="470" r="7.5" fill="#6366f1" />
      <circle cx="250" cy="470" r="7.5" fill="none" stroke="#c7d2fe" strokeWidth="1" />
    </svg>
  );
}

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Set by JoinRoom.tsx when an unauthenticated visitor opens a shared
  // meeting link — sends them back to that link instead of the default
  // course/dashboard landing page once signed in.
  const next = searchParams.get("next");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Redirect if already logged in
  if (user) {
    navigate(next || (user.role === "admin" ? "/admin/courses" : "/my/courses"), { replace: true });
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(identifier, password);
      // AuthProvider will update user; App will redirect via RootRedirect,
      // unless a specific destination (e.g. a shared meeting link) is set.
      navigate(next || "/", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-visual">
        <div className="login-graph-wrap">
          <LearningPathGraph />
        </div>

        <div className="login-brand">
          <span className="login-brand-mark">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path d="M12 3 1 8l11 5 9-4.1V17h2V8L12 3Z" fill="#fff" />
              <path d="M5 10.5V16c0 1.5 3 3.5 7 3.5s7-2 7-3.5v-5.5l-7 3.2-7-3.2Z" fill="#fff" fillOpacity="0.85" />
            </svg>
          </span>
          <div>
            <div className="login-brand-name">LMS</div>
          </div>
        </div>

        <div className="login-copy">
          <h2>Pick up where you left off.</h2>
          <p>Courses, progress, and certificates — all in one place.</p>
          <div className="login-legend">
            <span className="login-legend-item">
              <span className="login-legend-dot" style={{ background: "#10b981" }} />
              Completed
            </span>
            <span className="login-legend-item">
              <span className="login-legend-dot" style={{ background: "#6366f1" }} />
              In progress
            </span>
            <span className="login-legend-item">
              <span className="login-legend-dot" style={{ background: "#4b4f63" }} />
              Locked
            </span>
          </div>
        </div>
      </div>

      <div className="login-formside">
        <div className="login-card">
          <div className="login-form-header">
            <h1>Sign in</h1>
            <p>Enter your details to access your courses.</p>
          </div>
          <div className="login-card-panel">
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="identifier">CPF number</label>
                <input
                  id="identifier"
                  type="text"
                  inputMode="numeric"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="e.g. 55257"
                  autoComplete="username"
                  required
                  autoFocus
                />
              </div>
              <div className="form-group" style={{ marginBottom: 12 }}>
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                />
              </div>
              <p className="login-sso-hint">
                Sign in with your ONGC CPF number and Domain password.
              </p>
              {error && <p className="error-msg" style={{ marginTop: 8, marginBottom: 16 }}>{error}</p>}
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
          <p className="login-footnote">Trouble signing in? Contact your administrator.</p>
        </div>
      </div>
    </div>
  );
}
