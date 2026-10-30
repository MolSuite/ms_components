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
class TaskMonitorState:
    """One task in flight, as `ms_flow.engine.TaskSnapshot` gives it."""
    input: str  # a short repr of the chunk it runs; of the first one when it carries several
    chunks: int = 1
    attempt: int = 1
    seconds: float = 0.0  # since it was handed to its executor
    progress: float | None = None  # percent; None when the task does not say how far it is
    host: str | None = None  # the machine it runs on, where its executor has several


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
    executor: str | None = None  # the name it was submitted to
    status: str = "waiting"
    error: str = ""
    progress: float = 0.0  # percent
    chunks_total: int = 0  # 0 while the source of chunks has not said
    chunks_done: int = 0
    chunks_failed: int = 0
    chunks_running: int = 0  # taken and not settled: running, carried in a task, or being written
    tasks_running: int = 0  # what runs now, one worker each; <= chunks_running
    cpu_used: int = 0  # the CPU tokens those tasks hold
    chunks_retried: int = 0
    peak_mem_mb: int = 0
    usage: dict = field(default_factory=dict)  # what it used, kept once it ended: see ms_flow's JobSnapshot.usage
    throughput_eps: float = 0.0  # chunks settled per second over the last minutes; since it began once it ended
    throughput_history: list[float] = field(default_factory=list)  # the same, one value per few seconds
    started_at: datetime | None = None
    finished_at: datetime | None = None
    tasks: list[TaskMonitorState] = field(default_factory=list)  # read only for the selected job
    chunk_states: bytes | None = None  # a byte per chunk (0 pending, 1 running, 2 done, 3 failed): selected job only

    @property
    def chunks_settled(self) -> int:
        return self.chunks_done + self.chunks_failed

    @property
    def seconds_left(self) -> float | None:
        """At the speed of the last minutes; None when it cannot be said."""
        remaining = self.chunks_total - self.chunks_settled
        if self.is_terminal or self.throughput_eps <= 0 or remaining <= 0:
            return None
        return remaining / self.throughput_eps

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
