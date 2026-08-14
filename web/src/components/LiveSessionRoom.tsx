import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { LiveKitRoom, VideoConference } from "@livekit/components-react";
import "@livekit/components-styles";
import { employeeApi } from "../api/employee";
import { getErrorMessage } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import AdminNoticeBanner from "./AdminNoticeBanner";

function useCountdown(targetSeconds: number | null) {
  const [remaining, setRemaining] = useState(targetSeconds ?? 0);
  useEffect(() => {
    setRemaining(targetSeconds ?? 0);
    if (!targetSeconds) return;
    const id = setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
    return () => clearInterval(id);
  }, [targetSeconds]);
  return remaining;
}

function formatCountdown(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

const DATE_OPTS: Intl.DateTimeFormatOptions = { weekday: "short", month: "short", day: "numeric" };
const TIME_OPTS: Intl.DateTimeFormatOptions = { hour: "numeric", minute: "2-digit" };

function formatSessionRange(start: Date, end: Date, timezone: string): string {
  const sameDay = start.toDateString() === end.toDateString();
  const startDate = start.toLocaleDateString(undefined, DATE_OPTS);
  const startTime = start.toLocaleTimeString(undefined, TIME_OPTS);
  const endTime = end.toLocaleTimeString(undefined, TIME_OPTS);
  if (sameDay) return `${startDate} · ${startTime} – ${endTime} (${timezone})`;
  const endDate = end.toLocaleDateString(undefined, DATE_OPTS);
  return `${startDate}, ${startTime} → ${endDate}, ${endTime} (${timezone})`;
}

const STATUS_ICON: Record<string, JSX.Element> = {
  live: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
    </svg>
  ),
  scheduled: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 3" />
    </svg>
  ),
  ended: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  ),
  cancelled: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M9 9l6 6M15 9l-6 6" />
    </svg>
  ),
};

// Host-only: add/remove people from this session's audience, on the spot —
// no need to ask an admin to edit the course's audience rules mid-call.
// Shown on the pre-join panel (not inside the LiveKitRoom itself) since
// managing who's invited is a separate concern from the call UI, and the
// host may well do this before the session even starts.
function HostParticipants({ liveSessionId }: { liveSessionId: number }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [cpf, setCpf] = useState("");
  const [err, setErr] = useState("");
  const key = ["session-participants", liveSessionId];

  const { data: participants } = useQuery({
    queryKey: key,
    queryFn: () => employeeApi.listSessionParticipants(liveSessionId),
    enabled: expanded,
    refetchInterval: expanded ? 8000 : false,
  });

  const addMut = useMutation({
    mutationFn: () => employeeApi.addSessionParticipantByCpf(liveSessionId, cpf.trim()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: key }); setCpf(""); setErr(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const removeMut = useMutation({
    mutationFn: (userId: number) => employeeApi.removeSessionParticipant(liveSessionId, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
      <button className="btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => setExpanded((e) => !e)}>
        {expanded ? "Hide participants" : "Manage participants"}
      </button>

      {expanded && (
        <div style={{ marginTop: 10 }}>
          <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 8 }}>
            Add anyone by CPF, even outside this course's normal audience — they're enrolled automatically and emailed a link.
          </p>
          {err && <p className="error-msg" style={{ fontSize: 12, marginBottom: 8 }}>{err}</p>}
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <input
              value={cpf}
              onChange={(e) => setCpf(e.target.value)}
              placeholder="Add by CPF number…"
              style={{ width: 180 }}
              onKeyDown={(e) => e.key === "Enter" && cpf.trim() && addMut.mutate()}
            />
            <button className="btn-primary" style={{ padding: "4px 12px", fontSize: 12 }}
              disabled={!cpf.trim() || addMut.isPending} onClick={() => addMut.mutate()}>
              {addMut.isPending ? "Adding…" : "Add"}
            </button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {participants?.map((p) => (
              <span key={p.user_id} className="badge badge-gray" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                {p.name}
                {p.currently_in_room && <span className="badge badge-green" style={{ fontSize: 9, padding: "1px 5px" }}>in room</span>}
                <button onClick={() => removeMut.mutate(p.user_id)} style={{ background: "none", border: "none", color: "var(--danger)", padding: 0, cursor: "pointer" }} title="Remove">✕</button>
              </span>
            ))}
            {participants?.length === 0 && (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Nobody added individually — just the course's normal audience.</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function SessionJoinPanel({
  enrollmentId, sectionId, itemId,
}: { enrollmentId: number; sectionId: number; itemId: number }) {
  const { user } = useAuth();
  const [joined, setJoined] = useState<{ url: string; token: string } | null>(null);

  const { data: eligibility, refetch } = useQuery({
    queryKey: ["session-eligibility", enrollmentId, sectionId, itemId],
    queryFn: () => employeeApi.sessionEligibility(enrollmentId, sectionId, itemId),
    refetchInterval: (query) =>
      query.state.data && !query.state.data.eligible && (query.state.data.seconds_until_join_opens ?? 0) > 0
        ? 15000
        : false,
  });

  const remaining = useCountdown(eligibility?.seconds_until_join_opens ?? null);

  const joinMut = useMutation({
    mutationFn: () => employeeApi.joinSession(enrollmentId, sectionId, itemId),
    onSuccess: (res) => setJoined({ url: res.livekit_url, token: res.token }),
  });

  const leaveMut = useMutation({
    mutationFn: () => employeeApi.leaveSession(enrollmentId, sectionId, itemId),
    onSuccess: () => { setJoined(null); refetch(); },
  });

  if (joined) {
    return (
      <div style={{ position: "fixed", inset: 0, background: "#000", zIndex: 1000 }} data-lk-theme="default">
        <LiveKitRoom
          serverUrl={joined.url}
          token={joined.token}
          connect
          options={{
            audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          }}
          onDisconnected={() => leaveMut.mutate()}
          style={{ height: "100%" }}
        >
          <AdminNoticeBanner />
          <VideoConference />
        </LiveKitRoom>
      </div>
    );
  }

  if (!eligibility?.session) {
    return <div className="card" style={{ padding: 20 }}>Loading session details…</div>;
  }

  const { session } = eligibility;
  const start = new Date(session.start_at);
  const end = new Date(session.end_at);
  const statusCls = session.status === "live" ? "badge-green" : session.status === "ended" ? "badge-gray" : session.status === "cancelled" ? "badge-red" : "badge-yellow";
  const statusColor = session.status === "live" ? "var(--success)" : session.status === "cancelled" ? "var(--danger)" : session.status === "scheduled" ? "var(--warning)" : "var(--text-muted)";

  return (
    <div className="card session-panel">
      <div className="session-panel-icon" style={{ color: statusColor, borderColor: statusColor }}>
        {STATUS_ICON[session.status] ?? STATUS_ICON.scheduled}
      </div>

      <div className="session-panel-body">
        <div className="session-panel-badges">
          <span className={`badge ${statusCls}`}>{session.status}</span>
          <span className="badge badge-gray">{session.mode === "webinar" ? "Webinar" : "Meeting"}</span>
        </div>

        <div className="session-panel-time">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="5" width="18" height="16" rx="2" />
            <path d="M8 3v4M16 3v4M3 10h18" />
          </svg>
          {formatSessionRange(start, end, session.timezone)}
        </div>

        <div className="session-panel-action">
          {eligibility.eligible ? (
            <button className="btn-primary" onClick={() => joinMut.mutate()} disabled={joinMut.isPending}>
              {joinMut.isPending ? "Joining…" : "Join Session"}
            </button>
          ) : (
            <div className="session-panel-status-msg">
              {eligibility.reason}
              {remaining > 0 && session.status === "scheduled" && (
                <span className="session-panel-countdown"> — opens in {formatCountdown(remaining)}</span>
              )}
            </div>
          )}
          {joinMut.isError && (
            <div style={{ color: "var(--danger)", fontSize: 12, marginTop: 8 }}>Could not join — please try again.</div>
          )}
        </div>

        {user && session.host_user_id === user.id && (
          <HostParticipants liveSessionId={session.id} />
        )}
      </div>
    </div>
  );
}
