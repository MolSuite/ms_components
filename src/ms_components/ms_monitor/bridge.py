from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QMetaObject, QObject, QThread, Qt, Signal

from ms_components.ms_monitor.config import MonitorConfig
from ms_components.ms_monitor.models import (
    FailureState,
    JobDetailState,
    JobMonitorState,
    MonitorSyncState,
    ProjectMonitorState,
)
from ms_components.ms_monitor.polling import MolSuiteMonitorPoller


class MolSuiteMonitorBridge(QObject):
    project_changed = Signal(object)
    project_cleared = Signal()
    project_snapshot_updated = Signal(object)
    job_upserted = Signal(str, object)
    job_removed = Signal(str)
    job_finished = Signal(str, str)
    bridge_error = Signal(str)
    sync_state_updated = Signal(object)
    operator_action_succeeded = Signal(str, str)
    operator_action_failed = Signal(str, str)

    def __init__(
        self,
        *,
        workspace,
        poll_ms: int = MonitorConfig.model_fields["poll_ms"].default,
        max_recent_jobs: int = MonitorConfig.model_fields["max_recent_jobs"].default,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._poll_ms = poll_ms
        self._max_recent_jobs = max_recent_jobs
        self._thread: QThread | None = None
        self._poller = MolSuiteMonitorPoller(
            workspace=workspace,
            poll_ms=poll_ms,
            max_recent_jobs=max_recent_jobs,
        )
        self._sync_state = MonitorSyncState()
        self._connect_poller(self._poller)

    @property
    def current_snapshot(self) -> ProjectMonitorState | None:
        return self._poller.current_snapshot

    @property
    def workspace(self):
        return self._workspace

    @property
    def sync_state(self) -> MonitorSyncState:
        return self._sync_state

    def start(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = QThread(self)
        self._poller.moveToThread(self._thread)
        self._thread.started.connect(self._poller.start_polling)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMetaObject.invokeMethod(self._poller, "stop_polling", Qt.BlockingQueuedConnection)
            self._thread.quit()
            self._thread.wait(2000)
        self._thread = None

    def resync_now(self) -> ProjectMonitorState | None:
        return self.refresh_now()

    def request_refresh(self) -> None:
        self._set_sync_state(in_progress=True, last_error="")
        if self._thread is not None and self._thread.isRunning():
            QMetaObject.invokeMethod(self._poller, "poll_once", Qt.QueuedConnection)
            return
        try:
            self._poller.poll_once()
        finally:
            self._set_sync_state(in_progress=False, last_refresh_at=datetime.now())

    def refresh_now(self) -> ProjectMonitorState | None:
        self._set_sync_state(in_progress=True, last_error="")
        if self._thread is not None and self._thread.isRunning():
            QMetaObject.invokeMethod(self._poller, "poll_once", Qt.BlockingQueuedConnection)
        else:
            self._poller.poll_once()
        self._set_sync_state(in_progress=False, last_refresh_at=datetime.now())
        return self._poller.current_snapshot

    def get_job_detail(self, job_id: str | None, *, failure_limit: int = 200) -> JobDetailState | None:
        """The job as last polled plus its failed chunks, read from the project's journal."""
        if not job_id:
            return None
        job = self._visible_job(job_id)
        failures: list[FailureState] = []
        if job is not None and job.chunks_failed:
            failures = [
                FailureState(int(row["attempt"]), str(row["error"] or ""), str(row.get("input") or ""))
                for row in self._workspace.job_failures(job_id, failure_limit)
            ]
        return JobDetailState(job_id=job_id, job=job, failures=failures)

    def cancel_job(self, job_id: str) -> bool:
        job = self._visible_job(job_id) or self._visible_job(job_id, refresh=True)
        if job is None:
            self._emit_action_failed("cancel_job", f"Job '{job_id}' is not visible in the current monitor snapshot.")
            return False
        if job.is_terminal:
            self._emit_action_failed("cancel_job", f"Job '{job_id}' is already terminal.")
            return False
        if job.engine_id is None:
            self._emit_action_failed("cancel_job", f"Job '{job_id}' runs in another process; cancel it there.")
            return False
        try:
            self._workspace.engine.cancel(job.engine_id)
        except Exception as exc:
            self._emit_action_failed("cancel_job", str(exc))
            return False
        self.operator_action_succeeded.emit("cancel_job", job_id)
        return True

    def _visible_job(self, job_id: str, *, refresh: bool = False) -> JobMonitorState | None:
        snapshot = self.refresh_now() if refresh else self.current_snapshot
        if snapshot is None:
            return None
        return next((item for item in snapshot.jobs if item.job_id == job_id), None)

    def _set_sync_state(
        self,
        *,
        in_progress: bool | None = None,
        last_refresh_at: datetime | None = None,
        last_error: str | None = None,
    ) -> None:
        if in_progress is not None:
            self._sync_state.in_progress = bool(in_progress)
        if last_refresh_at is not None:
            self._sync_state.last_refresh_at = last_refresh_at
        if last_error is not None:
            self._sync_state.last_error = str(last_error or "")
        self.sync_state_updated.emit(self._sync_state)

    def _emit_action_failed(self, action: str, message: str) -> None:
        self.operator_action_failed.emit(action, message)
        self._set_sync_state(in_progress=False, last_error=message)

    def _connect_poller(self, poller: MolSuiteMonitorPoller) -> None:
        poller.project_changed.connect(self.project_changed)
        poller.project_cleared.connect(self._on_project_cleared)
        poller.project_snapshot_updated.connect(self._on_project_snapshot_updated)
        poller.job_upserted.connect(self.job_upserted)
        poller.job_removed.connect(self.job_removed)
        poller.job_finished.connect(self.job_finished)
        poller.bridge_error.connect(self._on_bridge_error)

    def _on_bridge_error(self, message: str) -> None:
        self._set_sync_state(in_progress=False, last_error=message)
        self.bridge_error.emit(message)

    def _on_project_snapshot_updated(self, snapshot) -> None:
        self._set_sync_state(in_progress=False, last_refresh_at=datetime.now(), last_error="")
        self.project_snapshot_updated.emit(snapshot)

    def _on_project_cleared(self) -> None:
        self._set_sync_state(in_progress=False, last_refresh_at=datetime.now(), last_error="")
        self.project_cleared.emit()
