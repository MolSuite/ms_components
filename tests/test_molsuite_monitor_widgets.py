from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ms_components.ms_monitor.detail import JobDetail, layout_cells, ranks
from ms_components.ms_monitor.models import FailureState, JobMonitorState, ProjectMonitorState, TaskMonitorState
from ms_components.ms_monitor.polling import _Speeds
from ms_components.ms_monitor.widget import MolSuiteMonitorWidget

TRACEBACK = 'Traceback (most recent call last):\n  File "dock.py", line 3, in dock\nValueError: bad ligand\n'


def _job(**changes) -> JobMonitorState:
    values = dict(job_id="abc123", engine_id=7, name="docking", executor="local", status="running", progress=50.0,
                  chunks_total=4, chunks_done=1, chunks_failed=1, chunks_running=2, started_at=datetime.now())
    return JobMonitorState(**{**values, **changes})


def test_the_grid_paints_the_worst_chunk_of_each_cell_and_pads_what_is_not_given_yet():
    # pending 0, running 1, done 2, failed 3 → ranks pending 0, done 1, running 2, failed 3
    assert ranks(bytes([2, 1, 3, 0]), 6, 1) == bytes([1, 2, 3, 0, 0, 0])
    assert ranks(bytes([2, 2, 2, 1, 3, 2]), 6, 3) == bytes([1, 3])
    assert layout_cells(40, 120, 60) == (12, 10, 1)  # few: big cells
    assert layout_cells(10_000, 100, 50) == (1, 100, 2)  # more than pixels: two chunks to one


def test_speed_is_that_of_the_last_minutes_and_goes_once_the_job_ends():
    speeds, job = _Speeds(), _job(chunks_done=0, chunks_failed=0, throughput_eps=99.0)
    speeds.apply(job, 1000.0)
    assert job.throughput_eps == 99.0  # too soon to say: the mean since it began stands
    for t, done in ((1005.0, 10), (1010.0, 30)):
        job = _job(chunks_done=done, chunks_failed=0)
        speeds.apply(job, t)
    assert job.throughput_eps == 3.0 and job.throughput_history == [2.0, 4.0]
    assert job.seconds_left is None  # 30 of 4 settled: nothing left to wait for
    speeds.apply(_job(status="completed"), 1015.0)
    assert speeds._seen == {}


def test_the_detail_shows_the_numbers_the_tasks_and_the_failures_grouped():
    QApplication.instance() or QApplication([])
    detail = JobDetail()
    tasks = [TaskMonitorState(input=f"lig{i}", seconds=10, host="pc2") for i in range(3)]
    tasks.append(TaskMonitorState(input="slow", seconds=60, progress=40.0, host="pc3"))
    detail.set_job(_job(chunks_total=8, chunks_done=2, chunks_failed=1, chunks_running=4, throughput_eps=0.5,
                        tasks=tasks, chunk_states=bytes([2, 2, 3, 1, 1, 1, 1])))

    assert detail._left.value.text() == "10s"
    assert detail._progress.value.text() == "38%" and "1 pending" in detail._progress.sub.text()
    assert detail._bar.parts == (2, 4, 1, 1) and detail._speed.value.text() == "30.0/min"
    assert detail._grid.isVisibleTo(detail) and detail._grid._n == 8
    assert detail._tabs.tabText(0) == "Running (4)"
    slow = detail._tasks.topLevelItem(3)
    assert (slow.text(1), slow.text(4)) == ("pc3", "40%") and slow.toolTip(0).startswith("slow:")
    assert not detail._tasks.topLevelItem(0).toolTip(0).startswith("slow:")

    other = TRACEBACK.replace("bad ligand", "no atoms")
    detail.set_failures([FailureState(1, TRACEBACK, "a"), FailureState(2, TRACEBACK, "b"), FailureState(1, other, "c")], 5)
    top = [detail._errors.topLevelItem(i).text(0) for i in range(detail._errors.topLevelItemCount())]
    assert top == ["ValueError: bad ligand", "ValueError: no atoms", "… 2 more failed chunks not read"]
    assert detail._errors.topLevelItem(0).childCount() == 2 and 'File "dock.py"' in detail._traceback.toPlainText()
    assert detail._tabs.tabText(1) == "Errors (5)"

    detail.set_job(_job(status="completed", engine_id=None))  # of another session: no grid, a note
    assert not detail._grid.isVisibleTo(detail) and "not run by this session" in detail._meta.text()


def test_monitor_widget_lists_filters_and_selects_the_jobs_and_empties_without_a_project():
    QApplication.instance() or QApplication([])
    widget = MolSuiteMonitorWidget()
    done = _job(job_id="old", engine_id=None, executor="ray", status="completed", chunks_done=4, chunks_failed=0,
                chunks_running=0)
    snapshot = ProjectMonitorState(project_id="p", project_name="Screening", has_project=True, jobs_active=1,
                                   jobs=[_job(), done])
    widget.update_snapshot(snapshot)
    assert widget._title_label.text() == "Screening"
    assert [job.job_id for job in widget._jobs_view.jobs()] == ["abc123", "old"]

    widget._jobs_view.select_job("old")
    assert widget._detail._name.text() == "docking" and widget._detail._chip.text() == "ray"
    assert not widget._cancel_button.isEnabled()
    widget.update_snapshot(snapshot)  # a poll keeps what is selected
    assert widget._jobs_view.selected_job_id() == "old"

    widget._jobs_view.set_search_text("dock")
    widget._jobs_view.set_status_filter("completed")
    assert widget._jobs_view.visible_job_ids() == ["old"]
    widget._jobs_view.set_status_filter("all")
    widget._hosts.filter_changed.emit({"local"})  # a host card clicked: only its executors' jobs
    assert widget._jobs_view.visible_job_ids() == ["abc123"]

    widget.update_snapshot(ProjectMonitorState(has_project=False))
    assert widget._title_label.text() == "No active project" and not widget._jobs_view.jobs()
    assert widget._detail._name.text() == "Select a job"


def test_the_hosts_are_listed_once_with_their_executors_and_a_queue_is_not_read():
    from ms_components.ms_monitor.resources import parse, workspace_hosts

    first = "cpu  100 0 100 800 0 0 0 0 0 0\nMemTotal: 16777216 kB\nMemAvailable: 4194304 kB\n"
    sample, ticks = parse(first, None)
    assert sample.cpu is None and (round(sample.mem), round(sample.mem_total_gb)) == (75, 16)
    second = "cpu  400 0 100 1100 0 0 0 0 0 0\nMemTotal: 16777216 kB\nMemAvailable: 4194304 kB\n35, 512, 6144\n"
    sample, _ = parse(second, ticks)
    assert round(sample.cpu) == 50 and sample.gpus == [(35.0, 512.0, 6144.0)]

    hosts = {"pc2": SimpleNamespace(address="me@pc2"), "hpc": SimpleNamespace(address="me@login")}
    workspace = SimpleNamespace(
        settings_manager=SimpleNamespace(settings=SimpleNamespace(hosts=hosts)),
        executors=lambda: [
            {"name": "ray", "kind": "ray", "state": "on", "hosts": ["pc2"]},
            {"name": "gpus", "kind": "ray", "state": "on", "hosts": ["pc2"]},
            {"name": "slurm", "kind": "queue", "state": "on", "hosts": ["hpc"]},
            {"name": "off", "kind": "ray", "state": "off", "hosts": ["pc9"]},
        ])
    assert workspace_hosts(workspace) == [
        ("local", "", "local", [], 5),
        ("pc2", "me@pc2", "ray", ["ray", "gpus"], 15),
        ("hpc", "me@login", "queue", ["slurm"], None),
    ]
