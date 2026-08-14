import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { resourceUsageApi, ResourceUsageSample } from "../../api/admin";

function formatBytesPerSec(v: number | null): string {
  if (v === null) return "—";
  if (v < 1024) return `${v.toFixed(0)} B/s`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB/s`;
  return `${(v / (1024 * 1024)).toFixed(2)} MB/s`;
}

function Gauge({ label, pct, sub }: { label: string; pct: number | null; sub?: string }) {
  const value = pct ?? 0;
  const color = value >= 85 ? "var(--danger)" : value >= 60 ? "var(--warning)" : "var(--success)";
  return (
    <div className="card" style={{ flex: 1, minWidth: 160, textAlign: "center" }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>
        {label}
      </div>
      <svg width="100" height="60" viewBox="0 0 100 60">
        <path d="M10 55 A 40 40 0 0 1 90 55" fill="none" stroke="var(--border)" strokeWidth="8" strokeLinecap="round" />
        <path
          d="M10 55 A 40 40 0 0 1 90 55"
          fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={`${Math.min(100, Math.max(0, value)) * 1.257} 200`}
        />
      </svg>
      <div style={{ fontSize: 22, fontWeight: 700, marginTop: -8 }}>{pct === null ? "—" : `${value.toFixed(0)}%`}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 140 }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

// Minimal hand-rolled SVG line chart — no charting library is installed
// in this project, and pulling one in just for this one page isn't worth
// the bundle-size tradeoff at this data volume (a day of ~60s samples is
// ~1440 points at most).
function LineChart({
  samples, field, label, color, formatValue,
}: {
  samples: ResourceUsageSample[];
  field: keyof ResourceUsageSample;
  label: string;
  color: string;
  formatValue?: (v: number) => string;
}) {
  const width = 800;
  const height = 160;
  const padding = 30;

  const points = samples
    .map((s) => ({ t: new Date(s.sampled_at).getTime(), v: s[field] as number | null }))
    .filter((p) => p.v !== null) as { t: number; v: number }[];

  if (points.length < 2) {
    return (
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>{label}</div>
        <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Not enough data yet — check back after a few sampling ticks.</p>
      </div>
    );
  }

  const minT = points[0].t;
  const maxT = points[points.length - 1].t;
  const maxV = Math.max(...points.map((p) => p.v), 1);
  const spanT = Math.max(1, maxT - minT);

  const toX = (t: number) => padding + ((t - minT) / spanT) * (width - 2 * padding);
  const toY = (v: number) => height - padding - (v / maxV) * (height - 2 * padding);

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${toX(p.t).toFixed(1)} ${toY(p.v).toFixed(1)}`).join(" ");
  const latest = points[points.length - 1].v;

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 600 }}>{label}</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          latest: <strong style={{ color: "var(--text)" }}>{formatValue ? formatValue(latest) : latest.toFixed(1)}</strong>
        </div>
      </div>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border)" strokeWidth="1" />
        <path d={pathD} fill="none" stroke={color} strokeWidth="1.75" />
      </svg>
    </div>
  );
}

const RANGE_OPTIONS = [
  { hours: 1, label: "Last hour" },
  { hours: 6, label: "Last 6 hours" },
  { hours: 24, label: "Last 24 hours" },
  { hours: 24 * 7, label: "Last 7 days" },
];

export default function ResourceMonitor() {
  const [rangeHours, setRangeHours] = useState(24);

  const { data: current, isLoading: currentLoading } = useQuery({
    queryKey: ["resource-usage-current"],
    queryFn: () => resourceUsageApi.current(),
    refetchInterval: 15000,
  });

  const { data: history } = useQuery({
    queryKey: ["resource-usage-history", rangeHours],
    queryFn: () => resourceUsageApi.history(rangeHours),
    refetchInterval: 30000,
  });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Resource Monitor</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
            Live server load and LiveKit bandwidth usage. Host CPU/memory reflects this whole machine
            (not just this app), sampled every 60 seconds.
          </p>
        </div>
        <select value={rangeHours} onChange={(e) => setRangeHours(Number(e.target.value))} style={{ width: 180 }}>
          {RANGE_OPTIONS.map((o) => <option key={o.hours} value={o.hours}>{o.label}</option>)}
        </select>
      </div>

      {currentLoading || !current ? (
        <div className="center"><div className="spinner" /></div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
            <Gauge label="Host CPU" pct={current.host_cpu_pct} />
            <Gauge
              label="Host Memory" pct={current.host_memory_pct}
              sub={current.host_memory_used_mb != null && current.host_memory_total_mb != null
                ? `${(current.host_memory_used_mb / 1024).toFixed(1)} / ${(current.host_memory_total_mb / 1024).toFixed(1)} GB`
                : undefined}
            />
            <Gauge label="LiveKit CPU" pct={current.livekit_cpu_pct} sub={current.livekit_memory_mb != null ? `${current.livekit_memory_mb.toFixed(0)} MB RAM` : undefined} />
          </div>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
            <StatCard label="Active rooms/sessions" value={String(current.active_room_count ?? "—")} />
            <StatCard label="Active participants" value={String(current.active_participant_count ?? "—")} />
            <StatCard label="Bandwidth in" value={formatBytesPerSec(current.bandwidth_in_bytes_per_sec)} />
            <StatCard label="Bandwidth out" value={formatBytesPerSec(current.bandwidth_out_bytes_per_sec)} />
          </div>
        </>
      )}

      {history && history.length > 0 && (
        <>
          <LineChart samples={history} field="host_cpu_pct" label="Host CPU (%)" color="#6366f1" formatValue={(v) => `${v.toFixed(0)}%`} />
          <LineChart samples={history} field="host_memory_pct" label="Host Memory (%)" color="#f59e0b" formatValue={(v) => `${v.toFixed(0)}%`} />
          <LineChart samples={history} field="active_participant_count" label="Active participants" color="#10b981" formatValue={(v) => v.toFixed(0)} />
          <LineChart samples={history} field="bandwidth_in_bytes_per_sec" label="Bandwidth in" color="#3b82f6" formatValue={(v) => formatBytesPerSec(v)} />
          <LineChart samples={history} field="bandwidth_out_bytes_per_sec" label="Bandwidth out" color="#ef4444" formatValue={(v) => formatBytesPerSec(v)} />
        </>
      )}
    </div>
  );
}
