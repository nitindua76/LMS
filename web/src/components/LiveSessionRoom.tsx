import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { LiveKitRoom, VideoConference } from "@livekit/components-react";
import "@livekit/components-styles";
import { employeeApi } from "../api/employee";

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
          onDisconnected={() => leaveMut.mutate()}
          style={{ height: "100%" }}
        >
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

  return (
    <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-start" }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <span className={`badge ${session.status === "live" ? "badge-green" : session.status === "ended" ? "badge-gray" : session.status === "cancelled" ? "badge-red" : "badge-yellow"}`}>
          {session.status}
        </span>
        <span className="badge badge-gray">{session.mode === "webinar" ? "Webinar" : "Meeting"}</span>
      </div>
      <div style={{ fontSize: 14 }}>
        {start.toLocaleString()} → {end.toLocaleString()} <span style={{ color: "var(--text-muted)" }}>({session.timezone})</span>
      </div>

      {eligibility.eligible ? (
        <button className="btn-primary" onClick={() => joinMut.mutate()} disabled={joinMut.isPending}>
          {joinMut.isPending ? "Joining…" : "Join Session"}
        </button>
      ) : (
        <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
          {eligibility.reason}
          {remaining > 0 && session.status === "scheduled" && (
            <span> — opens in {formatCountdown(remaining)}</span>
          )}
        </div>
      )}
      {joinMut.isError && (
        <div style={{ color: "var(--danger)", fontSize: 12 }}>Could not join — please try again.</div>
      )}
    </div>
  );
}
