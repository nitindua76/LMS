import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminRoomsApi, LiveRoomSummary } from "../../api/admin";
import { getErrorMessage } from "../../api/client";
import { MediaStateIcon as Icon, CAMERA_ICON_PATH as CAMERA_ICON, MIC_ICON_PATH as MIC_ICON, SCREEN_ICON_PATH as SCREEN_ICON } from "../../components/MediaStateIcons";

const KIND_LABEL: Record<string, string> = {
  instant_room: "Instant Room",
  live_session: "Scheduled Session",
};

function formatDuration(startedAt: string | null): string {
  if (!startedAt) return "—";
  const sec = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function RoomRow({ room }: { room: LiveRoomSummary }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [broadcastOpen, setBroadcastOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [err, setErr] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-live-rooms"] });

  const endMut = useMutation({
    mutationFn: () => adminRoomsApi.end(room.kind, room.id),
    onSuccess: invalidate,
    onError: (e) => setErr(getErrorMessage(e)),
  });
  const removeMut = useMutation({
    mutationFn: (userId: number) => adminRoomsApi.removeParticipant(room.kind, room.id, userId),
    onSuccess: invalidate,
    onError: (e) => setErr(getErrorMessage(e)),
  });
  const broadcastMut = useMutation({
    mutationFn: () => adminRoomsApi.broadcast(room.kind, room.id, message.trim()),
    onSuccess: () => { setBroadcastOpen(false); setMessage(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  // Rough "load" indicator — no true per-room bandwidth data is available
  // from self-hosted LiveKit without wiring in its Prometheus metrics
  // (a phase-2 item); participant/camera/screen-share counts are a
  // reasonable proxy for "how heavy is this room right now."
  const loadLevel = room.camera_count * 2 + room.screen_share_count * 3 + room.participant_count;
  const loadBadge = loadLevel >= 15 ? "badge-red" : loadLevel >= 6 ? "badge-yellow" : "badge-gray";

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span className="badge badge-gray">{KIND_LABEL[room.kind] ?? room.kind}</span>
            <span className={`badge ${loadBadge}`} title="Rough load estimate from participant/camera/screen-share counts">
              {loadLevel >= 15 ? "Heavy" : loadLevel >= 6 ? "Moderate" : "Light"}
            </span>
            <span style={{ fontWeight: 600, fontSize: 14 }}>{room.title}</span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 4 }}>
            Hosted by {room.owner_or_host_name} · running {formatDuration(room.started_at)}
            {" · "}{room.participant_count} participant{room.participant_count === 1 ? "" : "s"}
            {" · "}{room.camera_count} on camera · {room.screen_share_count} sharing screen
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-ghost" style={{ padding: "6px 10px", fontSize: 12 }} onClick={() => setExpanded((e) => !e)}>
            {expanded ? "Hide" : "Details"}
          </button>
          <button className="btn-secondary" style={{ padding: "6px 10px", fontSize: 12 }} onClick={() => setBroadcastOpen((b) => !b)}>
            Message
          </button>
          <button className="btn-danger" style={{ padding: "6px 10px", fontSize: 12 }}
            onClick={() => { if (confirm(`End "${room.title}"? Everyone will be disconnected.`)) endMut.mutate(); }}>
            End
          </button>
        </div>
      </div>

      {err && <p className="error-msg" style={{ marginTop: 10 }}>{err}</p>}

      {broadcastOpen && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
          <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 6 }}>
            Sends a visible, clearly-labeled message to everyone currently in this room — use this instead of joining to check on a session.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="e.g. Please keep sessions focused on work topics."
              style={{ flex: 1 }}
            />
            <button className="btn-primary" style={{ padding: "6px 14px" }}
              disabled={!message.trim() || broadcastMut.isPending} onClick={() => broadcastMut.mutate()}>
              {broadcastMut.isPending ? "Sending…" : "Send"}
            </button>
          </div>
        </div>
      )}

      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Participants
          </div>
          {room.participants.length === 0 && <p style={{ fontSize: 12, color: "var(--text-muted)" }}>No one currently in the room.</p>}
          {room.participants.map((p) => (
            <div key={p.user_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 0", fontSize: 12.5, borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span>{p.name}</span>
                {!p.admitted && <span className="badge badge-yellow" style={{ fontSize: 10 }}>waiting</span>}
                <span title="Camera"><Icon path={CAMERA_ICON} active={p.camera_on} /></span>
                <span title="Microphone"><Icon path={MIC_ICON} active={p.mic_on} /></span>
                <span title="Screen share"><Icon path={SCREEN_ICON} active={p.screen_sharing} /></span>
              </div>
              <button className="btn-ghost" style={{ padding: "3px 10px", fontSize: 11 }}
                onClick={() => { if (confirm(`Remove ${p.name} from this room?`)) removeMut.mutate(p.user_id); }}>
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function LiveSessionsDashboard() {
  const qc = useQueryClient();
  const [err, setErr] = useState("");

  const { data: rooms, isLoading } = useQuery({
    queryKey: ["admin-live-rooms"],
    queryFn: () => adminRoomsApi.list(),
    refetchInterval: 5000,
  });

  const endAllMut = useMutation({
    mutationFn: () => adminRoomsApi.endAll(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-live-rooms"] }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const totalParticipants = (rooms ?? []).reduce((sum, r) => sum + r.participant_count, 0);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Live Sessions</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
            Everything currently active — Instant Rooms and scheduled training sessions together.
            {rooms && rooms.length > 0 && ` ${rooms.length} room${rooms.length === 1 ? "" : "s"}, ${totalParticipants} participant${totalParticipants === 1 ? "" : "s"} right now.`}
          </p>
        </div>
        {rooms && rooms.length > 0 && (
          <button
            className="btn-danger"
            onClick={() => {
              if (confirm(`End ALL ${rooms.length} active rooms/sessions right now? Everyone will be disconnected. This cannot be undone.`)) {
                endAllMut.mutate();
              }
            }}
            disabled={endAllMut.isPending}
          >
            {endAllMut.isPending ? "Ending everything…" : "End All (bandwidth emergency)"}
          </button>
        )}
      </div>

      {err && <p className="error-msg" style={{ marginBottom: 16 }}>{err}</p>}

      {isLoading ? (
        <div className="center"><div className="spinner" /></div>
      ) : rooms && rooms.length > 0 ? (
        rooms.map((room) => <RoomRow key={`${room.kind}-${room.id}`} room={room} />)
      ) : (
        <div className="card" style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
          Nothing is live right now.
        </div>
      )}
    </div>
  );
}
