import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { LiveKitRoom, VideoConference } from "@livekit/components-react";
import "@livekit/components-styles";
import { roomsApi, InstantRoom } from "../api/rooms";
import { getErrorMessage } from "../api/client";
import AdminNoticeBanner from "./AdminNoticeBanner";

function AdmitQueue({ roomId }: { roomId: number }) {
  const qc = useQueryClient();
  const { data: pending } = useQuery({
    queryKey: ["room-pending", roomId],
    queryFn: () => roomsApi.listPending(roomId),
    refetchInterval: 3000,
  });

  const admitMut = useMutation({
    mutationFn: (userId: number) => roomsApi.admit(roomId, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["room-pending", roomId] }),
  });
  const declineMut = useMutation({
    mutationFn: (userId: number) => roomsApi.decline(roomId, userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["room-pending", roomId] }),
  });

  if (!pending || pending.length === 0) return null;

  return (
    <div className="admit-queue">
      <div className="admit-queue-title">Waiting to join ({pending.length})</div>
      {pending.map((p) => (
        <div key={p.user_id} className="admit-queue-row">
          <span>{p.name}</span>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn-primary" style={{ padding: "3px 10px", fontSize: 11.5 }} onClick={() => admitMut.mutate(p.user_id)}>
              Admit
            </button>
            <button className="btn-ghost" style={{ padding: "3px 10px", fontSize: 11.5 }} onClick={() => declineMut.mutate(p.user_id)}>
              Decline
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function WaitingForHost() {
  return (
    <div className="room-waiting-overlay">
      <div className="spinner" />
      <div style={{ marginTop: 12, fontSize: 14 }}>Waiting for the host to let you in…</div>
    </div>
  );
}

export default function RoomCall({ room, onLeave }: { room: InstantRoom; onLeave: () => void }) {
  const [joinState, setJoinState] = useState<{ url: string; token: string; isHost: boolean; admitted: boolean } | null>(null);
  const [error, setError] = useState("");

  const joinMut = useMutation({
    mutationFn: () => roomsApi.join(room.id),
    onSuccess: (res) => setJoinState({ url: res.livekit_url, token: res.token, isHost: res.is_host, admitted: res.admitted }),
    onError: (e) => setError(getErrorMessage(e)),
  });

  const leaveMut = useMutation({
    mutationFn: () => roomsApi.leave(room.id),
    onSuccess: onLeave,
  });

  useEffect(() => {
    joinMut.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room.id]);

  if (!joinState) {
    return (
      <div className="center" style={{ height: "100vh" }}>
        {error ? (
          <div style={{ textAlign: "center" }}>
            <p className="error-msg">{error}</p>
            <button className="btn-ghost" onClick={onLeave}>Back to My Rooms</button>
          </div>
        ) : (
          <div className="spinner" />
        )}
      </div>
    );
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "#000", zIndex: 1000 }} data-lk-theme="default">
      <LiveKitRoom
        serverUrl={joinState.url}
        token={joinState.token}
        connect
        options={{
          audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        }}
        onDisconnected={() => leaveMut.mutate()}
        style={{ height: "100%" }}
      >
        <AdminNoticeBanner />
        {!joinState.admitted && <WaitingForHost />}
        {joinState.isHost && <AdmitQueue roomId={room.id} />}
        <VideoConference />
      </LiveKitRoom>
    </div>
  );
}
