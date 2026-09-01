from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


TERMINAL_JOB_STATUSES = {"completed", "failed", "canceled"}


@dataclass(slots=True)
class ChunkMonitorState:
    chunk_id: str
    job_id: str
    status: str = ""
    progress: float = 0.0
    executor_name: str = ""
    error: str = ""
    input_summary: str = ""

    @property
    def short_id(self) -> str:
        return self.chunk_id[:8]


@dataclass(slots=True)
class EventMonitorState:
    event_id: int
    job_id: str
    level: str = ""
    event_type: str = ""
    message: str = ""
    created_at: datetime | None = None


@dataclass(slots=True)
class OutputMonitorState:
    index: int
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LogMonitorState:
    line: str
    source: str = "buffer"


@dataclass(slots=True)
class MonitorActionCapability:
    action: str
    supported: bool
    reason: str = ""


@dataclass(slots=True)
class MonitorSyncState:
    in_progress: bool = False
    last_refresh_at: datetime | None = None
    last_error: str = ""


@dataclass(slots=True)
class ExecutorMonitorState:
    name: str
    backend: str = ""
    mode: str = ""
    shared_fs: bool = False
    integration: str = "unknown"
    remote_backend: bool = False
    local_resource_accounting: str = "none"
    locally_constrained: bool = False
    active_jobs: int = 0
    running_chunks: int = 0
    reserved_cpu: int = 0
    used_cpu: int | None = None
    health: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeHealthState:
    status: str = "inactive"
    active_jobs: int = 0
    loop_latency_ms: float = 0.0
    checks: dict[str, Any] = field(default_factory=dict)
    core_health: dict[str, Any] = field(default_factory=dict)
    persistence_health: dict[str, Any] = field(default_factory=dict)
    sink_health: dict[str, Any] = field(default_factory=dict)
    project_id: str | None = None


@dataclass(slots=True)
class JobMonitorState:
    job_id: str
    project_id: str | None = None
    origin_id: str = ""
    task_type: str = ""
    executor_name: str = ""
    status: str = "pending"
    error: str = ""
    cancel_requested: bool = False
    progress: float = 0.0
    priority: int = 0
    queue_policy: str = "fifo"
    chunks_total: int = 0
    chunks_emitted: int = 0
    chunks_done: int = 0
    chunks_failed: int = 0
    chunks_stage_failed: int = 0
    chunks_running: int = 0
    chunks_pending: int = 0
    chunks_staging: int = 0
    feed_exhausted: bool = True
    feed_cursor_position: int = 0
    feed_items_acked: int = 0
    throughput_eps: float = 0.0
    loop_latency_ms: float = 0.0
    job_queue_wait_s: float | None = None
    chunk_queue_wait_avg_s: float = 0.0
    chunk_queue_wait_max_s: float = 0.0
    updated_at: datetime | None = None
    output_sink: dict[str, Any] | None = None
    chunks: list[ChunkMonitorState] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_JOB_STATUSES


@dataclass(slots=True)
class JobDetailState:
    job_id: str
    job: JobMonitorState | None = None
    events: list[EventMonitorState] = field(default_factory=list)
    outputs: list[OutputMonitorState] = field(default_factory=list)
    logs: list[LogMonitorState] = field(default_factory=list)
    chunks: list[ChunkMonitorState] = field(default_factory=list)


@dataclass(slots=True)
class ResourcePoolState:
    """Global token pool of the local scheduler (CPU always; GPU when total>0)."""
    cpu_total: int = 0
    cpu_used: int = 0
    gpu_total: int = 0
    gpu_used: int = 0


@dataclass(slots=True)
class ProjectMonitorState:
    project_id: str | None = None
    project_name: str = ""
    project_path: str | None = None
    has_project: bool = False
    active: bool = False
    jobs_active: int = 0
    job_ids: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    external_cancellers: int = 0
    executors: list[ExecutorMonitorState] = field(default_factory=list)
    jobs: list[JobMonitorState] = field(default_factory=list)
    chunks: list[ChunkMonitorState] = field(default_factory=list)
    recent_events: list[EventMonitorState] = field(default_factory=list)
    health: RuntimeHealthState | None = None
    resources: ResourcePoolState | None = None
    updated_at: datetime = field(default_factory=datetime.now)
