from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ms_flow.core.executor.job_snapshot import JobSnapshot

from ms_components.ms_monitor.models import (
    ChunkMonitorState,
    ExecutorMonitorState,
    EventMonitorState,
    JobMonitorState,
    ProjectMonitorState,
    ResourcePoolState,
    RuntimeHealthState,
)


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _coerce_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _field(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _normalize_health_state(raw: Any) -> RuntimeHealthState:
    payload = raw if isinstance(raw, dict) else {}
    return RuntimeHealthState(
        status=_coerce_str(payload.get("status"), "inactive"),
        active_jobs=_coerce_int(payload.get("active_jobs"), 0),
        loop_latency_ms=_coerce_float(payload.get("loop_latency_ms"), 0.0),
        checks=dict(payload.get("checks", {}) or {}),
        core_health=dict(payload.get("core_health", {}) or {}),
        persistence_health=dict(payload.get("persistence_health", {}) or {}),
        sink_health=dict(payload.get("sink_health", {}) or {}),
        project_id=payload.get("project_id"),
    )


def _normalize_executor_state(name: str, raw: Any) -> ExecutorMonitorState:
    payload = raw if isinstance(raw, dict) else {}
    return ExecutorMonitorState(
        name=name,
        backend=_coerce_str(payload.get("backend")),
        mode=_coerce_str(payload.get("mode")),
        shared_fs=_coerce_bool(payload.get("shared_fs"), False),
        integration=_coerce_str(payload.get("integration"), "unknown") or "unknown",
        remote_backend=_coerce_bool(payload.get("remote_backend"), False),
        local_resource_accounting=_coerce_str(payload.get("local_resource_accounting"), "none") or "none",
        locally_constrained=_coerce_bool(payload.get("locally_constrained"), False),
        active_jobs=_coerce_int(payload.get("active_jobs"), 0),
        running_chunks=_coerce_int(payload.get("running_chunks"), 0),
        reserved_cpu=_coerce_int(payload.get("reserved_cpu"), 0),
        used_cpu=_coerce_int(payload.get("used_cpu"), 0) if payload.get("used_cpu") is not None else None,
        health=dict(payload.get("health", {}) or {}),
    )


def _normalize_chunk_state(raw: Any) -> ChunkMonitorState | None:
    chunk_id = _coerce_str(_field(raw, "chunk_id"))
    job_id = _coerce_str(_field(raw, "job_id"))
    if not chunk_id or not job_id:
        return None
    return ChunkMonitorState(
        chunk_id=chunk_id,
        job_id=job_id,
        status=_coerce_str(_field(raw, "status")),
        progress=_coerce_float(_field(raw, "progress"), 0.0),
        executor_name=_coerce_str(_field(raw, "executor_name")),
        error=_coerce_str(_field(raw, "error")),
    )


def _normalize_event_state(raw: Any) -> EventMonitorState | None:
    event_id = _coerce_int(_field(raw, "event_id"), 0)
    if event_id <= 0:
        return None
    return EventMonitorState(
        event_id=event_id,
        job_id=_coerce_str(_field(raw, "job_id")),
        level=_coerce_str(_field(raw, "level")),
        event_type=_coerce_str(_field(raw, "event_type")),
        message=_coerce_str(_field(raw, "message")),
        created_at=_field(raw, "created_at"),
    )


def _normalize_job_state(
    raw: JobSnapshot | dict[str, Any] | Any,
    *,
    cancel_requested_job_ids: set[str],
) -> JobMonitorState | None:
    job_id = _coerce_str(_field(raw, "job_id"))
    if not job_id:
        return None
    return JobMonitorState(
        job_id=job_id,
        project_id=_field(raw, "project_id"),
        origin_id=_coerce_str(_field(raw, "origin_id")),
        task_type=_coerce_str(_field(raw, "task_type")),
        executor_name=_coerce_str(_field(raw, "executor_name")),
        status=_coerce_str(_field(raw, "status"), "pending") or "pending",
        error=_coerce_str(_field(raw, "error")),
        cancel_requested=_coerce_bool(_field(raw, "cancel_requested"), False) or job_id in cancel_requested_job_ids,
        progress=_coerce_float(_field(raw, "progress"), 0.0),
        priority=_coerce_int(_field(raw, "priority"), 0),
        queue_policy=_coerce_str(_field(raw, "queue_policy"), "fifo") or "fifo",
        chunks_total=_coerce_int(_field(raw, "chunks_total"), 0),
        chunks_emitted=_coerce_int(_field(raw, "chunks_emitted"), 0),
        chunks_done=_coerce_int(_field(raw, "chunks_done"), 0),
        chunks_failed=_coerce_int(_field(raw, "chunks_failed"), 0),
        chunks_stage_failed=_coerce_int(_field(raw, "chunks_stage_failed"), 0),
        chunks_running=_coerce_int(_field(raw, "chunks_running"), 0),
        chunks_pending=_coerce_int(_field(raw, "chunks_pending"), 0),
        chunks_staging=_coerce_int(_field(raw, "chunks_staging"), 0),
        feed_exhausted=_coerce_bool(_field(raw, "feed_exhausted"), True),
        feed_cursor_position=_coerce_int(_field(raw, "feed_cursor_position"), 0),
        feed_items_acked=_coerce_int(_field(raw, "feed_items_acked"), 0),
        throughput_eps=_coerce_float(_field(raw, "throughput_eps"), 0.0),
        loop_latency_ms=_coerce_float(_field(raw, "loop_latency_ms"), 0.0),
        job_queue_wait_s=(
            _coerce_float(_field(raw, "job_queue_wait_s"), 0.0)
            if _field(raw, "job_queue_wait_s") is not None
            else None
        ),
        chunk_queue_wait_avg_s=_coerce_float(_field(raw, "chunk_queue_wait_avg_s"), 0.0),
        chunk_queue_wait_max_s=_coerce_float(_field(raw, "chunk_queue_wait_max_s"), 0.0),
        updated_at=_field(raw, "updated_at"),
        output_sink=dict(_field(raw, "output_sink", {}) or {}) if _field(raw, "output_sink") is not None else None,
    )


class _MonitorRuntimeBackend:
    def __init__(self, molsuite) -> None:
        self._molsuite = molsuite

    @property
    def manager(self):
        return getattr(self._molsuite, "executor_manager", None)

    def get_project_activity(self) -> dict[str, Any]:
        activity = self._molsuite.get_project_activity()
        return dict(activity or {})

    def get_health_state(self) -> RuntimeHealthState:
        return _normalize_health_state(self._molsuite.get_runtime_healthcheck())

    def get_executor_states(self) -> list[ExecutorMonitorState]:
        manager = self.manager
        if manager is None:
            return []
        status = manager.get_status()
        if not isinstance(status, dict):
            return []
        executors = status.get("executors", {}) or {}
        return [
            _normalize_executor_state(name, executors.get(name))
            for name in sorted(executors.keys())
        ]

    def get_resource_pool(self) -> ResourcePoolState:
        manager = self.manager
        if manager is None:
            return ResourcePoolState()
        status = manager.get_status()
        if not isinstance(status, dict):
            return ResourcePoolState()
        cpu = status.get("cpu", {}) or {}
        gpu = status.get("gpu", {}) or {}
        return ResourcePoolState(
            cpu_total=_coerce_int(cpu.get("total")),
            cpu_used=_coerce_int(cpu.get("used")),
            gpu_total=_coerce_int(gpu.get("total")),
            gpu_used=_coerce_int(gpu.get("used")),
        )

    def list_job_snapshots(self, *, project_id: str | None, max_recent_jobs: int) -> list[JobSnapshot | Any]:
        manager = self.manager
        if manager is None or project_id is None:
            return []
        summaries = list(manager.list_jobs())
        project_rows = [
            item
            for item in summaries
            if _coerce_str(_field(item, "project_id")) == project_id
        ]
        return project_rows[:max_recent_jobs]

    def get_job_snapshot(self, job_id: str) -> JobSnapshot | Any | None:
        manager = self.manager
        if manager is None:
            return None
        return manager.get_job(job_id)

    def list_live_chunks(self, *, job_ids: list[str]) -> list[ChunkMonitorState]:
        if not job_ids:
            return []
        rows = self._molsuite.get_job_chunks(
            job_ids=job_ids,
            statuses=("running", "staging", "pending"),
        )
        chunks = [chunk for row in rows if (chunk := _normalize_chunk_state(row)) is not None]
        chunks.sort(key=lambda item: (item.status != "running", item.job_id, item.chunk_id))
        return chunks

    def list_recent_events(
        self,
        *,
        after_event_id: int,
        limit: int = 200,
    ) -> list[EventMonitorState]:
        rows = self._molsuite.get_job_event_records(
            after_event_id=after_event_id,
            limit=limit,
        )
        return [event for row in rows if (event := _normalize_event_state(row)) is not None]


class MolSuiteMonitorPoller(QObject):
    project_changed = Signal(object)
    project_cleared = Signal()
    project_snapshot_updated = Signal(object)
    job_upserted = Signal(str, object)
    job_removed = Signal(str)
    job_finished = Signal(str, str)
    executors_updated = Signal(object)
    health_updated = Signal(object)
    events_updated = Signal(object)
    bridge_error = Signal(str)

    def __init__(
        self,
        *,
        molsuite,
        poll_ms: int = 500,
        max_recent_jobs: int = 20,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._molsuite = molsuite
        self._backend = _MonitorRuntimeBackend(molsuite)
        self._poll_ms = max(100, poll_ms)
        # Only poll fast while jobs are active; back off hard when idle so the monitor isn't
        # running healthchecks/executor queries twice a second for nothing.
        self._active_poll_ms = self._poll_ms
        self._idle_poll_ms = max(self._poll_ms, 3000)
        self._max_recent_jobs = max(5, max_recent_jobs)
        self._timer: QTimer | None = None
        self._current_project_id: str | None = None
        self._last_snapshot: ProjectMonitorState | None = None
        self._job_cache: dict[str, JobMonitorState] = {}
        self._last_health: RuntimeHealthState | None = None
        self._last_executors: list[ExecutorMonitorState] = []
        self._last_event_id: int = 0
        self._recent_events: list[EventMonitorState] = []

    @property
    def current_snapshot(self) -> ProjectMonitorState | None:
        return self._last_snapshot

    @Slot()
    def start_polling(self) -> None:
        if self._timer is not None:
            return
        self._timer = QTimer(self)
        self._timer.setInterval(self._poll_ms)
        self._timer.timeout.connect(self.poll_once)
        self._timer.start()
        self.poll_once()

    @Slot()
    def stop_polling(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

    @Slot()
    def poll_once(self) -> None:
        try:
            snapshot = self._build_snapshot()
            self._emit_snapshot(snapshot)
            self._adjust_interval(snapshot)
        except Exception as exc:
            self.bridge_error.emit(str(exc))

    def _adjust_interval(self, snapshot: ProjectMonitorState | None) -> None:
        if self._timer is None:
            return
        active = snapshot is not None and int(getattr(snapshot, "jobs_active", 0) or 0) > 0
        desired = self._active_poll_ms if active else self._idle_poll_ms
        if self._timer.interval() != desired:
            self._timer.setInterval(desired)

    def _emit_snapshot(self, snapshot: ProjectMonitorState) -> None:
        previous_project_id = self._current_project_id
        current_project_id = snapshot.project_id

        if current_project_id != previous_project_id:
            self._job_cache.clear()
            self._recent_events = []
            self._last_event_id = 0
            if current_project_id is None:
                if previous_project_id is not None:
                    self.project_cleared.emit()
            else:
                self.project_changed.emit(snapshot)
            self._current_project_id = current_project_id

        if snapshot.health != self._last_health:
            self.health_updated.emit(snapshot.health)
            self._last_health = snapshot.health

        if snapshot.executors != self._last_executors:
            self.executors_updated.emit(snapshot.executors)
            self._last_executors = list(snapshot.executors)

        previous_events = self._last_snapshot.recent_events if self._last_snapshot is not None else []
        if snapshot.recent_events != previous_events:
            self.events_updated.emit(snapshot.recent_events)

        current_jobs = {job.job_id: job for job in snapshot.jobs}
        previous_jobs = dict(self._job_cache)

        for job_id, state in current_jobs.items():
            prev = previous_jobs.get(job_id)
            if prev != state:
                self.job_upserted.emit(job_id, state)
            if state.is_terminal and (prev is None or prev.status != state.status):
                self.job_finished.emit(job_id, state.status)

        for job_id in previous_jobs:
            if job_id not in current_jobs:
                self.job_removed.emit(job_id)

        self._job_cache = current_jobs
        self._last_snapshot = snapshot
        self.project_snapshot_updated.emit(snapshot)

    def _build_snapshot(self) -> ProjectMonitorState:
        molsuite = self._molsuite
        context = getattr(molsuite, "active_context", None)
        activity = self._backend.get_project_activity()
        health = self._backend.get_health_state()
        project_id = activity.get("project_id")

        if project_id != self._current_project_id:
            self._recent_events = []
            self._last_event_id = 0

        # Executors and the token pool belong to the runtime, not to a project:
        # they must be visible (and operable) with no project open.
        executors = self._backend.get_executor_states()
        resources = self._backend.get_resource_pool()
        jobs: list[JobMonitorState] = []
        chunks: list[ChunkMonitorState] = []
        recent_events: list[EventMonitorState] = []
        if context is not None and project_id is not None:
            recent_events = self._update_recent_events()
            jobs = self._build_jobs(
                project_id=project_id,
                activity=activity,
                recent_events=recent_events,
            )
            chunks = self._build_live_chunks(
                job_ids=[job.job_id for job in jobs if not job.is_terminal]
            )
            chunk_map: dict[str, list] = {}
            for chunk in chunks:
                chunk_map.setdefault(chunk.job_id, []).append(chunk)
            for job in jobs:
                job.chunks = chunk_map.get(job.job_id, [])

        project_name = getattr(context, "name", "") if context is not None else ""
        project_path = str(getattr(context, "path", "")) if context is not None else None
        has_project = context is not None and project_id is not None
        return ProjectMonitorState(
            project_id=project_id,
            project_name=project_name,
            project_path=project_path,
            has_project=has_project,
            active=bool(activity.get("active", False)),
            jobs_active=int(activity.get("jobs_active", 0) or 0),
            job_ids=list(activity.get("job_ids", []) or []),
            statuses=list(activity.get("statuses", []) or []),
            external_cancellers=int(activity.get("external_cancellers", 0) or 0),
            executors=executors,
            jobs=jobs,
            chunks=chunks,
            recent_events=recent_events,
            health=health,
            resources=resources,
            updated_at=datetime.now(),
        )

    def _build_jobs(
        self,
        *,
        project_id: str,
        activity: dict[str, Any],
        recent_events: list[EventMonitorState],
    ) -> list[JobMonitorState]:
        summaries = self._backend.list_job_snapshots(
            project_id=project_id,
            max_recent_jobs=self._max_recent_jobs,
        )

        active_ids = list(activity.get("job_ids", []) or [])
        candidate_ids: list[str] = []
        seen: set[str] = set()
        for job_id in active_ids:
            if job_id not in seen:
                candidate_ids.append(job_id)
                seen.add(job_id)
        for item in summaries[: self._max_recent_jobs]:
            job_id = _coerce_str(_field(item, "job_id"))
            if not job_id or job_id in seen:
                continue
            candidate_ids.append(job_id)
            seen.add(job_id)

        result: list[JobMonitorState] = []
        cancel_requested_job_ids = {
            event.job_id
            for event in recent_events
            if event.event_type == "job_cancel_requested" and event.job_id
        }
        for job_id in candidate_ids:
            state = _normalize_job_state(
                self._backend.get_job_snapshot(job_id),
                cancel_requested_job_ids=cancel_requested_job_ids,
            )
            if state is None:
                continue
            result.append(state)
        result.sort(
            key=lambda item: (
                1 if item.is_terminal else 0,
                -(item.updated_at.timestamp() if item.updated_at is not None else 0.0),
            ),
            reverse=False,
        )
        active_rows = sorted(
            [item for item in result if not item.is_terminal],
            key=lambda item: item.updated_at.timestamp() if item.updated_at is not None else 0.0,
            reverse=True,
        )
        terminal_rows = sorted(
            [item for item in result if item.is_terminal],
            key=lambda item: item.updated_at.timestamp() if item.updated_at is not None else 0.0,
            reverse=True,
        )
        return active_rows + terminal_rows

    def _build_live_chunks(self, *, job_ids: list[str]) -> list:
        return self._backend.list_live_chunks(job_ids=job_ids)

    def _update_recent_events(self) -> list[EventMonitorState]:
        rows = self._backend.list_recent_events(after_event_id=self._last_event_id, limit=200)
        if rows:
            for event in rows:
                self._recent_events.append(event)
                self._last_event_id = max(self._last_event_id, event.event_id)
            self._recent_events = self._recent_events[-200:]
        return list(self._recent_events)
