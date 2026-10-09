from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


TERMINAL_JOB_STATUSES = {"completed", "completed_with_errors", "failed", "canceled", "interrupted"}


@dataclass(slots=True)
class FailureState:
    """One chunk that failed: the attempt that gave up, its traceback and a short repr of its input."""
    attempt: int
    error: str
    input: str = ""


@dataclass(slots=True)
class MonitorSyncState:
    in_progress: bool = False
    last_refresh_at: datetime | None = None
    last_error: str = ""


@dataclass(slots=True)
class JobMonitorState:
    job_id: str  # the key of the job in the project's journal
    engine_id: int | None = None  # its id in this session's engine; None for a job of another session
    name: str = ""
    status: str = "waiting"
    error: str = ""
    progress: float = 0.0  # percent
    chunks_total: int = 0  # 0 while the source of chunks has not said
    chunks_done: int = 0
    chunks_failed: int = 0
    chunks_running: int = 0
    chunks_retried: int = 0
    peak_mem_mb: int = 0
    throughput_eps: float = 0.0
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_JOB_STATUSES


@dataclass(slots=True)
class JobDetailState:
    job_id: str
    job: JobMonitorState | None = None
    failures: list[FailureState] = field(default_factory=list)


@dataclass(slots=True)
class ProjectMonitorState:
    project_id: str | None = None
    project_name: str = ""
    project_path: str | None = None
    has_project: bool = False
    active: bool = False
    jobs_active: int = 0
    external_cancellers: int = 0
    jobs: list[JobMonitorState] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.now)
