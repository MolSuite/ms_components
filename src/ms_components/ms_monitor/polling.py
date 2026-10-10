from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ms_components.ms_monitor.models import JobMonitorState, ProjectMonitorState, TaskMonitorState


def job_state(job, now: float) -> JobMonitorState:
    """A `ms_flow.engine.JobSnapshot` as the monitor shows it."""
    settled = job.chunks_done + job.chunks_failed
    elapsed = (job.finished_at or now) - job.started_at
    return JobMonitorState(
        job_id=job.key,
        engine_id=job.id,
        name=job.name,
        status=job.status,
        error=job.error or "",
        progress=100.0 * (job.progress or 0.0),
        chunks_total=job.chunks_total or 0,
        chunks_done=job.chunks_done,
        chunks_failed=job.chunks_failed,
        chunks_running=job.chunks_inflight,
        chunks_retried=job.chunks_retried,
        peak_mem_mb=job.peak_mem_mb,
        # ponytail: the mean since the job started, not the rate right now; a rate over the
        # last polls if an ETA that lags misleads.
        throughput_eps=settled / elapsed if elapsed > 0 else 0.0,
        started_at=datetime.fromtimestamp(job.started_at),
        finished_at=datetime.fromtimestamp(job.finished_at) if job.finished_at else None,
    )


class MolSuiteMonitorPoller(QObject):
    project_changed = Signal(object)
    project_cleared = Signal()
    project_snapshot_updated = Signal(object)
    job_upserted = Signal(str, object)
    job_removed = Signal(str)
    job_finished = Signal(str, str)
    bridge_error = Signal(str)

    def __init__(
        self,
        *,
        workspace,
        poll_ms: int = 500,
        max_recent_jobs: int = 20,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        # Only poll fast while jobs are active; back off hard when idle.
        self._active_poll_ms = max(100, poll_ms)
        self._idle_poll_ms = max(self._active_poll_ms, 3000)
        self._max_recent_jobs = max(5, max_recent_jobs)
        self._timer: QTimer | None = None
        self._current_project_id: str | None = None
        self._last_snapshot: ProjectMonitorState | None = None
        self._job_cache: dict[str, JobMonitorState] = {}
        self.unfolded: frozenset[str] = frozenset()  # the jobs whose tasks in flight are asked for

    @property
    def current_snapshot(self) -> ProjectMonitorState | None:
        return self._last_snapshot

    @Slot()
    def start_polling(self) -> None:
        if self._timer is not None:
            return
        self._timer = QTimer(self)
        self._timer.setInterval(self._active_poll_ms)
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
            if self._timer is not None:
                self._timer.setInterval(self._active_poll_ms if snapshot.jobs_active else self._idle_poll_ms)
        except Exception as exc:
            self.bridge_error.emit(str(exc))

    def _emit_snapshot(self, snapshot: ProjectMonitorState) -> None:
        previous_project_id = self._current_project_id
        if snapshot.project_id != previous_project_id:
            self._job_cache.clear()
            if snapshot.project_id is not None:
                self.project_changed.emit(snapshot)
            elif previous_project_id is not None:
                self.project_cleared.emit()
            self._current_project_id = snapshot.project_id

        current_jobs = {job.job_id: job for job in snapshot.jobs}
        previous_jobs = self._job_cache
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
        workspace = self._workspace
        context = workspace.active_context
        activity = workspace.get_project_activity()
        now = time.time()
        # Live state comes from the engine's memory, history from the project's journal;
        # `jobs()` merges both and gives them oldest first.
        jobs = [job_state(job, now) for job in workspace.jobs(self._max_recent_jobs)][::-1]
        jobs.sort(key=lambda job: job.is_terminal)  # stable: active first, newest first in each
        for job in jobs:
            if job.job_id in self.unfolded and not job.is_terminal:
                job.tasks = [
                    TaskMonitorState(task.input, task.chunks, task.attempt, task.seconds,
                                     None if task.progress is None else 100.0 * task.progress)
                    for task in workspace.job_tasks(job.engine_id)
                ]
        project_id = activity.get("project_id") if context is not None else None
        return ProjectMonitorState(
            project_id=project_id,
            project_name=context.name if context is not None else "",
            project_path=str(context.path) if context is not None else None,
            has_project=project_id is not None,
            active=bool(activity.get("active", False)),
            jobs_active=sum(not job.is_terminal for job in jobs),
            external_cancellers=int(activity.get("external_cancellers", 0) or 0),
            jobs=jobs,
            updated_at=datetime.now(),
        )
