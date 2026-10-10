"""The monitor bridge over a real Workspace: what it shows of the engine's jobs."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ms_flow import Workspace, job, table_sink, task
from ms_components.ms_monitor import MolSuiteMonitorBridge

GATE = threading.Event()


@task()
def halve(n: int) -> dict:
    GATE.wait(10)
    if n % 2:
        raise ValueError(f"odd {n}")
    return {"half": n / 2}


@job(task=halve, output=table_sink("halves", columns=("half",)))
def halves(params, project):
    return range(4)


@pytest.fixture
def ms(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    QApplication.instance() or QApplication([])
    workspace = Workspace(app_id="monitor-test")
    yield workspace
    GATE.set()
    workspace.shutdown()


def _open(ms, tmp_path):
    ms.create_or_open_project(name="p", folder=tmp_path / "p", description="", activate=True)
    with closing(sqlite3.connect(str(ms.project_db.db_path))) as conn, conn:
        conn.execute("CREATE TABLE IF NOT EXISTS halves (id INTEGER PRIMARY KEY, half REAL)")


def _visible(bridge):
    """The one job of the project, once its row has reached the journal."""
    end = time.monotonic() + 10
    while not (jobs := bridge.refresh_now().jobs):
        assert time.monotonic() < end, "the job never showed"
        time.sleep(0.01)
    [state] = jobs
    return state


def test_no_project_shows_nothing(ms):
    snapshot = MolSuiteMonitorBridge(workspace=ms, poll_ms=50).refresh_now()
    assert (snapshot.has_project, snapshot.project_id, snapshot.jobs, snapshot.jobs_active) == (False, None, [], 0)


def test_a_job_is_followed_to_its_end_and_read_back_from_the_journal(ms, tmp_path):
    _open(ms, tmp_path)
    bridge = MolSuiteMonitorBridge(workspace=ms, poll_ms=50)
    finished = []
    bridge.job_finished.connect(lambda job_id, status: finished.append((job_id, status)))

    GATE.clear()
    job_id = ms.submit(halves, executor="thread")
    state = _visible(bridge)
    assert (state.engine_id, state.name, state.is_terminal) == (job_id, "halves", False)
    assert bridge.current_snapshot.jobs_active == 1 and bridge.current_snapshot.active
    assert bridge.cancel_job("unknown") is False

    # its tasks in flight are read only while the job is unfolded
    assert state.tasks == []
    bridge.set_unfolded_jobs([state.job_id])
    tasks = bridge.refresh_now().jobs[0].tasks
    assert tasks and {task.input for task in tasks} <= {"0", "1", "2", "3"}
    assert all((task.chunks, task.attempt, task.progress) == (1, 1, None) for task in tasks)  # threads do not say

    GATE.set()
    ms.engine.wait(job_id, 30)
    [state] = bridge.refresh_now().jobs
    assert (state.status, state.chunks_done, state.chunks_failed, state.progress) == ("completed_with_errors", 2, 2, 100.0)
    assert finished == [(state.job_id, "completed_with_errors")]
    assert bridge.cancel_job(state.job_id) is False  # it has ended

    failures = bridge.get_job_detail(state.job_id).failures
    assert sorted(failure.error.strip().splitlines()[-1] for failure in failures) == ["ValueError: odd 1", "ValueError: odd 3"]
    assert sorted(failure.input for failure in failures) == ["1", "3"]

    # another session of the project: the same job, now only on record
    ms.close_project()
    assert bridge.refresh_now().jobs == []
    _open(ms, tmp_path)
    [past] = bridge.refresh_now().jobs
    assert (past.engine_id, past.job_id, past.status, past.chunks_failed) == (None, state.job_id, "completed_with_errors", 2)
    assert len(bridge.get_job_detail(past.job_id).failures) == 2


def test_cancel_reaches_the_engine(ms, tmp_path):
    _open(ms, tmp_path)
    bridge = MolSuiteMonitorBridge(workspace=ms, poll_ms=50)
    GATE.clear()
    job_id = ms.submit(halves, executor="thread")
    state = _visible(bridge)

    assert bridge.cancel_job(state.job_id) is True
    GATE.set()
    assert ms.engine.wait(job_id, 30).status == "canceled"
    assert bridge.refresh_now().jobs[0].status == "canceled"
