from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class ResourceUsageSampleRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    sampled_at: datetime
    host_cpu_pct: Optional[float] = None
    host_memory_pct: Optional[float] = None
    host_memory_used_mb: Optional[float] = None
    host_memory_total_mb: Optional[float] = None
    livekit_cpu_pct: Optional[float] = None
    livekit_memory_mb: Optional[float] = None
    bandwidth_in_bytes_per_sec: Optional[float] = None
    bandwidth_out_bytes_per_sec: Optional[float] = None
    active_room_count: Optional[int] = None
    active_participant_count: Optional[int] = None


class ResourceUsageHistory(BaseModel):
    samples: List[ResourceUsageSampleRead]
