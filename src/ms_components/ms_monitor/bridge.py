from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtCore import QMetaObject, QObject, QThread, Qt, Signal

from ms_components.ms_monitor.config import MonitorConfig
from ms_components.ms_monitor.models import (
    ChunkMonitorState,
    ExecutorMonitorState,
    EventMonitorState,
    JobDetailState,
    JobMonitorState,
    LogMonitorState,
    MonitorActionCapability,
    MonitorSyncState,
    OutputMonitorState,
    ProjectMonitorState,
    RuntimeHealthState,
)


def _summarize_chunk_input(payload_json: str) -> str:
    """One-line 'which element was this chunk processing' from the chunk input payload.
    Prefers a file/name key (AMDock chunks carry file_path); falls back to a short excerpt."""
    if not payload_json:
        return ""
    try:
        payload = json.loads(payload_json)
    except (ValueError, TypeError):
        return payload_json[:120]
    if not isinstance(payload, dict):
        return str(payload)[:120]
    for key in ("file_path", "path", "name", "source", "id"):
        value = payload.get(key)
        if value:
            text = str(value)
            head = text.rsplit("/", 1)[-1] if key in ("file_path", "path") else text
            kind = payload.get("kind") or payload.get("molecule_kind")
            return f"{head} ({kind})" if kind else head
    return ", ".join(f"{k}={payload[k]}" for k in list(payload)[:3])[:120]


def _chunk_state_from_row(raw: dict | object | None) -> ChunkMonitorState | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        chunk_id = str(raw.get("chunk_id", "") or "")
        job_id = str(raw.get("job_id", "") or "")
        status = str(raw.get("status", "") or "")
        progress = float(raw.get("progress", 0.0) or 0.0)
        executor_name = str(raw.get("executor_name", "") or "")
        error = str(raw.get("error", "") or "")
        input_summary = _summarize_chunk_input(str(raw.get("payload_json", "") or ""))
    else:
        chunk_id = str(getattr(raw, "chunk_id", "") or "")
        job_id = str(getattr(raw, "job_id", "") or "")
        status = str(getattr(raw, "status", "") or "")
        progress = float(getattr(raw, "progress", 0.0) or 0.0)
        executor_name = str(getattr(raw, "executor_name", "") or "")
        error = str(getattr(raw, "error", "") or "")
        input_summary = _summarize_chunk_input(str(getattr(raw, "payload_json", "") or ""))
    if not chunk_id or not job_id:
        return None
    return ChunkMonitorState(
        chunk_id=chunk_id,
        job_id=job_id,
        status=status,
        progress=progress,
        executor_name=executor_name,
        error=error,
        input_summary=input_summary,
    )
from ms_components.ms_monitor.polling import MolSuiteMonitorPoller


class MolSuiteMonitorBridge(QObject):
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
    sync_state_updated = Signal(object)
    operator_action_succeeded = Signal(str, str)
    operator_action_failed = Signal(str, str)

    def __init__(
        self,
        *,
        molsuite,
        poll_ms: int = MonitorConfig.model_fields["poll_ms"].default,
        max_recent_jobs: int = MonitorConfig.model_fields["max_recent_jobs"].default,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._molsuite = molsuite
        self._poll_ms = poll_ms
        self._max_recent_jobs = max_recent_jobs
        self._thread: QThread | None = None
        self._poller = MolSuiteMonitorPoller(
            molsuite=molsuite,
            poll_ms=poll_ms,
            max_recent_jobs=max_recent_jobs,
        )
        self._sync_state = MonitorSyncState()
        self._connect_poller(self._poller)

    @property
    def current_snapshot(self) -> ProjectMonitorState | None:
        return self._poller.current_snapshot

    @property
    def molsuite(self):
        return self._molsuite

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

    def get_recent_events(self, job_id: str | None = None) -> list[EventMonitorState]:
        snapshot = self.current_snapshot
        if snapshot is None:
            return []
        if job_id is None:
            return list(snapshot.recent_events)
        try:
            rows = self._molsuite.get_job_events(job_id, limit=50)
        except Exception:
            return [item for item in snapshot.recent_events if item.job_id == job_id]
        events: list[EventMonitorState] = []
        for index, row in enumerate(rows, start=1):
            events.append(
                EventMonitorState(
                    event_id=index,
                    job_id=job_id,
                    level=str(row.get("level", "") or ""),
                    event_type=str(row.get("type", "") or ""),
                    message=str(row.get("message", "") or ""),
                    created_at=None,
                )
            )
        return events

    def get_recent_outputs(self, job_id: str | None, *, limit: int = 10) -> list[dict]:
        if not job_id:
            return []
        try:
            outputs = self._molsuite.get_job_outputs(job_id)
        except Exception:
            return []
        return outputs[-limit:] if limit > 0 else outputs

    def get_recent_logs(self, job_id: str | None, *, limit: int = 50) -> list[LogMonitorState]:
        if not job_id:
            return []
        logging_manager = getattr(self._molsuite, "logging_manager", None)
        if logging_manager is None:
            return []
        lines = [
            line
            for line in logging_manager.log_buffer
            if f"job_id={job_id}" in line
        ]
        if limit > 0:
            lines = lines[-limit:]
        return [LogMonitorState(line=line) for line in lines]

    def get_job_history(self, *, limit: int = 20) -> list[JobMonitorState]:
        snapshot = self.current_snapshot
        if snapshot is None:
            return []
        rows = [job for job in snapshot.jobs if job.is_terminal]
        if limit > 0:
            rows = rows[:limit]
        return rows

    def get_job_detail(
        self,
        job_id: str | None,
        *,
        event_limit: int = 50,
        output_limit: int = 10,
        log_limit: int = 50,
    ) -> JobDetailState | None:
        if not job_id:
            return None
        snapshot = self.current_snapshot
        job = None
        chunks: list[ChunkMonitorState] = []
        if snapshot is not None:
            job = next((item for item in snapshot.jobs if item.job_id == job_id), None)
            chunks = [item for item in snapshot.chunks if item.job_id == job_id]
        if not chunks:
            try:
                rows = self._molsuite.get_job_chunks(job_id=job_id, limit=200, include_payload=True)
                chunks = [
                    chunk
                    for row in rows
                    if (chunk := _chunk_state_from_row(row)) is not None
                ]
            except Exception:
                chunks = []
        events = self.get_recent_events(job_id)
        if event_limit > 0:
            events = events[-event_limit:]
        outputs = [
            OutputMonitorState(index=index, payload=dict(payload or {}))
            for index, payload in enumerate(self.get_recent_outputs(job_id, limit=output_limit), start=1)
        ]
        logs = self.get_recent_logs(job_id, limit=log_limit)
        return JobDetailState(
            job_id=job_id,
            job=job,
            events=events,
            outputs=outputs,
            logs=logs,
            chunks=chunks,
        )

    def get_action_capabilities(self, job_id: str | None = None) -> list[MonitorActionCapability]:
        snapshot = self.current_snapshot
        job = None
        if job_id and snapshot is not None:
            job = next((item for item in snapshot.jobs if item.job_id == job_id), None)
        can_cancel = job is not None and not job.is_terminal
        can_resubmit = job is not None and job.is_terminal
        return [
            MonitorActionCapability(
                action="refresh",
                supported=True,
                reason="Snapshot refresh and re-sync are always supported.",
            ),
            MonitorActionCapability(
                action="cancel_job",
                supported=can_cancel,
                reason="" if can_cancel else "Cancellation is only supported for visible non-terminal jobs.",
            ),
            MonitorActionCapability(
                action="resubmit_job",
                supported=can_resubmit,
                reason=(
                    ""
                    if can_resubmit
                    else "Resubmit is only considered for terminal jobs and may still fail if the original source was not persisted."
                ),
            ),
            MonitorActionCapability(
                action="delete_job",
                supported=False,
                reason="Delete/archive is not supported without a formal persistence policy.",
            ),
            MonitorActionCapability(
                action="edit_job",
                supported=False,
                reason="Editing submitted jobs is not supported; use templates or resubmit paths instead.",
            ),
        ]

    def cancel_job(self, job_id: str) -> bool:
        try:
            job = self._require_job_for_action(job_id, action="cancel_job", require_terminal=False)
        except Exception as exc:
            self._emit_action_failed("cancel_job", str(exc))
            return False
        if job.is_terminal:
            self._emit_action_failed("cancel_job", f"Job '{job_id}' is already terminal.")
            return False
        try:
            self._molsuite.cancel_job(job_id)
        except Exception as exc:
            self._emit_action_failed("cancel_job", str(exc))
            return False
        self.operator_action_succeeded.emit("cancel_job", job_id)
        return True

    def resubmit_job(self, job_id: str) -> str | None:
        try:
            job = self._require_job_for_action(job_id, action="resubmit_job", require_terminal=True)
        except Exception as exc:
            self._emit_action_failed("resubmit_job", str(exc))
            return None
        if not job.is_terminal:
            self._emit_action_failed("resubmit_job", f"Job '{job_id}' is not terminal.")
            return None
        try:
            replay_job_id = self._molsuite.resubmit_job(job_id)
        except Exception as exc:
            self._emit_action_failed("resubmit_job", str(exc))
            return None
        self.operator_action_succeeded.emit("resubmit_job", replay_job_id)
        return replay_job_id

    def _require_job_for_action(
        self,
        job_id: str,
        *,
        action: str,
        require_terminal: bool,
    ) -> JobMonitorState:
        snapshot = self.current_snapshot
        if snapshot is None:
            snapshot = self.refresh_now()
        if snapshot is None:
            raise RuntimeError(f"Cannot run '{action}' without a current monitor snapshot.")
        job = next((item for item in snapshot.jobs if item.job_id == job_id), None)
        if job is None:
            snapshot = self.refresh_now()
            if snapshot is not None:
                job = next((item for item in snapshot.jobs if item.job_id == job_id), None)
        if job is None:
            raise RuntimeError(f"Job '{job_id}' is not visible in the current monitor snapshot.")
        if require_terminal and not job.is_terminal:
            raise RuntimeError(f"Job '{job_id}' must be terminal before '{action}'.")
        return job

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
        poller.executors_updated.connect(self.executors_updated)
        poller.health_updated.connect(self.health_updated)
        poller.events_updated.connect(self.events_updated)
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
