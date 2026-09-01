from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ms_components.ms_monitor.cards import MetricCard
from ms_components.ms_monitor.events_panel import EventsPanel
from ms_components.ms_monitor.executor_panel import ExecutorPanel
from ms_components.ms_monitor.executors_tab import ExecutorsTab
from ms_components.ms_monitor.formatting import format_relative_time, format_throughput
from ms_components.ms_monitor.job_cards import JobCardList
from ms_components.ms_monitor.models import ProjectMonitorState
from ms_components.ms_monitor.palette import P


class MolSuiteMonitorWidget(QWidget):
    def __init__(self, *, bridge=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = None
        self._snapshot: ProjectMonitorState | None = None
        # Detail panels (chunks/events/outputs/logs) are loaded once per explicit job
        # selection and frozen afterwards — they do NOT follow the poll. Otherwise the
        # constant re-render scrolls them back to the top while the user reads them.
        self._detail_job_id: str | None = None

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
        self._health_label = QLabel("Health: inactive", self._project_panel)
        self._sync_label = QLabel("Sync: idle", self._project_panel)
        for lbl in (self._health_label, self._sync_label):
            lbl.setStyleSheet("color:palette(placeholder-text); font-size:11px;")
        status_row.addWidget(self._health_label)
        status_row.addWidget(self._sync_label)
        status_row.addStretch(1)
        self._action_label = QLabel("", self._project_panel)
        self._action_label.setStyleSheet("color:palette(highlight); font-size:11px;")
        status_row.addWidget(self._action_label)

        project_layout.addWidget(self._title_label)
        project_layout.addWidget(self._summary_label)
        project_layout.addLayout(status_row)
        layout.addWidget(self._project_panel)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(10)
        self._active_jobs_card = MetricCard("ACTIVE JOBS", "0", subtitle="0 visible", parent=self)
        self._throughput_card = MetricCard("THROUGHPUT", "-", subtitle="0 chunks running", parent=self)
        self._chunks_card = MetricCard("CHUNKS", "0", subtitle="0%", accent=P["ok"], parent=self)
        self._failures_card = MetricCard("FAILURES", "0", subtitle="0 ext. cancellers", accent=P["error"], parent=self)
        self._health_card = MetricCard("HEALTH", "inactive", subtitle="", accent=P["text_muted"], parent=self)
        metrics_row.addWidget(self._active_jobs_card)
        metrics_row.addWidget(self._throughput_card)
        metrics_row.addWidget(self._chunks_card)
        metrics_row.addWidget(self._failures_card)
        metrics_row.addWidget(self._health_card)
        layout.addLayout(metrics_row)

        self._executor_panel = ExecutorPanel(self)
        layout.addWidget(self._executor_panel)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._search_input = QLineEdit(self)
        self._search_input.setPlaceholderText("Search job_id, task, origin, executor...")
        self._status_filter = QComboBox(self)
        self._status_filter.addItem("All statuses", "all")
        self._executor_filter = QComboBox(self)
        self._executor_filter.addItem("All executors", "all")
        self._refresh_button = QPushButton("Resync", self)
        self._cancel_button = QPushButton("Cancel Selected", self)
        self._cancel_button.setEnabled(False)
        filter_row.addWidget(self._search_input, 1)
        filter_row.addWidget(self._status_filter)
        filter_row.addWidget(self._executor_filter)
        filter_row.addWidget(self._refresh_button)
        filter_row.addWidget(self._cancel_button)
        layout.addLayout(filter_row)

        self._jobs_view = JobCardList(self)
        self._events_panel = EventsPanel(parent=self)

        # Horizontal split: jobs on the left, job detail on the right. Uses the
        # available width instead of stacking, so the panel stays usable when its
        # height is squeezed (e.g. docked below other panels). Live chunks now
        # expand inside each job card, so there is no separate chunk panel.
        main_splitter = QSplitter(Qt.Horizontal, self)
        main_splitter.addWidget(self._jobs_view)
        main_splitter.addWidget(self._events_panel)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 2)
        main_splitter.setSizes([560, 440])

        # Jobs are what you watch; executors are what you operate. Same panel,
        # two tabs, so testing/launching a backend lives next to its health.
        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(main_splitter, "Jobs")
        self._executors_tab = ExecutorsTab(parent=self)
        self._tabs.addTab(self._executors_tab, "Executors")
        layout.addWidget(self._tabs, 1)

        self._search_input.textChanged.connect(self._jobs_view.set_search_text)
        self._status_filter.currentIndexChanged.connect(self._apply_filters)
        self._executor_filter.currentIndexChanged.connect(self._apply_filters)
        self._refresh_button.clicked.connect(self._refresh_from_bridge)
        self._cancel_button.clicked.connect(self._cancel_selected_job)
        self._jobs_view.job_selected.connect(self._on_current_job_changed)

        if bridge is not None:
            self.attach_bridge(bridge)

    @staticmethod
    def _format_health_summary(snapshot: ProjectMonitorState) -> tuple[str, str]:
        health = snapshot.health
        if health is None:
            return "Health: inactive", ""
        checks = dict(health.checks or {})
        failing: list[str] = []
        categories = {
            "core": health.core_health,
            "persistence": health.persistence_health,
            "sink": health.sink_health,
        }
        for name, category in categories.items():
            if category and not bool(dict(category or {}).get("ok", True)):
                failing.append(name)
        for key, item in checks.items():
            if key == "executors":
                for executor_name, executor_item in dict(item or {}).items():
                    if not bool(dict(executor_item or {}).get("ok", True)):
                        failing.append(f"executor:{executor_name}")
                continue
            if key not in categories and not bool(dict(item or {}).get("ok", True)):
                failing.append(str(key))
        if not failing:
            return f"Health: {health.status}", ""
        short = ", ".join(failing[:3])
        if len(failing) > 3:
            short += f" +{len(failing) - 3}"
        tooltip = "\n".join(failing)
        return f"Health: {health.status} ({short})", tooltip

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
        bridge.project_snapshot_updated.connect(self.update_snapshot)
        bridge.project_cleared.connect(self.clear_snapshot)
        bridge.sync_state_updated.connect(self._update_sync_state)
        bridge.operator_action_succeeded.connect(self._handle_action_success)
        bridge.operator_action_failed.connect(self._handle_action_failure)
        bridge.bridge_error.connect(self._handle_bridge_error)
        snapshot = getattr(bridge, "current_snapshot", None)
        self._executors_tab.attach_bridge(bridge)
        if snapshot is not None:
            self.update_snapshot(snapshot)
        self._update_sync_state(getattr(bridge, "sync_state", None))

    def clear_snapshot(self) -> None:
        self._snapshot = None
        self._title_label.setText("No active project")
        self._summary_label.setText("Open a project to monitor jobs.")
        self._health_label.setText("Health: inactive")
        self._health_label.setToolTip("")
        self._sync_label.setText("Sync: idle")
        self._action_label.setText("")
        self._active_jobs_card.set_value("0", "0 visible")
        self._throughput_card.set_value("-", "0 chunks running")
        self._chunks_card.set_value("0", "0%")
        self._failures_card.set_value("0", "0 ext. cancellers")
        self._health_card.set_value("inactive", "", accent=P["text_muted"])
        self._executor_panel.clear()
        self._executors_tab.set_live_executors(())
        self._jobs_view.clear()
        self._search_input.clear()
        self._status_filter.blockSignals(True)
        self._status_filter.clear()
        self._status_filter.addItem("All statuses", "all")
        self._status_filter.blockSignals(False)
        self._executor_filter.blockSignals(True)
        self._executor_filter.clear()
        self._executor_filter.addItem("All executors", "all")
        self._executor_filter.blockSignals(False)
        self._cancel_button.setEnabled(False)
        self._events_panel.clear()
        self._detail_job_id = None

    def update_snapshot(self, snapshot: ProjectMonitorState) -> None:
        self._snapshot = snapshot
        if not snapshot.has_project:
            self.clear_snapshot()
            # Executors are runtime-level, not project-level: keep them on screen.
            self._show_executors(snapshot)
            return

        title = snapshot.project_name or snapshot.project_id or "Active project"
        self._title_label.setText(title)
        self._summary_label.setText(
            f"Path: {snapshot.project_path or '-'} | Active jobs: {snapshot.jobs_active} | "
            f"External cancellers: {snapshot.external_cancellers}"
        )
        health_status = snapshot.health.status if snapshot.health is not None else "inactive"
        health_text, health_tooltip = self._format_health_summary(snapshot)
        self._health_label.setText(health_text)
        self._health_label.setToolTip(health_tooltip)

        # Cross-job aggregates — the summary row was previously just counts.
        jobs = snapshot.jobs
        total_eps = sum(j.throughput_eps for j in jobs)
        running_chunks = sum(j.chunks_running for j in jobs)
        chunks_done = sum(j.chunks_done for j in jobs)
        chunks_total = sum(j.chunks_total for j in jobs)
        failures = sum(j.chunks_failed + j.chunks_stage_failed for j in jobs)
        pct = (chunks_done / chunks_total * 100.0) if chunks_total else 0.0
        loop_latency = snapshot.health.loop_latency_ms if snapshot.health is not None else 0.0
        health_ok = health_tooltip == ""

        self._active_jobs_card.set_value(str(snapshot.jobs_active), f"{len(jobs)} visible")
        self._throughput_card.set_value(
            format_throughput(total_eps), f"{running_chunks:,} chunks running")
        self._chunks_card.set_value(f"{chunks_done:,} / {chunks_total:,}", f"{pct:.0f}%")
        self._failures_card.set_value(
            f"{failures:,}", f"{snapshot.external_cancellers} ext. cancellers",
            accent=P["error"] if failures else P["border"])
        self._health_card.set_value(
            health_status, f"latency {loop_latency:.0f}ms",
            accent=P["ok"] if health_ok and health_status not in ("inactive", "") else
            (P["text_muted"] if health_status in ("inactive", "") else P["warn"]))
        self._show_executors(snapshot)
        # Preserve selected job_id before refresh
        selected_job_id = self._selected_job_id()
        self._jobs_view.set_jobs(snapshot.jobs)
        self._rebuild_filters(snapshot)
        # Restore selection if the job still exists; the detail panels are NOT touched
        # here — they only reload on an explicit (re)selection or Resync, so scrolling
        # through chunks/events of the selected job is never yanked back to the top.
        if selected_job_id:
            self._jobs_view.select_job(selected_job_id)

    def _show_executors(self, snapshot: ProjectMonitorState) -> None:
        self._executor_panel.set_executors(snapshot.executors)
        self._executor_panel.set_resources(snapshot.resources)
        self._executors_tab.set_live_executors(ex.name for ex in snapshot.executors)

    def _rebuild_filters(self, snapshot: ProjectMonitorState) -> None:
        current_status = self._status_filter.currentData()
        current_executor = self._executor_filter.currentData()

        self._status_filter.blockSignals(True)
        self._status_filter.clear()
        self._status_filter.addItem("All statuses", "all")
        for status in sorted({job.status for job in snapshot.jobs if job.status}):
            self._status_filter.addItem(status, status)
        index = max(0, self._status_filter.findData(current_status))
        self._status_filter.setCurrentIndex(index)
        self._status_filter.blockSignals(False)

        self._executor_filter.blockSignals(True)
        self._executor_filter.clear()
        self._executor_filter.addItem("All executors", "all")
        for executor_name in sorted({job.executor_name for job in snapshot.jobs if job.executor_name}):
            self._executor_filter.addItem(executor_name, executor_name)
        index = max(0, self._executor_filter.findData(current_executor))
        self._executor_filter.setCurrentIndex(index)
        self._executor_filter.blockSignals(False)
        self._apply_filters()

    def _apply_filters(self) -> None:
        self._jobs_view.set_status_filter(str(self._status_filter.currentData() or "all"))
        self._jobs_view.set_executor_filter(str(self._executor_filter.currentData() or "all"))

    def _refresh_from_bridge(self) -> None:
        if self._bridge is not None:
            self._bridge.request_refresh()
        # Resync is an explicit user action, so it's the one place we reload the detail
        # of the currently selected job.
        self._load_detail()

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

    def _on_current_job_changed(self, *_args) -> None:
        # Triggered only by an explicit click on a job card → reload its detail once.
        self._load_detail()

    def _load_detail(self) -> None:
        if self._bridge is None:
            self._events_panel.clear()
            self._cancel_button.setEnabled(False)
            return
        job_id = self._selected_job_id()
        job = self._selected_job()
        self._cancel_button.setEnabled(job is not None and not job.is_terminal)
        if not job_id:
            self._events_panel.clear()
            self._detail_job_id = None
            return
        detail = self._bridge.get_job_detail(job_id, output_limit=5, event_limit=50, log_limit=50)
        self._events_panel.set_job_detail(detail)
        self._detail_job_id = job_id

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
        elif action == "resubmit_job":
            self._action_label.setText(f"Action: resubmitted as {payload[:8]}")
        else:
            self._action_label.setText(f"Action: {action}")

    def _handle_action_failure(self, action: str, message: str) -> None:
        self._action_label.setText(f"Action error [{action}]: {message}")

    def _handle_bridge_error(self, message: str) -> None:
        self._action_label.setText(f"Bridge error: {message}")


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    window = MolSuiteMonitorWidget()
    window.show()
    app.exec()
