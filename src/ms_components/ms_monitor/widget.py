from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QEvent, Qt
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
from ms_components.ms_monitor.palette import P
from ms_components.ms_monitor.resources import HostsStrip, workspace_hosts


class MolSuiteMonitorWidget(QWidget):
    """The jobs of the open project: a header with the tools, the executors' machines, the jobs,
    and the one selected."""

    def __init__(self, *, bridge=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = None
        self._snapshot: ProjectMonitorState | None = None
        # The failures of the selected job come from the journal: read again only when the job
        # changes or fails more, not each poll, so the list does not jump while it is read.
        self._failures_key = None
        self._qss = ""

        self.setObjectName("molsuiteMonitor")
        self._restyle()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(10)

        # the project and what it runs on the left, the tools on the right
        header = QHBoxLayout()
        header.setSpacing(8)
        about = QVBoxLayout()
        about.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(7)
        self._title_label = QLabel("No active project", self)
        self._title_label.setStyleSheet("font-size:16px; font-weight:650;")
        self._sync_dot = QLabel("●", self)
        self._sync_label = QLabel("idle", self)
        self._sync_label.setStyleSheet("color:palette(placeholder-text); font-size:11.5px;")
        self._action_label = QLabel("", self)
        self._action_label.setStyleSheet("color:palette(highlight); font-size:11.5px;")
        for widget in (self._title_label, self._sync_dot, self._sync_label, self._action_label):
            title_row.addWidget(widget)
        title_row.addStretch(1)
        self._summary_label = QLabel("Open a project to monitor jobs.", self)
        self._summary_label.setStyleSheet("color:palette(placeholder-text); font-size:11.5px;")
        self._summary_label.setMinimumWidth(10)
        about.addLayout(title_row)
        about.addWidget(self._summary_label)
        header.addLayout(about, 1)

        self._search_input = QLineEdit(self)
        self._search_input.setPlaceholderText("Search jobs…")
        self._search_input.setFixedWidth(190)
        self._status_filter = QComboBox(self)
        self._status_filter.addItem("All statuses", "all")
        self._refresh_button = QPushButton("Resync", self)
        self._refresh_button.setObjectName("primary")
        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.setObjectName("danger")
        self._cancel_button.setToolTip("Cancel the selected job")
        self._resume_button = QPushButton("Resume", self)
        self._resume_button.setToolTip("Continue a job that was canceled or interrupted, where it ran.")
        self._move_button = QPushButton("Move to", self)
        self._move_button.setToolTip("Continue the job on another executor: one that is running is stopped first.")
        self._move_button.setMenu(QMenu(self._move_button))
        for widget in (self._search_input, self._status_filter, self._refresh_button, self._cancel_button,
                       self._resume_button, self._move_button):
            widget.setFixedHeight(30)
            header.addWidget(widget, 0, Qt.AlignVCenter)
        self._set_job_actions(None)
        layout.addLayout(header)

        self._hosts = HostsStrip(getattr(bridge, "workspace", None), parent=self)
        layout.addWidget(self._hosts)

        jobs_panel = QFrame(self)
        jobs_panel.setObjectName("panel")
        jobs_box = QVBoxLayout(jobs_panel)
        jobs_box.setContentsMargins(10, 10, 10, 10)
        jobs_box.setSpacing(6)
        jobs_head = QHBoxLayout()
        jobs_head.setContentsMargins(4, 0, 2, 0)
        jobs_title = QLabel("Jobs", jobs_panel)
        jobs_title.setStyleSheet("font-weight:600; font-size:13px;")
        self._jobs_count = QLabel(jobs_panel)
        self._jobs_count.setStyleSheet("color:palette(placeholder-text); font-size:11.5px;")
        self._filter_chip = QPushButton(jobs_panel)
        self._filter_chip.setObjectName("filterChip")
        self._filter_chip.setCursor(Qt.PointingHandCursor)
        self._filter_chip.setToolTip("Show every job")
        self._filter_chip.setVisible(False)
        order = QLabel("active first", jobs_panel)
        order.setStyleSheet("color:palette(placeholder-text); font-size:11.5px;")
        for widget in (jobs_title, self._jobs_count, self._filter_chip):
            jobs_head.addWidget(widget)
        jobs_head.addStretch(1)
        jobs_head.addWidget(order)
        jobs_box.addLayout(jobs_head)
        self._jobs_view = JobList(jobs_panel)
        jobs_box.addWidget(self._jobs_view, 1)
        self._detail = JobDetail(self)

        main_splitter = QSplitter(Qt.Horizontal, self)
        main_splitter.setHandleWidth(10)
        main_splitter.addWidget(jobs_panel)
        main_splitter.addWidget(self._detail)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([410, 1000])
        layout.addWidget(main_splitter, 1)

        self._search_input.textChanged.connect(self._jobs_view.set_search_text)
        self._status_filter.currentIndexChanged.connect(self._apply_filters)
        self._refresh_button.clicked.connect(self._refresh_from_bridge)
        self._cancel_button.clicked.connect(self._cancel_selected_job)
        self._resume_button.clicked.connect(lambda: self._resume_selected_job())
        self._move_button.menu().aboutToShow.connect(self._fill_destinations)
        self._jobs_view.job_selected.connect(self._on_current_job_changed)
        self._hosts.filter_changed.connect(
            lambda executors: self._filter(executors, None if executors is None else f"host: {self._hosts.chosen}"))
        self._detail.executor_clicked.connect(lambda name: self._filter({name}, f"executor: {name}", host=False))
        self._filter_chip.clicked.connect(lambda: self._filter(None, None, host=False))

        if bridge is not None:
            self.attach_bridge(bridge)

    def _restyle(self) -> None:
        """The panels and the tool buttons. The danger red has no palette role, so this is built
        again when the theme changes."""
        qss = f"""
            QFrame#panel {{ background: palette(base); border: 1px solid palette(mid); border-radius: 8px; }}
            QSplitter::handle {{ background: transparent; }}
            QPushButton#primary {{ color: palette(highlight); border: 1px solid palette(highlight); border-radius: 6px; padding: 0 12px; }}
            QPushButton#danger {{ color: {P["error"]}; }}
            QPushButton#danger:disabled {{ color: palette(placeholder-text); }}
            QPushButton#xchip {{ color: palette(placeholder-text); background: transparent; border: 1px solid palette(mid);
                                 border-radius: 4px; padding: 1px 7px; font-size: 11px; min-height: 0; }}
            QPushButton#xchip:hover {{ color: palette(text); border-color: palette(highlight); }}
            QPushButton#filterChip {{ color: palette(highlight); background: transparent; border: 1px solid palette(highlight);
                                      border-radius: 9px; padding: 0 8px; font-size: 11px; min-height: 0; }}
            QTabWidget#pills::pane {{ border: none; }}
            QTabWidget#pills > QTabBar {{ background: palette(alternate-base); border-radius: 7px; }}
            QTabWidget#pills > QTabBar::tab {{ background: transparent; border: none; border-radius: 5px; padding: 4px 12px; margin: 3px 1px; }}
            QTabWidget#pills > QTabBar::tab:selected {{ background: palette(button); }}
        """
        if qss != self._qss:
            self._qss = qss
            self.setStyleSheet(qss)

    def changeEvent(self, event):
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            self._restyle()
        super().changeEvent(event)

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
        self._update_sync_state(None)
        self._action_label.setText("")
        self._jobs_view.clear()
        self._jobs_count.setText("")
        self._hosts.set_jobs([])
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

        self._title_label.setText(snapshot.project_name or snapshot.project_id or "Active project")
        by_status = Counter(job.status.replace("_", " ") for job in snapshot.jobs)
        said = f"{len(snapshot.jobs)} jobs" + (": " + " · ".join(f"{n} {s}" for s, n in by_status.most_common()) if by_status else "")
        executors = sorted({job.executor for job in snapshot.jobs if job.executor and not job.is_terminal})
        path = f"{snapshot.project_path} · " if snapshot.project_path else ""
        self._summary_label.setText(path + said + (f" · on {', '.join(executors)}" if executors else ""))
        self._summary_label.setToolTip(self._summary_label.text())
        self._jobs_count.setText(str(len(snapshot.jobs)))

        self._jobs_view.set_jobs(snapshot.jobs)
        self._hosts.set_jobs(snapshot.jobs)
        self._rebuild_filters(snapshot)
        self._show_selected()

    def _rebuild_filters(self, snapshot: ProjectMonitorState) -> None:
        current_status = self._status_filter.currentData()

        self._status_filter.blockSignals(True)
        self._status_filter.clear()
        self._status_filter.addItem("All statuses", "all")
        for status in sorted({job.status for job in snapshot.jobs if job.status}):
            self._status_filter.addItem(status.replace("_", " "), status)
        index = max(0, self._status_filter.findData(current_status))
        self._status_filter.setCurrentIndex(index)
        self._status_filter.blockSignals(False)
        self._apply_filters()

    def _apply_filters(self) -> None:
        self._jobs_view.set_status_filter(str(self._status_filter.currentData() or "all"))

    def _filter(self, executors, label: str | None, *, host: bool = True) -> None:
        """Only the jobs of `executors` (None: every job), said by the chip in the jobs' header."""
        if not host:
            self._hosts.clear_choice()
        self._jobs_view.set_executor_filter(executors)
        self._filter_chip.setText(f"{label}  ✕" if label else "")
        self._filter_chip.setVisible(executors is not None)

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
        self._action_label.setText(f"moving {job_id[:8]} to {executor}…" if executor else f"resuming {job_id[:8]}…")
        self._bridge.resume_job(job_id, executor)

    def _on_current_job_changed(self, job_id) -> None:
        if self._bridge is not None:
            self._bridge.select_job(job_id)
        self._show_selected()

    def _show_selected(self) -> None:
        job = self._selected_job()
        self._set_job_actions(job)
        self._detail.set_job(job)
        if job is not None:
            self._detail.set_color(self._jobs_view.color_of(job.job_id))
        key = None if job is None else (job.job_id, job.chunks_failed, job.error)
        if key == self._failures_key:
            return
        self._failures_key = key
        detail = self._bridge.get_job_detail(job.job_id) if self._bridge is not None and job is not None else None
        self._detail.set_failures(detail.failures if detail else [], job.chunks_failed if job else 0, job.error if job else "")

    def _selected_job(self):
        return self._jobs_view.selected_job()

    def _update_sync_state(self, state) -> None:
        hue, said = P["text_muted"], "idle"
        if state is not None and getattr(state, "in_progress", False):
            hue, said = P["warn"], "refreshing…"
        elif state is not None and getattr(state, "last_error", ""):
            hue, said = P["error"], f"sync error: {state.last_error}"
        elif state is not None and getattr(state, "last_refresh_at", None) is not None:
            hue, said = P["ok"], f"synced {format_relative_time(state.last_refresh_at)}"
        self._sync_dot.setStyleSheet(f"color:{hue}; font-size:10px;")
        self._sync_label.setText(said)

    def _handle_action_success(self, action: str, payload: str) -> None:
        if action == "cancel_job":
            self._action_label.setText(f"cancellation requested for {payload[:8]}")
        elif action == "resume_job":
            self._action_label.setText(f"{payload[:8]} continues")
            self._bridge.request_refresh()
        else:
            self._action_label.setText(action)

    def _handle_action_failure(self, action: str, message: str) -> None:
        self._action_label.setText(f"{action} failed: {message}")

    def _handle_bridge_error(self, message: str) -> None:
        self._action_label.setText(f"bridge error: {message}")
