from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ms_components.ms_monitor.detail_panel import JobDetailPanel
from ms_components.ms_monitor.job_cards import JobCard
from ms_components.ms_monitor.models import (FailureState, JobDetailState, JobMonitorState, ProjectMonitorState,
                                             TaskMonitorState)
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


def test_an_unfolded_card_lists_the_tasks_in_flight():
    QApplication.instance() or QApplication([])
    tasks = [TaskMonitorState(input=f"lig{i}", seconds=75, progress=40.0 if i else None) for i in range(14)]
    card, told = JobCard(_job(tasks=tasks)), []
    card.unfolded.connect(lambda job_id, unfolded: told.append((job_id, unfolded)))
    assert card._task_rows == []  # folded: nothing is built

    card._toggle.click()
    assert told == [("abc123", True)] and len(card._task_rows) == 12
    assert card._tasks_note.text() == "+2 more tasks…"
    watched, unwatched = card._task_rows[1], card._task_rows[0]
    assert (watched._far.text(), watched._bar._busy) == ("40%", None)
    assert unwatched._far.text() == "1m" and unwatched._bar._busy is not None  # how far is unknown: it only runs

    card.set_job(_job(status="completed", tasks=[]))
    assert card._task_rows == [] and card._tasks_note.text() == "No tasks in flight"


def test_monitor_widget_shows_the_jobs_and_empties_without_a_project():
    QApplication.instance() or QApplication([])
    widget = MolSuiteMonitorWidget()
    done = _job(job_id="old", engine_id=None, status="completed", chunks_done=4, chunks_failed=0, chunks_running=0)
    widget.update_snapshot(ProjectMonitorState(project_id="p", project_name="Screening", has_project=True,
                                               jobs_active=1, jobs=[_job(), done]))

    assert widget._title_label.text() == "Screening"
    assert list(widget._jobs_view._cards) == ["abc123", "old"]
    assert widget._chunks_card._value.text() == "1 / 4"  # the job that runs, not the ones listed before it
    widget.update_snapshot(ProjectMonitorState(project_id="p", project_name="Screening", has_project=True, jobs_active=1,
                                               jobs=[_job(chunks_running=28, tasks_running=14, cpu_used=14), done]))
    assert widget._throughput_card._subtitle.text() == "14 tasks running on 14 CPU"
    assert "14 ⚙" in widget._jobs_view._cards["abc123"]._counters_lbl.text()
    widget._jobs_view._cards["old"].clicked.emit("old")
    assert widget._jobs_view._cards["old"]._selected and "2px solid" in widget._jobs_view._cards["old"].styleSheet()
    assert widget._failures_card._value.text() == "1"
    widget._jobs_view.set_search_text("dock")
    widget._jobs_view.set_status_filter("completed")
    assert [key for key, card in widget._jobs_view._cards.items() if not card.isHidden()] == ["old"]

    widget.update_snapshot(ProjectMonitorState(has_project=False))
    assert widget._title_label.text() == "No active project" and not widget._jobs_view._cards


def test_resources_parse_reads_cpu_as_the_change_between_two_reads():
    from ms_components.ms_monitor.resources import parse

    first = "cpu  100 0 100 800 0 0 0 0 0 0\nMemTotal: 16777216 kB\nMemAvailable: 4194304 kB\n"
    sample, ticks = parse(first, None)
    assert sample.cpu is None and (round(sample.mem), round(sample.mem_total_gb)) == (75, 16)
    second = "cpu  400 0 100 1100 0 0 0 0 0 0\nMemTotal: 16777216 kB\nMemAvailable: 4194304 kB\n35, 512, 6144\n"
    sample, _ = parse(second, ticks)
    assert round(sample.cpu) == 50 and sample.gpus == [(35.0, 512.0, 6144.0)]
