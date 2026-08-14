import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { roomsApi, InstantRoom } from "../../api/rooms";
import { getErrorMessage } from "../../api/client";
import RoomCall from "../../components/RoomCall";

function CreateRoomForm({ onCreated }: { onCreated: (room: InstantRoom) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [admitMode, setAdmitMode] = useState<"automatic" | "manual">("automatic");
  const [err, setErr] = useState("");

  const createMut = useMutation({
    mutationFn: () => roomsApi.create({ name: name.trim(), admit_mode: admitMode }),
    onSuccess: (room) => {
      qc.invalidateQueries({ queryKey: ["my-rooms"] });
      setName("");
      onCreated(room);
    },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Start a new room</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 14 }}>
        For quick discussions, standups, or ad-hoc video calls — no scheduling needed. Share it with anyone by their CPF number.
      </p>
      {err && <p className="error-msg" style={{ marginBottom: 10 }}>{err}</p>}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="form-group" style={{ margin: 0, flex: 1, minWidth: 200 }}>
          <label>Room name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Daily standup"
            onKeyDown={(e) => e.key === "Enter" && name.trim() && createMut.mutate()}
          />
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label>Who can join</label>
          <select value={admitMode} onChange={(e) => setAdmitMode(e.target.value as "automatic" | "manual")}>
            <option value="automatic">Anyone added joins immediately</option>
            <option value="manual">I admit each person myself</option>
          </select>
        </div>
        <button className="btn-primary" disabled={!name.trim() || createMut.isPending} onClick={() => createMut.mutate()}>
          {createMut.isPending ? "Creating…" : "Create Room"}
        </button>
      </div>
    </div>
  );
}

function AddMemberByCpf({ roomId }: { roomId: number }) {
  const qc = useQueryClient();
  const [cpf, setCpf] = useState("");
  const [err, setErr] = useState("");

  const addMut = useMutation({
    mutationFn: () => roomsApi.addMemberByCpf(roomId, cpf.trim()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["my-rooms"] }); setCpf(""); setErr(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
      <input
        value={cpf}
        onChange={(e) => setCpf(e.target.value)}
        placeholder="Add by CPF number…"
        style={{ width: 180 }}
        onKeyDown={(e) => e.key === "Enter" && cpf.trim() && addMut.mutate()}
      />
      <button className="btn-ghost" style={{ padding: "4px 10px" }} disabled={!cpf.trim() || addMut.isPending} onClick={() => addMut.mutate()}>
        {addMut.isPending ? "Adding…" : "Add"}
      </button>
      {err && <span style={{ color: "var(--danger)", fontSize: 11.5 }}>{err}</span>}
    </div>
  );
}

function RoomCard({ room, onJoin }: { room: InstantRoom; onJoin: (room: InstantRoom) => void }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(room.join_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API can be blocked (permissions, non-HTTPS context) —
      // fall back to a prompt so the link is still copyable.
      window.prompt("Copy this meeting link:", room.join_url);
    }
  };

  const removeMemberMut = useMutation({
    mutationFn: (memberId: number) => roomsApi.removeMember(room.id, memberId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["my-rooms"] }),
  });

  const deleteMut = useMutation({
    mutationFn: () => roomsApi.delete(room.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["my-rooms"] }),
  });

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{room.name}</div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>
            {room.is_owner ? "You own this room" : `Hosted by ${room.owner_name}`}
            {" · "}
            {room.admit_mode === "manual" ? "Manual admit" : "Anyone added joins immediately"}
            {" · "}
            {room.members.length} member{room.members.length === 1 ? "" : "s"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-ghost" style={{ padding: "6px 10px", fontSize: 12 }} onClick={copyLink}>
            {copied ? "Copied!" : "Copy link"}
          </button>
          <button className="btn-ghost" style={{ padding: "6px 10px", fontSize: 12 }} onClick={() => setExpanded((e) => !e)}>
            {expanded ? "Hide members" : "Manage"}
          </button>
          <button className="btn-primary" style={{ padding: "6px 14px" }} onClick={() => onJoin(room)}>
            Join
          </button>
          {room.is_owner && (
            <button className="btn-danger" style={{ padding: "6px 10px", fontSize: 12 }}
              onClick={() => { if (confirm(`Delete "${room.name}"? This cannot be undone.`)) deleteMut.mutate(); }}>
              Delete
            </button>
          )}
        </div>
      </div>

      {expanded && room.is_owner && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Meeting link
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            <input readOnly value={room.join_url} style={{ flex: 1, fontSize: 12, color: "var(--text-muted)" }} onFocus={(e) => e.target.select()} />
            <button className="btn-ghost" style={{ padding: "6px 12px", fontSize: 12, whiteSpace: "nowrap" }} onClick={copyLink}>
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Members
          </div>
          <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 8 }}>
            Adding someone by CPF also emails them this link automatically, if mail is configured.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 4 }}>
            {room.members.map((m) => (
              <span key={m.id} className="badge badge-gray" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                {m.name}
                <button onClick={() => removeMemberMut.mutate(m.id)} style={{ background: "none", border: "none", color: "var(--danger)", padding: 0, cursor: "pointer" }}>✕</button>
              </span>
            ))}
            {room.members.length === 0 && <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Nobody added yet — you're the only one who can join.</span>}
          </div>
          <AddMemberByCpf roomId={room.id} />
        </div>
      )}
    </div>
  );
}

export default function Rooms() {
  const [activeRoom, setActiveRoom] = useState<InstantRoom | null>(null);

  const { data: rooms, isLoading } = useQuery({
    queryKey: ["my-rooms"],
    queryFn: () => roomsApi.list(),
  });

  if (activeRoom) {
    return <RoomCall room={activeRoom} onLeave={() => setActiveRoom(null)} />;
  }

  return (
    <div>
      <div className="page-header">
        <h1>My Discussion Rooms</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
          Instant meeting rooms for day-to-day discussions and video calls — no scheduling required.
        </p>
      </div>

      <CreateRoomForm onCreated={() => {}} />

      {isLoading ? (
        <div className="center"><div className="spinner" /></div>
      ) : rooms && rooms.length > 0 ? (
        rooms.map((room) => <RoomCard key={room.id} room={room} onJoin={setActiveRoom} />)
      ) : (
        <div className="card" style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
          You don't have any rooms yet — create one above to get started.
        </div>
      )}
    </div>
  );
}
