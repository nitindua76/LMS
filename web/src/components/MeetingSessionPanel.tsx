import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  sessionsApi, usersApi, disciplinesApi, levelsApi,
  LiveSessionInput, Discipline, Level, SessionParticipant,
} from "../api/admin";
import { getErrorMessage } from "../api/client";

const STATUS_BADGE: Record<string, string> = {
  scheduled: "badge-yellow", live: "badge-green", ended: "badge-gray", cancelled: "badge-red",
};

function ScheduleForm({
  courseId, sectionId, itemId, onScheduled, heading,
}: { courseId: number; sectionId: number; itemId: number; onScheduled: () => void; heading?: string }) {
  const [err, setErr] = useState("");
  const [form, setForm] = useState<LiveSessionInput>({
    mode: "meeting",
    start_at: "",
    end_at: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    join_before_start_min: 10,
    waiting_room_enabled: false,
  });

  const createMut = useMutation({
    mutationFn: () => sessionsApi.create(courseId, sectionId, itemId, {
      ...form,
      start_at: new Date(form.start_at).toISOString(),
      end_at: new Date(form.end_at).toISOString(),
    }),
    onSuccess: onScheduled,
    onError: (e) => setErr(getErrorMessage(e)),
  });

  return (
    <div>
      {heading && <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>{heading}</div>}
      {err && <div style={{ color: "var(--danger)", fontSize: 12, marginBottom: 8 }}>{err}</div>}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <div className="form-group" style={{ margin: 0 }}>
          <label>Mode</label>
          <select value={form.mode} onChange={(e) => setForm(f => ({ ...f, mode: e.target.value as "meeting" | "webinar" }))}>
            <option value="meeting">Meeting (everyone can talk)</option>
            <option value="webinar">Webinar / Seminar (host + presenters only)</option>
          </select>
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label>Start</label>
          <input type="datetime-local" value={form.start_at}
            onChange={(e) => setForm(f => ({ ...f, start_at: e.target.value }))} />
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label>End</label>
          <input type="datetime-local" value={form.end_at}
            onChange={(e) => setForm(f => ({ ...f, end_at: e.target.value }))} />
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label>Join opens (min before)</label>
          <input type="number" min={0} value={form.join_before_start_min}
            onChange={(e) => setForm(f => ({ ...f, join_before_start_min: Number(e.target.value) }))} style={{ width: 90 }} />
        </div>
      </div>
      <div style={{ marginTop: 8 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: "normal", textTransform: "none" }}>
          <input type="checkbox" style={{ width: "auto" }} checked={form.waiting_room_enabled}
            onChange={(e) => setForm(f => ({ ...f, waiting_room_enabled: e.target.checked }))} />
          Waiting room (admin must admit each attendee)
        </label>
      </div>
      <button className="btn-primary" style={{ marginTop: 10 }}
        onClick={() => createMut.mutate()}
        disabled={!form.start_at || !form.end_at || createMut.isPending}>
        {createMut.isPending ? "Scheduling…" : "Schedule Session"}
      </button>
    </div>
  );
}

export default function MeetingSessionPanel({
  courseId, sectionId, itemId,
}: { courseId: number; sectionId: number; itemId: number }) {
  const qc = useQueryClient();
  const [err, setErr] = useState("");
  const [reschedule, setReschedule] = useState(false);
  const key = ["live-session", courseId, sectionId, itemId];

  const { data: session, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => sessionsApi.get(courseId, sectionId, itemId),
    retry: false,
    // Keep polling while the session can still change state (scheduled → live
    // → ended happens on the scheduler's own clock, not from an admin click),
    // so the status badge and attendance panel below flip over on their own.
    // Once it's ended/cancelled that's terminal — no more polling needed.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // No session yet (404 while the admin is filling out the create
      // form) — nothing to poll for, and polling here was refetching every
      // 5s indefinitely, which is the "keeps refreshing" symptom.
      if (!status) return false;
      return status === "ended" || status === "cancelled" ? false : 5000;
    },
  });

  const { data: disciplines } = useQuery({ queryKey: ["disciplines"], queryFn: () => disciplinesApi.list() });
  const { data: levels } = useQuery({ queryKey: ["levels"], queryFn: () => levelsApi.list() });

  const cancelMut = useMutation({
    mutationFn: () => sessionsApi.cancel(courseId, sectionId, itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const endMut = useMutation({
    mutationFn: () => sessionsApi.end(courseId, sectionId, itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  if (isLoading) return <div className="spinner" style={{ width: 16, height: 16 }} />;

  if (!session) {
    return (
      <div style={{ background: "var(--bg-elevated)", borderRadius: 4, padding: 12, marginTop: 8 }}>
        <ScheduleForm courseId={courseId} sectionId={sectionId} itemId={itemId}
          onScheduled={() => qc.invalidateQueries({ queryKey: key })} />
      </div>
    );
  }

  const isTerminal = session.status === "ended" || session.status === "cancelled";

  return (
    <div style={{ background: "var(--bg-elevated)", borderRadius: 4, padding: 12, marginTop: 8 }}>
      {err && <div style={{ color: "var(--danger)", fontSize: 12, marginBottom: 8 }}>{err}</div>}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span className={`badge ${STATUS_BADGE[session.status]}`}>{session.status}</span>
        <span className="badge badge-gray">{session.mode}</span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {new Date(session.start_at).toLocaleString()} → {new Date(session.end_at).toLocaleString()} ({session.timezone})
        </span>
        {!isTerminal && (
          <>
            <button className="btn-ghost" style={{ padding: "2px 8px", fontSize: 11 }}
              onClick={() => cancelMut.mutate()} disabled={cancelMut.isPending}>Cancel</button>
            <button className="btn-danger" style={{ padding: "2px 8px", fontSize: 11 }}
              onClick={() => endMut.mutate()} disabled={endMut.isPending}>End Now</button>
          </>
        )}
        {isTerminal && !reschedule && (
          <button className="btn-primary" style={{ padding: "2px 8px", fontSize: 11 }}
            onClick={() => setReschedule(true)}>
            + Schedule New Session
          </button>
        )}
      </div>

      {isTerminal && reschedule && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
          <ScheduleForm courseId={courseId} sectionId={sectionId} itemId={itemId}
            heading="New occurrence — this content item's next session"
            onScheduled={() => { setReschedule(false); qc.invalidateQueries({ queryKey: key }); }} />
        </div>
      )}

      <AudienceRules courseId={courseId} sectionId={sectionId} itemId={itemId}
        disciplines={disciplines?.items ?? []} levels={levels?.items ?? []}
        rules={session.audience_rules} onError={setErr} />

      <Attendance courseId={courseId} sectionId={sectionId} itemId={itemId} status={session.status} />
    </div>
  );
}

function AudienceRules({
  courseId, sectionId, itemId, disciplines, levels, rules, onError,
}: {
  courseId: number; sectionId: number; itemId: number;
  disciplines: Discipline[]; levels: Level[];
  rules: { id: number; discipline_id: number | null; level_id: number | null; user_id: number | null }[];
  onError: (e: string) => void;
}) {
  const qc = useQueryClient();
  const key = ["live-session", courseId, sectionId, itemId];
  const [query, setQuery] = useState("");
  const { data: matches } = useQuery({
    queryKey: ["user-search", query],
    queryFn: () => usersApi.list({ search: query, page_size: 8, role: "employee" }),
    enabled: query.trim().length >= 2,
  });

  const addMut = useMutation({
    mutationFn: (data: { discipline_id?: number; level_id?: number; user_id?: number }) =>
      sessionsApi.addAudience(courseId, sectionId, itemId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: key }); setQuery(""); },
    onError: (e) => onError(getErrorMessage(e)),
  });
  const removeMut = useMutation({
    mutationFn: (ruleId: number) => sessionsApi.removeAudience(courseId, sectionId, itemId, ruleId),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: (e) => onError(getErrorMessage(e)),
  });

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
        Additional audience for this session
      </div>
      <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 0, marginBottom: 6 }}>
        On top of the course's normal department/level targeting — add a whole department, level, or a specific employee just for this session.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
        {rules.map((r) => {
          const label = r.user_id != null
            ? `Employee #${r.user_id}`
            : r.discipline_id != null
              ? disciplines.find(d => d.id === r.discipline_id)?.name ?? `Dept ${r.discipline_id}`
              : levels.find(l => l.id === r.level_id)?.code ?? `Level ${r.level_id}`;
          return (
            <span key={r.id} className="badge badge-gray" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              {label}
              <button onClick={() => removeMut.mutate(r.id)} style={{ background: "none", border: "none", color: "var(--danger)", padding: 0, cursor: "pointer" }}>✕</button>
            </span>
          );
        })}
        {rules.length === 0 && <span style={{ fontSize: 12, color: "var(--text-muted)" }}>None — inherits the course's normal targeting only.</span>}
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <select onChange={(e) => { if (e.target.value) { addMut.mutate({ discipline_id: Number(e.target.value) }); e.target.value = ""; } }} defaultValue="">
          <option value="" disabled>+ Add department…</option>
          {disciplines.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <select onChange={(e) => { if (e.target.value) { addMut.mutate({ level_id: Number(e.target.value) }); e.target.value = ""; } }} defaultValue="">
          <option value="" disabled>+ Add level…</option>
          {levels.map(l => <option key={l.id} value={l.id}>{l.code} ({l.name})</option>)}
        </select>
        <div style={{ position: "relative" }}>
          <input placeholder="Search employee by name/email…" value={query} onChange={(e) => setQuery(e.target.value)} style={{ width: 220 }} />
          {matches && matches.items.length > 0 && (
            <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 10, background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 4, maxHeight: 160, overflowY: "auto" }}>
              {matches.items.map(u => (
                <div key={u.id} style={{ padding: "6px 8px", cursor: "pointer", fontSize: 12 }}
                  onClick={() => addMut.mutate({ user_id: u.id })}>
                  {u.name} <span style={{ color: "var(--text-muted)" }}>({u.email})</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Live-elapsed clock for in-room participants — duration_sec only reflects
// completed stints (it's written by the leave/webhook path), so someone
// still in the room would otherwise show a stale/zero duration until they
// leave. Ticks once a second purely to re-render; it doesn't refetch.
function useNowTick(enabled: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [enabled]);
  return now;
}

function Attendance({
  courseId, sectionId, itemId, status,
}: { courseId: number; sectionId: number; itemId: number; status: string }) {
  const isLive = status === "live";
  const { data: participants } = useQuery({
    queryKey: ["session-participants", courseId, sectionId, itemId],
    queryFn: () => sessionsApi.participants(courseId, sectionId, itemId),
    // Poll while the session is actually running so the admin sees near
    // real-time attendance; once it's ended/cancelled/still scheduled,
    // one fetch is enough — those last numbers just stay on screen.
    refetchInterval: isLive ? 5000 : false,
  });
  const now = useNowTick(isLive);

  if (!participants || participants.length === 0) return null;

  const liveElapsedSec = (p: SessionParticipant) =>
    p.left_at ? p.duration_sec : p.duration_sec + Math.max(0, Math.floor((now - new Date(p.joined_at).getTime()) / 1000));

  const currentlyIn = participants.filter((p) => !p.left_at).length;
  const totalJoined = new Set(participants.map((p) => p.user_id)).size;
  const completedDurations = participants.map((p) => p.duration_sec).filter((d) => d > 0);
  const avgMin = completedDurations.length
    ? Math.round(completedDurations.reduce((a, b) => a + b, 0) / completedDurations.length / 60)
    : 0;

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
        {isLive ? "Live attendance" : "Attendance (last recorded)"}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>
        {isLive && <span className="badge badge-green" style={{ fontSize: 10, marginRight: 6 }}>{currentlyIn} in room now</span>}
        {totalJoined} total joined{avgMin > 0 && ` · avg ${avgMin}m`}
      </div>
      {participants.map((p) => (
        <div key={p.id} style={{ fontSize: 12, display: "flex", gap: 8, padding: "2px 0" }}>
          <span>User #{p.user_id}</span>
          <span className="badge badge-gray" style={{ fontSize: 10 }}>{p.role}</span>
          <span style={{ color: "var(--text-muted)" }}>{Math.round(liveElapsedSec(p) / 60)}m attended</span>
          {!p.left_at && <span className="badge badge-green" style={{ fontSize: 10 }}>in room</span>}
        </div>
      ))}
    </div>
  );
}
