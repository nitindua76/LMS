"""
Resource usage monitoring — periodic snapshots of host CPU/memory (via
psutil, in the api container) and LiveKit's own Prometheus metrics
(bandwidth, active room/participant counts, its own process CPU/memory),
stored as ResourceUsageSample rows for the admin Resource Monitor page.

Two things worth being explicit about, verified against the ACTUAL running
stack rather than assumed from docs:

1. "Host CPU/memory" here means the Docker Desktop VM this whole compose
   stack runs in (confirmed via `cat /sys/fs/cgroup/memory.max` returning
   "No such file" — no cgroup limits are set on this container, so psutil
   reads the shared VM's /proc, not a container-scoped view). On a single-
   purpose host mostly running this stack, that's still a meaningful
   number; it is NOT "just the api process's own usage," and callers must
   not present it as if it were container-isolated.

2. LiveKit's Prometheus endpoint (enabled via livekit.yaml's
   `prometheus.port: 6789`, confirmed reachable at http://livekit:6789/metrics
   from the api container over the internal compose network — never
   published to the host) exposes standard process_cpu_seconds_total /
   process_resident_memory_bytes for LiveKit's own process, plus
   livekit_packet_bytes{direction="incoming"|"outgoing"} (cumulative byte
   counters) and livekit_room_total / livekit_participant_total. Bandwidth
   is a COUNTER, not a gauge — actual bytes/sec requires diffing two
   samples over the known time between them, which is what
   _compute_bandwidth_rate does below using the previous DB row.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
import psutil
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.resource_usage import ResourceUsageSample

logger = logging.getLogger(__name__)

_METRIC_LINE_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}\s+([0-9.eE+-]+)\s*$')
_METRIC_LINE_NO_LABELS_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)\s+([0-9.eE+-]+)\s*$')


def _parse_prometheus_text(text: str) -> dict[str, list[tuple[dict[str, str], float]]]:
    """
    Minimal Prometheus text-format parser — just enough to pull the handful
    of metrics this module cares about (no external dependency needed for
    that). Returns {metric_name: [(labels_dict, value), ...]}; a metric
    with no labels gets an empty labels_dict.
    """
    out: dict[str, list[tuple[dict[str, str], float]]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _METRIC_LINE_RE.match(line)
        if m:
            name, label_str, value_str = m.groups()
            labels = {}
            for pair in re.findall(r'(\w+)="([^"]*)"', label_str):
                labels[pair[0]] = pair[1]
            try:
                out.setdefault(name, []).append((labels, float(value_str)))
            except ValueError:
                continue
            continue
        m2 = _METRIC_LINE_NO_LABELS_RE.match(line)
        if m2:
            name, value_str = m2.groups()
            try:
                out.setdefault(name, []).append(({}, float(value_str)))
            except ValueError:
                continue
    return out


def _sum_metric(metrics: dict, name: str, label_filter: Optional[dict[str, str]] = None) -> Optional[float]:
    rows = metrics.get(name)
    if not rows:
        return None
    total = 0.0
    matched = False
    for labels, value in rows:
        if label_filter and any(labels.get(k) != v for k, v in label_filter.items()):
            continue
        total += value
        matched = True
    return total if matched else None


def _fetch_livekit_metrics() -> Optional[dict]:
    url = f"http://livekit:{settings.LIVEKIT_PROMETHEUS_PORT}/metrics"
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        return _parse_prometheus_text(resp.text)
    except httpx.HTTPError as exc:
        logger.warning("Could not reach LiveKit metrics endpoint at %s: %s", url, exc)
        return None


def _host_stats() -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    try:
        cpu_pct = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        return cpu_pct, mem.percent, mem.used / (1024 * 1024), mem.total / (1024 * 1024)
    except Exception:
        logger.exception("Failed to read host CPU/memory via psutil")
        return None, None, None, None


def _compute_bandwidth_rate(
    bytes_in: Optional[float], bytes_out: Optional[float], now: datetime,
) -> tuple[Optional[float], Optional[float]]:
    """Bandwidth counters are cumulative since LiveKit started — diff
    against the last raw counter values seen by THIS process (tracked
    in-memory by _RATE_STATE, not read back from the DB — we only persist
    the computed rate, not the raw counters, so there's nothing to recover
    from prior rows) to get a bytes/sec rate. Returns (None, None) for the
    very first sample after an api restart, or if the counters reset
    (e.g. LiveKit itself restarted, new value < old)."""
    if bytes_in is None or bytes_out is None:
        return None, None
    return _RATE_STATE.compute(bytes_in, bytes_out, now)


class _RateState:
    """In-process cache of the last raw (cumulative) counter values and
    when they were observed — reset on api restart, which just means the
    first sample after a restart reports no rate (None) rather than a
    wrong one. Deliberately not persisted; storing every raw counter would
    need its own columns for no real benefit over this."""

    def __init__(self):
        self._last_in: Optional[float] = None
        self._last_out: Optional[float] = None
        self._last_time: Optional[datetime] = None

    def compute(self, bytes_in: float, bytes_out: float, now: datetime) -> tuple[Optional[float], Optional[float]]:
        rate_in = rate_out = None
        if self._last_time is not None:
            elapsed = (now - self._last_time).total_seconds()
            if elapsed > 0 and bytes_in >= self._last_in and bytes_out >= self._last_out:
                rate_in = (bytes_in - self._last_in) / elapsed
                rate_out = (bytes_out - self._last_out) / elapsed
        self._last_in, self._last_out, self._last_time = bytes_in, bytes_out, now
        return rate_in, rate_out


_RATE_STATE = _RateState()


def take_sample(db: Session) -> ResourceUsageSample:
    now = datetime.now(timezone.utc)
    host_cpu, host_mem_pct, host_mem_used, host_mem_total = _host_stats()

    metrics = _fetch_livekit_metrics()
    livekit_cpu_pct = None
    livekit_mem_mb = None
    bytes_in = bytes_out = None
    room_count = participant_count = None

    if metrics is not None:
        cpu_seconds = _sum_metric(metrics, "process_cpu_seconds_total")
        # process_cpu_seconds_total is also cumulative — same rate-over-
        # time treatment as bandwidth, reusing the same elapsed-time
        # tracking via _RATE_STATE would conflate two different counters,
        # so this one is tracked separately and inline (simpler than a
        # second _RateState instance for one value).
        livekit_cpu_pct = _livekit_cpu_rate(cpu_seconds, now)
        resident_bytes = _sum_metric(metrics, "process_resident_memory_bytes")
        livekit_mem_mb = resident_bytes / (1024 * 1024) if resident_bytes is not None else None

        bytes_in = _sum_metric(metrics, "livekit_packet_bytes", {"direction": "incoming"})
        bytes_out = _sum_metric(metrics, "livekit_packet_bytes", {"direction": "outgoing"})
        room_count_raw = _sum_metric(metrics, "livekit_room_total")
        room_count = int(room_count_raw) if room_count_raw is not None else None
        participant_count_raw = _sum_metric(metrics, "livekit_participant_total")
        participant_count = int(participant_count_raw) if participant_count_raw is not None else None

    rate_in, rate_out = _compute_bandwidth_rate(bytes_in, bytes_out, now)

    sample = ResourceUsageSample(
        sampled_at=now,
        host_cpu_pct=host_cpu, host_memory_pct=host_mem_pct,
        host_memory_used_mb=host_mem_used, host_memory_total_mb=host_mem_total,
        livekit_cpu_pct=livekit_cpu_pct, livekit_memory_mb=livekit_mem_mb,
        bandwidth_in_bytes_per_sec=rate_in, bandwidth_out_bytes_per_sec=rate_out,
        active_room_count=room_count, active_participant_count=participant_count,
    )
    db.add(sample)
    db.commit()
    return sample


class _CpuRateState:
    """Same cumulative-counter-to-rate pattern as _RateState, but for
    LiveKit's own process_cpu_seconds_total -> a 0-100 CPU percent."""

    def __init__(self):
        self._last_seconds: Optional[float] = None
        self._last_time: Optional[datetime] = None

    def compute(self, cpu_seconds: Optional[float], now: datetime) -> Optional[float]:
        if cpu_seconds is None:
            return None
        pct = None
        if self._last_time is not None and self._last_seconds is not None:
            elapsed = (now - self._last_time).total_seconds()
            delta = cpu_seconds - self._last_seconds
            if elapsed > 0 and delta >= 0:
                pct = min(100.0, (delta / elapsed) * 100.0)
        self._last_seconds, self._last_time = cpu_seconds, now
        return pct


_CPU_RATE_STATE = _CpuRateState()


def _livekit_cpu_rate(cpu_seconds: Optional[float], now: datetime) -> Optional[float]:
    return _CPU_RATE_STATE.compute(cpu_seconds, now)


def _run_once() -> None:
    db = SessionLocal()
    try:
        take_sample(db)
    except Exception:
        logger.exception("resource_monitor sampling tick failed")
    finally:
        db.close()


_scheduler: Optional[BackgroundScheduler] = None
_SAMPLE_INTERVAL_SECONDS = 60


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_once, "interval", seconds=_SAMPLE_INTERVAL_SECONDS,
        id="resource_monitor_tick", max_instances=1,
    )
    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
