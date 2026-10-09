from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ms_components.ms_monitor.detail_panel import JobDetailPanel
from ms_components.ms_monitor.models import FailureState, JobDetailState, JobMonitorState, ProjectMonitorState
from ms_components.ms_monitor.widget import MolSuiteMonitorWidget

TRACEBACK = 'Traceback (most recent call last):\n  File "dock.py", line 3, in dock\nValueError: bad ligand\n'


def _job(**changes) -> JobMonitorState:
    values = dict(job_id="abc123", engine_id=7, name="docking", status="running", progress=50.0,
                  chunks_total=4, chunks_done=1, chunks_failed=1, chunks_running=2, started_at=datetime.now())
    return JobMonitorState(**{**values, **changes})


def test_detail_panel_shows_the_reason_in_the_summary_and_the_traceback_in_errors():
    QApplication.instance() or QApplication([])
    panel = JobDetailPanel()
    panel.set_job_detail(JobDetailState(job_id="abc123", job=_job(), failures=[FailureState(attempt=2, error=TRACEBACK)]))

    summary = panel._summary.toPlainText()
    assert "status: running" in summary and "chunk (attempt 2): ValueError: bad ligand" in summary
    assert 'File "dock.py"' in panel._errors.toPlainText()
    assert panel._tabs.tabText(panel._errors_tab_index) == "Errors (1)"

    panel.clear()
    assert (panel._summary.toPlainText(), panel._errors.toPlainText()) == ("", "")
    assert panel._tabs.tabText(panel._errors_tab_index) == "Errors"


def test_monitor_widget_shows_the_jobs_and_empties_without_a_project():
    QApplication.instance() or QApplication([])
    widget = MolSuiteMonitorWidget()
    done = _job(job_id="old", engine_id=None, status="completed", chunks_done=4, chunks_failed=0, chunks_running=0)
    widget.update_snapshot(ProjectMonitorState(project_id="p", project_name="Screening", has_project=True,
                                               jobs_active=1, jobs=[_job(), done]))

    assert widget._title_label.text() == "Screening"
    assert list(widget._jobs_view._cards) == ["abc123", "old"]
    assert widget._chunks_card._value.text() == "5 / 8"
    assert widget._failures_card._value.text() == "1"
    widget._jobs_view.set_search_text("dock")
    widget._jobs_view.set_status_filter("completed")
    assert [key for key, card in widget._jobs_view._cards.items() if not card.isHidden()] == ["old"]

    widget.update_snapshot(ProjectMonitorState(has_project=False))
    assert widget._title_label.text() == "No active project" and not widget._jobs_view._cards
