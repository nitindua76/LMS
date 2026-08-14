import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminRoomsApi, SessionHistoryRow } from "../../api/admin";
import { MediaStateIcon, CAMERA_ICON_PATH, MIC_ICON_PATH, SCREEN_ICON_PATH } from "../../components/MediaStateIcons";

const KIND_LABEL: Record<string, string> = {
  instant_room: "Instant Room",
  live_session: "Scheduled Session",
};

const STATUS_BADGE: Record<string, string> = {
  ended: "badge-gray",
  cancelled: "badge-red",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function formatDuration(startedAt: string | null, endedAt: string | null): string {
  if (!startedAt || !endedAt) return "—";
  const sec = Math.max(0, Math.floor((new Date(endedAt).getTime() - new Date(startedAt).getTime()) / 1000));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m} min.`;
}

function DetailPanel({ row, onClose }: { row: SessionHistoryRow; onClose: () => void }) {
  const { data: detail, isLoading } = useQuery({
    queryKey: ["session-history-detail", row.kind, row.id],
    queryFn: () => adminRoomsApi.historyDetail(row.kind, row.id),
  });

  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Attendance
        </div>
        <button className="btn-ghost" style={{ padding: "2px 8px", fontSize: 11 }} onClick={onClose}>Close</button>
      </div>
      {isLoading ? (
        <div className="center"><div className="spinner" /></div>
      ) : !detail || detail.participants.length === 0 ? (
        <p style={{ fontSize: 12, color: "var(--text-muted)" }}>No attendance recorded.</p>
      ) : (
        detail.participants.map((p) => (
          <div key={`${p.user_id}-${p.joined_at}`} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12.5, padding: "5px 0", borderBottom: "1px solid var(--border)" }}>
            <span style={{ minWidth: 140 }}>{p.name}</span>
            <span style={{ color: "var(--text-muted)" }}>
              {formatDateTime(p.joined_at)}
              {p.left_at && ` → ${new Date(p.left_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`}
            </span>
            <span style={{ color: "var(--text-muted)" }}>{Math.round(p.duration_sec / 60)} min. attended</span>
            <span title="Camera"><MediaStateIcon path={CAMERA_ICON_PATH} active={p.camera_on} /></span>
            <span title="Microphone"><MediaStateIcon path={MIC_ICON_PATH} active={p.mic_on} /></span>
            <span title="Screen share"><MediaStateIcon path={SCREEN_ICON_PATH} active={p.screen_sharing} /></span>
          </div>
        ))
      )}
    </div>
  );
}

export default function SessionHistory() {
  const [page, setPage] = useState(1);
  const [kindFilter, setKindFilter] = useState<"" | "instant_room" | "live_session">("");
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["session-history", page, kindFilter],
    queryFn: () => adminRoomsApi.history(page, pageSize, kindFilter),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Session History</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
            Every past Instant Room and scheduled training session — who attended, who shared their screen, and when.
          </p>
        </div>
        <select
          value={kindFilter}
          onChange={(e) => { setKindFilter(e.target.value as typeof kindFilter); setPage(1); }}
          style={{ width: 200 }}
        >
          <option value="">All kinds</option>
          <option value="instant_room">Instant Rooms only</option>
          <option value="live_session">Scheduled Sessions only</option>
        </select>
      </div>

      {isLoading ? (
        <div className="center"><div className="spinner" /></div>
      ) : !data || data.items.length === 0 ? (
        <div className="card" style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
          Nothing has ended yet.
        </div>
      ) : (
        <>
          {data.items.map((row) => {
            const key = `${row.kind}-${row.id}`;
            const isExpanded = expandedKey === key;
            return (
              <div className="card" key={key} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span className="badge badge-gray">{KIND_LABEL[row.kind] ?? row.kind}</span>
                      <span className={`badge ${STATUS_BADGE[row.status] ?? "badge-gray"}`}>{row.status}</span>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{row.title}</span>
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 4 }}>
                      Hosted by {row.owner_or_host_name} · {formatDateTime(row.started_at)} · ran {formatDuration(row.started_at, row.ended_at)}
                      {" · "}{row.participant_count} participant{row.participant_count === 1 ? "" : "s"}
                      {" · "}peak {row.max_concurrent} at once
                      {row.screen_share_count > 0 && ` · ${row.screen_share_count} shared screen`}
                    </div>
                  </div>
                  <button className="btn-ghost" style={{ padding: "6px 10px", fontSize: 12 }}
                    onClick={() => setExpandedKey(isExpanded ? null : key)}>
                    {isExpanded ? "Hide" : "View attendance"}
                  </button>
                </div>
                {isExpanded && <DetailPanel row={row} onClose={() => setExpandedKey(null)} />}
              </div>
            );
          })}

          {totalPages > 1 && (
            <div className="pagination">
              <button className="btn-ghost" style={{ padding: "4px 10px" }} onClick={() => setPage((p) => p - 1)} disabled={page === 1}>←</button>
              <span>Page {page} of {totalPages} ({data.total} total)</span>
              <button className="btn-ghost" style={{ padding: "4px 10px" }} onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages}>→</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
