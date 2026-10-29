from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ms_components.ms_monitor.detail import JobDetail
from ms_components.ms_monitor.formatting import format_relative_time
from ms_components.ms_monitor.jobs import JobList
from ms_components.ms_monitor.models import ProjectMonitorState
from ms_components.ms_monitor.resources import HostsStrip, workspace_hosts


class MolSuiteMonitorWidget(QWidget):
    def __init__(self, *, bridge=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = None
        self._snapshot: ProjectMonitorState | None = None
        # The failures of the selected job come from the journal: read again only when the job
        # changes or fails more, not each poll, so the list does not jump while it is read.
        self._failures_key = None

        self.setObjectName("molsuiteMonitor")
        # Only what the app-wide base.qss does NOT already give us: the card frame.
        # Inputs/buttons/trees/scrollbars are deliberately left to the global
        # stylesheet — re-declaring them here would override the theme.
        self.setStyleSheet(
            """
            QFrame#panel {
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 10px;
            }
            QSplitter::handle { background: transparent; }
            """
        )

        layout = QVBoxLayout(self)
        # layout.setContentsMargins(12, 12, 12, 12)
        # layout.setSpacing(10)

        self._project_panel = QFrame(self)
        self._project_panel.setObjectName("panel")
        project_layout = QVBoxLayout(self._project_panel)
        # project_layout.setContentsMargins(14, 12, 14, 12)
        project_layout.setSpacing(4)

        self._title_label = QLabel("No active project", self._project_panel)
        self._title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._title_label.setStyleSheet("color:palette(text); font-size:16px; font-weight:700;")
        self._summary_label = QLabel("Open a project to monitor jobs.", self._project_panel)
        self._summary_label.setStyleSheet("color:palette(placeholder-text); font-size:11px;")

        # One compact status strip instead of a vertical wall of labels.
        status_row = QHBoxLayout()
        status_row.setSpacing(16)
        self._sync_label = QLabel("Sync: idle", self._project_panel)
        self._sync_label.setStyleSheet("color:palette(placeholder-text); font-size:11px;")
        status_row.addWidget(self._sync_label)
        status_row.addStretch(1)
        self._action_label = QLabel("", self._project_panel)
        self._action_label.setStyleSheet("color:palette(highlight); font-size:11px;")
        status_row.addWidget(self._action_label)

        project_layout.addWidget(self._title_label)
        project_layout.addWidget(self._summary_label)
        project_layout.addLayout(status_row)
        layout.addWidget(self._project_panel)

        self._hosts = HostsStrip(getattr(bridge, "workspace", None), parent=self)
        layout.addWidget(self._hosts)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._search_input = QLineEdit(self)
        self._search_input.setPlaceholderText("Search name, key, status...")
        self._status_filter = QComboBox(self)
        self._status_filter.addItem("All statuses", "all")
        self._refresh_button = QPushButton("Resync", self)
        self._cancel_button = QPushButton("Cancel Selected", self)
        self._cancel_button.setEnabled(False)
        filter_row.addWidget(self._search_input, 1)
        filter_row.addWidget(self._status_filter)
        filter_row.addWidget(self._refresh_button)
        self._resume_button = QPushButton("Resume", self)
        self._resume_button.setToolTip("Continue a job that was canceled or interrupted, where it ran.")
        self._move_button = QPushButton("Move to…", self)
        self._move_button.setToolTip("Continue the job on another executor: one that is running is stopped first.")
        self._move_button.setMenu(QMenu(self._move_button))
        filter_row.addWidget(self._cancel_button)
        filter_row.addWidget(self._resume_button)
        filter_row.addWidget(self._move_button)
        self._set_job_actions(None)
        layout.addLayout(filter_row)

        self._jobs_view = JobList(self)
        self._detail = JobDetail(self)

        # Jobs on the left, the selected one on the right: uses the width, so the panel stays
        # usable when its height is squeezed (docked below other panels).
        main_splitter = QSplitter(Qt.Horizontal, self)
        main_splitter.addWidget(self._jobs_view)
        main_splitter.addWidget(self._detail)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setSizes([380, 620])
        layout.addWidget(main_splitter, 1)

        self._search_input.textChanged.connect(self._jobs_view.set_search_text)
        self._status_filter.currentIndexChanged.connect(self._apply_filters)
        self._refresh_button.clicked.connect(self._refresh_from_bridge)
        self._cancel_button.clicked.connect(self._cancel_selected_job)
        self._resume_button.clicked.connect(lambda: self._resume_selected_job())
        self._move_button.menu().aboutToShow.connect(self._fill_destinations)
        self._jobs_view.job_selected.connect(self._on_current_job_changed)
        self._hosts.filter_changed.connect(self._jobs_view.set_executor_filter)

        if bridge is not None:
            self.attach_bridge(bridge)

    def attach_bridge(self, bridge) -> None:
        if self._bridge is bridge:
            return
        if self._bridge is not None:
            self._bridge.project_snapshot_updated.disconnect(self.update_snapshot)
            self._bridge.project_cleared.disconnect(self.clear_snapshot)
            self._bridge.sync_state_updated.disconnect(self._update_sync_state)
            self._bridge.operator_action_succeeded.disconnect(self._handle_action_success)
            self._bridge.operator_action_failed.disconnect(self._handle_action_failure)
            self._bridge.bridge_error.disconnect(self._handle_bridge_error)
        self._bridge = bridge
        self._hosts.hosts = lambda: workspace_hosts(bridge.workspace)
        if self._hosts.isVisible():
            self._hosts.start()
        bridge.project_snapshot_updated.connect(self.update_snapshot)
        bridge.project_cleared.connect(self.clear_snapshot)
        bridge.sync_state_updated.connect(self._update_sync_state)
        bridge.operator_action_succeeded.connect(self._handle_action_success)
        bridge.operator_action_failed.connect(self._handle_action_failure)
        bridge.bridge_error.connect(self._handle_bridge_error)
        snapshot = getattr(bridge, "current_snapshot", None)
        if snapshot is not None:
            self.update_snapshot(snapshot)
        self._update_sync_state(getattr(bridge, "sync_state", None))

    def clear_snapshot(self) -> None:
        self._snapshot = None
        self._title_label.setText("No active project")
        self._summary_label.setText("Open a project to monitor jobs.")
        self._sync_label.setText("Sync: idle")
        self._action_label.setText("")
        self._jobs_view.clear()
        self._search_input.clear()
        self._status_filter.blockSignals(True)
        self._status_filter.clear()
        self._status_filter.addItem("All statuses", "all")
        self._status_filter.blockSignals(False)
        self._set_job_actions(None)
        self._detail.set_job(None)
        self._failures_key = None

    def update_snapshot(self, snapshot: ProjectMonitorState) -> None:
        self._snapshot = snapshot
        if not snapshot.has_project:
            self.clear_snapshot()
            return

        title = snapshot.project_name or snapshot.project_id or "Active project"
        self._title_label.setText(title)
        self._summary_label.setText(
            f"Path: {snapshot.project_path or '-'} | Active jobs: {snapshot.jobs_active} | "
            f"External cancellers: {snapshot.external_cancellers}"
        )

        self._jobs_view.set_jobs(snapshot.jobs)
        self._rebuild_filters(snapshot)
        self._show_selected()

    def _rebuild_filters(self, snapshot: ProjectMonitorState) -> None:
        current_status = self._status_filter.currentData()

        self._status_filter.blockSignals(True)
        self._status_filter.clear()
        self._status_filter.addItem("All statuses", "all")
        for status in sorted({job.status for job in snapshot.jobs if job.status}):
            self._status_filter.addItem(status, status)
        index = max(0, self._status_filter.findData(current_status))
        self._status_filter.setCurrentIndex(index)
        self._status_filter.blockSignals(False)
        self._apply_filters()

    def _apply_filters(self) -> None:
        self._jobs_view.set_status_filter(str(self._status_filter.currentData() or "all"))

    def _refresh_from_bridge(self) -> None:
        if self._bridge is not None:
            self._bridge.request_refresh()
        self._failures_key = None  # an explicit resync reads the failures again
        self._show_selected()

    def _selected_job_id(self) -> str | None:
        return self._jobs_view.selected_job_id()

    def _cancel_selected_job(self) -> None:
        if self._bridge is None:
            return
        job_id = self._selected_job_id()
        if not job_id:
            return
        if self._bridge.cancel_job(job_id):
            self._bridge.request_refresh()

    def _set_job_actions(self, job) -> None:
        stopped = job is not None and job.status in ("canceled", "interrupted")
        self._cancel_button.setEnabled(job is not None and not job.is_terminal)
        self._resume_button.setEnabled(stopped)
        self._move_button.setEnabled(stopped or (job is not None and not job.is_terminal))

    def _fill_destinations(self) -> None:
        menu, job_id = self._move_button.menu(), self._selected_job_id()
        menu.clear()
        for name in (self._bridge.job_destinations(job_id) if self._bridge is not None and job_id else ()):
            menu.addAction(name, lambda name=name: self._resume_selected_job(name))
        if menu.isEmpty():
            menu.addAction("This job cannot be continued").setEnabled(False)

    def _resume_selected_job(self, executor: str | None = None) -> None:
        job_id = self._selected_job_id()
        if self._bridge is None or not job_id:
            return
        self._action_label.setText(f"Action: moving {job_id[:8]} to {executor}" if executor else f"Action: resuming {job_id[:8]}")
        self._bridge.resume_job(job_id, executor)

    def _on_current_job_changed(self, job_id) -> None:
        if self._bridge is not None:
            self._bridge.select_job(job_id)
        self._show_selected()

    def _show_selected(self) -> None:
        job = self._selected_job()
        self._set_job_actions(job)
        self._detail.set_job(job)
        key = None if job is None else (job.job_id, job.chunks_failed, job.error)
        if key == self._failures_key:
            return
        self._failures_key = key
        detail = self._bridge.get_job_detail(job.job_id) if self._bridge is not None and job is not None else None
        self._detail.set_failures(detail.failures if detail else [], job.chunks_failed if job else 0, job.error if job else "")

    def _selected_job(self):
        return self._jobs_view.selected_job()

    def _update_sync_state(self, state) -> None:
        if state is None:
            self._sync_label.setText("Sync: idle")
            return
        if getattr(state, "in_progress", False):
            self._sync_label.setText("Sync: refreshing...")
            return
        last_error = str(getattr(state, "last_error", "") or "")
        if last_error:
            self._sync_label.setText(f"Sync error: {last_error}")
            return
        last_refresh_at = getattr(state, "last_refresh_at", None)
        if last_refresh_at is None:
            self._sync_label.setText("Sync: idle")
            return
        self._sync_label.setText(f"Sync: last refresh {format_relative_time(last_refresh_at)}")

    def _handle_action_success(self, action: str, payload: str) -> None:
        if action == "cancel_job":
            self._action_label.setText(f"Action: cancellation requested for {payload[:8]}")
        elif action == "resume_job":
            self._action_label.setText(f"Action: {payload[:8]} continues")
            self._bridge.request_refresh()
        else:
            self._action_label.setText(f"Action: {action}")

    def _handle_action_failure(self, action: str, message: str) -> None:
        self._action_label.setText(f"Action error [{action}]: {message}")

    def _handle_bridge_error(self, message: str) -> None:
        self._action_label.setText(f"Bridge error: {message}")
