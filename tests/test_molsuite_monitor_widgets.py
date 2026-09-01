from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ms_components.ms_monitor.chunk_panel import ChunkPanel
from ms_components.ms_monitor.events_panel import EventsPanel
from ms_components.ms_monitor.models import (
    ChunkMonitorState,
    EventMonitorState,
    JobDetailState,
    JobMonitorState,
    LogMonitorState,
    OutputMonitorState,
)


def _ensure_qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_events_panel_renders_separate_summary_events_outputs_and_logs():
    _ensure_qt_app()
    panel = EventsPanel()
    detail = JobDetailState(
        job_id="job-12345678",
        job=JobMonitorState(
            job_id="job-12345678",
            task_type="dock",
            executor_name="thread",
            status="running",
            progress=0.5,
            chunks_total=10,
            chunks_done=4,
            chunks_running=2,
            chunks_pending=4,
            feed_exhausted=False,
            feed_cursor_position=5,
            feed_items_acked=4,
            throughput_eps=1.25,
        ),
        events=[
            EventMonitorState(
                event_id=1,
                job_id="job-12345678",
                level="info",
                event_type="job_running",
                message="running",
                created_at=datetime(2026, 1, 1, 12, 0, 0),
            )
        ],
        outputs=[OutputMonitorState(index=1, payload={"value": 2})],
        logs=[LogMonitorState(line="executor log line")],
        chunks=[ChunkMonitorState(chunk_id="chunk-1", job_id="job-12345678", status="running", progress=0.5)],
    )

    panel.set_job_detail(detail)

    assert "job-12345678" in panel._summary.toPlainText()
    assert "job_running" in panel._events.toPlainText()
    assert '"value": 2' in panel._outputs.toPlainText()
    assert "executor log line" in panel._logs.toPlainText()


def test_chunk_panel_filters_for_selected_job_and_limits_rows():
    _ensure_qt_app()
    panel = ChunkPanel()
    chunks = [
        ChunkMonitorState(chunk_id=f"chunk-{index}", job_id="job-a", status="running", progress=0.1)
        for index in range(120)
    ]
    chunks.append(ChunkMonitorState(chunk_id="chunk-x", job_id="job-b", status="running", progress=0.2))

    panel.set_chunks(chunks, job_id="job-a")

    assert "job-a"[:8] in panel._title.text()
    assert panel._tree.topLevelItemCount() == panel.MAX_VISIBLE_ROWS


def test_events_panel_clear_resets_all_tabs():
    _ensure_qt_app()
    panel = EventsPanel()
    panel._summary.setPlainText("x")
    panel._events.setPlainText("y")
    panel._outputs.setPlainText("z")
    panel._logs.setPlainText("w")

    panel.clear()

    assert panel._summary.toPlainText() == ""
    assert panel._events.toPlainText() == ""
    assert panel._outputs.toPlainText() == ""
    assert panel._logs.toPlainText() == ""


def test_monitor_widget_keeps_executors_without_project():
    _ensure_qt_app()
    from ms_components.ms_monitor.models import ExecutorMonitorState, ProjectMonitorState
    from ms_components.ms_monitor.widget import MolSuiteMonitorWidget

    widget = MolSuiteMonitorWidget()
    widget.update_snapshot(
        ProjectMonitorState(
            has_project=False,
            executors=[ExecutorMonitorState(name="local", backend="loky")],
            updated_at=datetime.now(),
        )
    )

    assert not widget._executor_panel._empty.isVisible()
    assert widget._executor_panel._title.text().endswith("1")
