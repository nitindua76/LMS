"""
Admin Resource Monitor — live gauges + historical chart backing
services/resource_monitor.py's periodic sampling. See that module's
docstring for exactly what "host CPU/memory" means on this deployment
(the shared Docker Desktop VM, not a container-isolated view) and where
the bandwidth/room/participant numbers come from (LiveKit's own
Prometheus endpoint).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models.resource_usage import ResourceUsageSample
from app.models.user import User
from app.schemas.resource_usage import ResourceUsageSampleRead, ResourceUsageHistory
from app.services.resource_monitor import take_sample

router = APIRouter(prefix="/admin/resource-usage", tags=["admin-resource-usage"])


@router.get("/current", response_model=ResourceUsageSampleRead)
def get_current_usage(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    On-demand fresh sample for the live-gauges view — deliberately does
    NOT just return the last scheduler-taken row, since an admin looking
    at this page wants what's happening right now, not up to 60s stale.
    Still writes the sample to the history table like every scheduled
    tick, so manually refreshing this page also densifies the chart.
    """
    return take_sample(db)


@router.get("/history", response_model=ResourceUsageHistory)
def get_usage_history(
    hours: int = Query(24, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Historical samples for the chart — default last 24 hours, capped at
    30 days (this table isn't pruned, but a chart with a month of ~60s
    samples is already the practical upper bound before it stops being
    readable anyway)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        db.query(ResourceUsageSample)
        .filter(ResourceUsageSample.sampled_at >= since)
        .order_by(ResourceUsageSample.sampled_at.asc())
        .all()
    )
    return ResourceUsageHistory(samples=rows)
