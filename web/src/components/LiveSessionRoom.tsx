import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { LiveKitRoom, VideoConference } from "@livekit/components-react";
import "@livekit/components-styles";
import { employeeApi } from "../api/employee";
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

export default function SessionJoinPanel({
  enrollmentId, sectionId, itemId,
}: { enrollmentId: number; sectionId: number; itemId: number }) {
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
      </div>
    </div>
  );
}
