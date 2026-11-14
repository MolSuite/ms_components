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

    # its tasks in flight and chunk states are read only while it is the selected job
    assert (state.tasks, state.chunk_states, state.executor) == ([], None, "thread")
    bridge.select_job(state.job_id)
    selected = bridge.refresh_now().jobs[0]
    assert selected.tasks and {task.input for task in selected.tasks} <= {"0", "1", "2", "3"}
    assert all((task.chunks, task.attempt, task.progress, task.host) == (1, 1, None, None)  # threads do not say
               for task in selected.tasks)
    assert len(selected.chunk_states) == 4 and set(selected.chunk_states) <= {0, 1}  # pending or running

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


def test_a_job_whose_host_does_not_answer_says_so_and_is_asked_again(ms, tmp_path):
    from ms_flow.engine import ThreadExecutor
    from ms_components.ms_monitor.widget import MolSuiteMonitorWidget

    class Far(ThreadExecutor):  # what a RemoteExecutor tells of its other machine
        unreachable, asked = "far has not answered since 10:00: Connection refused", 0
        note = "waiting in the queue (job 7)"  # what a campaign says it is at
        steps = ((1000.0, "staging its elements and their files here"), (1000.4, "waiting in the queue (job 7)"))
        queue_usage = {"wall_s": 21.0, "cpu_s": 20.1, "cpus": 2, "peak_mem_mb": 209.8, "mem_mb": 800.0,
                       "final": True, "job": "7"}  # what the queue's accounting says

        def reconnect(self):
            self.asked += 1

    _open(ms, tmp_path)
    far = Far(2)
    ms.engine.register("far", far)
    bridge = MolSuiteMonitorBridge(workspace=ms, poll_ms=50)
    widget = MolSuiteMonitorWidget()
    widget.attach_bridge(bridge)
    GATE.clear()
    ms.submit(halves, executor="far")
    state = _visible(bridge)
    widget.update_snapshot(bridge.current_snapshot)
    widget._jobs_view.select_job(state.job_id)

    assert state.unreachable == far.unreachable and state.note == far.note
    assert far.note in widget._detail._meta.text()
    steps = widget._detail._steps
    assert widget._detail._tabs.isTabVisible(3) and steps.topLevelItemCount() == 2
    assert [steps.topLevelItem(0).text(n) for n in (1, 2)] == ["0.4s", "staging its elements and their files here"]
    facts = widget._detail._fact
    assert facts["CPU"].text().startswith("in the queue (job 7): 0.01 CPU·h · 48% of 2 CPUs busy over")
    assert facts["peak memory"].text().startswith("210 MB at most of 800 MB asked for, in the queue (job 7)")
    assert widget._detail._badge.text() == "WAITING FOR HOST" and not widget._reconnect_button.isHidden()
    widget._reconnect_button.click()
    assert far.asked == 1
    state.canceling, state.unreachable = True, ""  # what a campaign is while its queue lets it go
    widget._detail.set_job(state)
    widget._set_job_actions(state)
    assert widget._detail._badge.text() == "CANCELING" and widget._cancel_button.text() == "Cancel now"
    GATE.set()


def test_a_job_is_moved_while_it_runs_from_the_buttons_of_the_monitor(ms, tmp_path, monkeypatch):
    from ms_components.ms_monitor.widget import MolSuiteMonitorWidget

    _open(ms, tmp_path)
    bridge, heard = MolSuiteMonitorBridge(workspace=ms, poll_ms=50, destinations=lambda key: [ms.origin(key) and "thread"]), []
    bridge.operator_action_succeeded.connect(lambda action, key: heard.append((action, key)))
    bridge.operator_action_failed.connect(lambda action, why: heard.append((action, why)))
    widget = MolSuiteMonitorWidget()
    widget.attach_bridge(bridge)
    asked, cancel = threading.Event(), ms.engine.cancel
    monkeypatch.setattr(ms.engine, "cancel", lambda job_id: (cancel(job_id), asked.set()))
    GATE.clear()
    first = ms.submit(halves, executor="thread")
    state = _visible(bridge)
    widget.update_snapshot(bridge.current_snapshot)
    widget._jobs_view.select_job(state.job_id)

    assert widget._move_button.isEnabled() and not widget._resume_button.isEnabled()
    widget._fill_destinations()
    offered = [action.text() for action in widget._move_button.menu().actions()]
    assert offered == ["thread"] and bridge.job_destinations("no such job") == []
    assert bridge._active_executors(state.job_id) == ["local"]  # what is offered when nobody says

    next(action for action in widget._move_button.menu().actions() if action.text() == "thread").trigger()
    assert asked.wait(10)  # the tasks are let go once the job was told to stop, or it just ends
    GATE.set()
    end = time.monotonic() + 30
    while not heard:
        assert time.monotonic() < end, "the move never answered"
        QApplication.processEvents()
        time.sleep(0.01)
    assert heard == [("resume_job", state.job_id)]
    assert ms.engine.wait(first, 30).status == "canceled"
    [moved] = [job for job in ms.engine.jobs() if job.key == state.job_id and job.id != first]
    assert ms.engine.wait(moved.id, 30).status == "completed_with_errors"  # the odd ones

    bridge.resume_job(state.job_id)  # it has ended: nothing to continue, and the monitor says why
    while len(heard) < 2:
        assert time.monotonic() < end, "the refusal never answered"
        QApplication.processEvents()
        time.sleep(0.01)
    assert heard[1][0] == "resume_job" and "already ended" in heard[1][1]


def test_what_the_application_measures_is_shown_with_the_chunks(ms, tmp_path):
    """`measure` names a unit and how many of it are done: asked while the job runs, once after."""
    _open(ms, tmp_path)
    asked, done = [], {"n": 3}

    def measure(job_id):
        asked.append(job_id)
        return {"done": done["n"], "total": 12, "unit": "records"} if job_id == state_id[0] else None

    state_id = [None]
    bridge = MolSuiteMonitorBridge(workspace=ms, poll_ms=50, measure=measure)
    GATE.clear()
    job_id = ms.submit(halves, executor="thread")
    state_id[0] = _visible(bridge).job_id
    running = bridge.refresh_now().jobs[0]
    assert (running.items_unit, running.items_done, running.items_total) == ("records", 3, 12)
    assert running.items_eps > 0  # the mean since it began, until there are minutes to go by

    GATE.set()
    ms.engine.wait(job_id, 30)
    done["n"] = 12
    bridge.refresh_now()
    calls = len(asked)
    done["n"] = 99  # it ended: the last word stands
    [ended] = bridge.refresh_now().jobs
    assert (ended.items_done, len(asked)) == (12, calls)


def test_a_job_the_application_does_not_measure_shows_its_chunks_alone(ms, tmp_path):
    _open(ms, tmp_path)
    bridge = MolSuiteMonitorBridge(workspace=ms, poll_ms=50, measure=lambda job_id: 1 / 0)
    GATE.set()
    ms.engine.wait(ms.submit(halves, executor="thread"), 30)
    [state] = bridge.refresh_now().jobs
    assert (state.items_unit, state.items_done, state.status) == ("", 0, "completed_with_errors")


def test_the_application_titles_a_job_once_and_a_failing_title_keeps_its_name(ms, tmp_path):
    """`title(job_id, name)` replaces the name of the job in the monitor; it is asked once a job."""
    _open(ms, tmp_path)
    asked = []

    def title(job_id, name):
        asked.append((job_id, name))
        return f"Halves · {name}"

    bridge = MolSuiteMonitorBridge(workspace=ms, poll_ms=50, title=title)
    GATE.set()
    ms.engine.wait(ms.submit(halves, executor="thread"), 30)
    [state] = bridge.refresh_now().jobs
    assert state.title == f"Halves · {state.name}" and state.label == state.title
    bridge.refresh_now()
    assert asked == [(state.job_id, state.name)]

    failing = MolSuiteMonitorBridge(workspace=ms, poll_ms=50, title=lambda job_id, name: 1 / 0)
    [state] = failing.refresh_now().jobs
    assert (state.title, state.label) == ("", state.name)
