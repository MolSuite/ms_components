from __future__ import annotations

import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ms_components.ms_monitor.detail import JobDetail, counts, grid_window, layout_cells
from ms_components.ms_monitor.models import FailureState, JobMonitorState, ProjectMonitorState, TaskMonitorState
from ms_components.ms_monitor.polling import _Speeds
from ms_components.ms_monitor.widget import MolSuiteMonitorWidget

TRACEBACK = 'Traceback (most recent call last):\n  File "dock.py", line 3, in dock\nValueError: bad ligand\n'


def _job(**changes) -> JobMonitorState:
    values = dict(job_id="abc123", engine_id=7, name="docking", executor="local", status="running", progress=50.0,
                  chunks_total=4, chunks_done=1, chunks_failed=1, chunks_running=2, started_at=datetime.now())
    return JobMonitorState(**{**values, **changes})


def test_the_grid_shows_a_thousand_chunks_at_most_and_moves_on_as_the_work_does():
    assert layout_cells(40, 120, 60) == (10, 2, 5)  # few: big cells, filled column by column
    assert grid_window(bytes([2] * 900), 0) == 0  # all of them fit
    work = bytes([2] * 999 + [1] + [0] * 2000)  # the furthest that began is at the window's end
    assert grid_window(work, 0) == 500
    assert grid_window(bytes([2] * 1400 + [1] + [0] * 1599), 500) == 500  # not yet: it holds still
    assert grid_window(bytes([2] * 1500 + [0] * 1500), 500) == 1000  # 1,500 reached: back to 500 in
    assert grid_window(bytes([2] * 2990 + [0] * 10), 1500) == 2000  # never past the last full window
    assert counts(bytes([2, 2, 3, 1, 0, 0])) == [2, 1, 2, 1]


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
    assert detail._progress.value.text() == "2 / 8" and detail._pct.text() == "38%" and "1 pending" in detail._legend.text()
    assert detail._bar.parts == (2, 4, 1, 1) and (detail._speed.value.text(), detail._speed.unit.text()) == ("30.0", "chunks/min")
    assert detail._grid.isVisibleTo(detail) and detail._grid.cells == bytes([2, 2, 3, 1, 1, 1, 1, 0])
    assert detail._tabs.tabText(0) == "Running  4" and "1 slow" in detail._tab_meta.text()
    slow = detail._tasks.topLevelItem(3)
    assert (slow.text(1), slow.text(4)) == ("pc3", "40%") and slow.toolTip(0).startswith("slow:")
    assert not detail._tasks.topLevelItem(0).toolTip(0).startswith("slow:")

    other = TRACEBACK.replace("bad ligand", "no atoms")
    detail.set_failures([FailureState(1, TRACEBACK, "a"), FailureState(2, TRACEBACK, "b"), FailureState(1, other, "c")], 5)
    top = [detail._errors.item(i).text() for i in range(detail._errors.count())]
    assert top == ["ValueError: bad ligand", "ValueError: no atoms", "… 2 more failed chunks not read"]
    assert detail._errors.item(0).data(Qt.UserRole + 1) == 2 and 'File "dock.py"' in detail._traceback.toPlainText()
    assert detail._tabs.tabText(1) == "Errors  5" and detail._failed.sub.text() == "2 error types"

    detail.set_job(_job(status="completed", engine_id=None))  # of another session: no grid, a note
    assert not detail._grid.isVisibleTo(detail) and "not run by this session" in detail._meta.text()
    assert detail._fact["status"].text() == "completed"


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
    assert widget._jobs_view.visible_job_ids() == ["abc123"] and not widget._filter_chip.isHidden()
    widget._detail.executor_clicked.emit("ray")  # the detail's executor chip
    assert widget._jobs_view.visible_job_ids() == ["old"] and widget._filter_chip.text().startswith("executor: ray")
    widget._filter_chip.click()  # ✕: every job again
    assert widget._jobs_view.visible_job_ids() == ["abc123", "old"] and widget._filter_chip.isHidden()

    widget.update_snapshot(ProjectMonitorState(has_project=False))
    assert widget._title_label.text() == "No active project" and not widget._jobs_view.jobs()
    assert widget._detail._name.text() == "Select a job"


def test_a_mac_is_read_without_proc(tmp_path):
    """Run the Mac half of the script with stand-ins for its `sysctl`, `ps` and `vm_stat`."""
    from ms_components.ms_monitor.resources import _MAC, parse

    fakes = {
        "sysctl": 'case "$2" in hw.ncpu) echo 8 ;; hw.memsize) echo 17179869184 ;; esac',
        "ps": "printf ' 100.0\\n 50.0\\n 10.0\\n'",  # 160 % of one core = 20 % of eight
        "vm_stat": "printf 'Mach Virtual Memory Statistics: (page size of 16384 bytes)\\nPages free:  65536.\\n"
                   "Pages active:  9999.\\nPages inactive:  131072.\\nPages speculative:  65536.\\n'",  # 4 GB free
    }
    for name, body in fakes.items():
        (tmp_path / name).write_text(f"#!/bin/sh\n{body}\n")
        (tmp_path / name).chmod(0o755)
    text = subprocess.check_output(["sh", "-c", _MAC], text=True, env={"PATH": f"{tmp_path}:/usr/bin:/bin"})
    sample, _ = parse(text, None)
    assert (sample.cpu, round(sample.mem), round(sample.mem_total_gb)) == (20.0, 75, 16), text

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


def test_a_host_under_a_ray_is_read_from_its_metrics_with_no_ssh():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from ms_components.ms_monitor.resources import HostsStrip, _Reader

    text = ('# HELP ray_node_cpu_utilization Total CPU usage\n'
            'ray_node_cpu_utilization{ip="10.0.0.2",SessionName="s"} 42.5\n'
            'ray_node_mem_used{ip="10.0.0.2"} 4294967296.0\n'
            'ray_node_mem_total{ip="10.0.0.2"} 17179869184.0\n'
            'ray_node_gpus_utilization{GpuIndex="1",ip="10.0.0.2"} 80.0\n'
            'ray_node_gram_used{GpuIndex="1",ip="10.0.0.2"} 2048.0\n'
            'ray_node_gram_available{GpuIndex="1",ip="10.0.0.2"} 4096.0\n'
            'ray_node_gpus_utilization{GpuIndex="0",ip="10.0.0.2"} 20.0\n')

    class Metrics(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(text.encode())

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Metrics)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/metrics"
    try:
        asked = []
        workspace = SimpleNamespace(node_metrics=lambda executor: asked.append(executor) or {"pc2": url})
        metrics = HostsStrip(workspace, hosts=lambda: [])._metrics("pc2", "ray", ["ray"])
        reader = _Reader("me@nowhere.invalid", metrics)  # ssh there would fail: the sample says it did not go
        for _ in range(2):
            sample = reader.read()
            assert (sample.error, sample.via, sample.cpu, round(sample.mem), round(sample.mem_total_gb)) == ("", "Ray", 42.5, 25, 16)
            assert sample.gpus == [(20.0, 0.0, 0.0), (80.0, 2048.0, 6144.0)]
        assert asked == ["ray"]  # the URL is kept while it answers
        assert HostsStrip(workspace, hosts=lambda: [])._metrics("pc2", "queue", ["slurm"]) is None
    finally:
        server.shutdown()
