from __future__ import annotations

from pathlib import Path
import threading
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ms_flow.api import MolSuite
from ms_components.ms_monitor import MolSuiteMonitorBridge

_STAGE_GATE: threading.Event | None = None


def _patch_fake_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def _ensure_qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _double_value(payload: dict):
    return {"value": int(payload["value"]) * 2}


def _slow_double(payload: dict):
    time.sleep(0.5)
    return {"value": int(payload["value"]) * 2}


def _blocking_stage(payload: dict):
    gate = _STAGE_GATE
    if gate is not None:
        gate.wait(timeout=2.0)
    return payload


def test_monitor_bridge_reports_inactive_without_project(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        health_updates = []
        bridge.health_updated.connect(lambda state: health_updates.append(state))

        snapshot = bridge.refresh_now()

        assert snapshot is not None
        assert snapshot.has_project is False
        assert snapshot.project_id is None
        assert snapshot.jobs == []
        assert snapshot.health is not None
        assert snapshot.health.status == "inactive"
        assert snapshot.health.core_health["status"] == "inactive"
        assert snapshot.health.persistence_health["status"] == "inactive"
        assert snapshot.health.sink_health["status"] == "inactive"
        assert health_updates
    finally:
        ms.shutdown()


def test_monitor_bridge_reports_active_project_jobs_and_switch(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_a_dir = tmp_path / "monitor_project_a"
    project_b_dir = tmp_path / "monitor_project_b"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        changed = []
        cleared = []
        bridge.project_changed.connect(lambda state: changed.append(state.project_id))
        bridge.project_cleared.connect(lambda: cleared.append(True))

        project_a = ms.create_or_open_project(
            name="monitor_project_a",
            folder=project_a_dir,
            description="monitor project a",
            activate=True,
        )
        job_a = ms.run(
            name="job_a",
            input=[{"value": 2}],
            process=_double_value,
            executor="thread",
            store_results=True,
        )
        ms.wait_for_job(job_a, poll_s=0.05)

        snapshot_a = bridge.refresh_now()
        assert snapshot_a is not None
        assert snapshot_a.has_project is True
        assert snapshot_a.project_id == str(project_a.id)
        assert any(job.job_id == job_a for job in snapshot_a.jobs)

        ms.close_project()
        snapshot_none = bridge.refresh_now()
        assert snapshot_none is not None
        assert snapshot_none.has_project is False
        assert snapshot_none.jobs == []
        assert snapshot_none.chunks == []
        assert snapshot_none.recent_events == []
        assert cleared

        project_b = ms.create_or_open_project(
            name="monitor_project_b",
            folder=project_b_dir,
            description="monitor project b",
            activate=True,
        )
        job_b = ms.run(
            name="job_b",
            input=[{"value": 5}],
            process=_double_value,
            executor="thread",
            store_results=True,
        )
        ms.wait_for_job(job_b, poll_s=0.05)

        snapshot_b = bridge.refresh_now()
        assert snapshot_b is not None
        assert snapshot_b.has_project is True
        assert snapshot_b.project_id == str(project_b.id)
        job_ids_b = {job.job_id for job in snapshot_b.jobs}
        assert job_b in job_ids_b
        assert job_a not in job_ids_b
        assert changed[0] == str(project_a.id)
        assert changed[-1] == str(project_b.id)
    finally:
        ms.shutdown()


def test_monitor_bridge_reports_staging_and_live_chunks(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_project_staging"
    gate = threading.Event()
    global _STAGE_GATE
    _STAGE_GATE = gate

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        ms.create_or_open_project(
            name="monitor_project_staging",
            folder=project_dir,
            description="monitor staging project",
            activate=True,
        )
        job_id = ms.run(
            name="job_staging",
            input=[{"value": 7}],
            process=_double_value,
            stage=_blocking_stage,
            executor="thread",
            store_results=True,
        )

        deadline = time.time() + 5.0
        snapshot = None
        while time.time() < deadline:
            snapshot = bridge.refresh_now()
            if snapshot is not None:
                job = next((item for item in snapshot.jobs if item.job_id == job_id), None)
                if job is not None and (job.status == "staging" or job.chunks_staging > 0):
                    break
            time.sleep(0.05)
        else:
            raise AssertionError("Bridge did not observe staging state in time.")

        assert snapshot is not None
        job = next(item for item in snapshot.jobs if item.job_id == job_id)
        assert job.status in {"staging", "running", "completed"}
        assert job.chunks_staging >= 0
        assert any(chunk.job_id == job_id for chunk in snapshot.chunks)

        gate.set()
        final = ms.wait_for_job(job_id, poll_s=0.05)
        assert final.status == "completed"
    finally:
        _STAGE_GATE = None
        ms.shutdown()


def test_monitor_bridge_reports_cancel_requested_state(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_project_cancel"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        ms.create_or_open_project(
            name="monitor_project_cancel",
            folder=project_dir,
            description="monitor cancel project",
            activate=True,
        )
        job_id = ms.run(
            name="job_cancel",
            input=[{"value": 4}],
            process=_slow_double,
            executor="thread",
            store_results=True,
        )

        time.sleep(0.1)
        bridge.cancel_job(job_id)

        deadline = time.time() + 5.0
        seen_cancel_requested = False
        while time.time() < deadline:
            snapshot = bridge.refresh_now()
            assert snapshot is not None
            job = next((item for item in snapshot.jobs if item.job_id == job_id), None)
            if job is not None and (job.cancel_requested or job.status == "cancel_requested"):
                seen_cancel_requested = True
                break
            time.sleep(0.05)

        assert seen_cancel_requested is True
        final = ms.wait_for_job(job_id, poll_s=0.05)
        assert final.status == "canceled"

        snapshot_final = bridge.refresh_now()
        assert snapshot_final is not None
        job_final = next((item for item in snapshot_final.jobs if item.job_id == job_id), None)
        assert job_final is not None
        assert job_final.status == "canceled"
    finally:
        ms.shutdown()


def test_monitor_bridge_orders_active_jobs_before_recent_terminal_jobs(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_project_ordering"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        ms.create_or_open_project(
            name="monitor_project_ordering",
            folder=project_dir,
            description="monitor ordering project",
            activate=True,
        )

        completed_job = ms.run(
            name="job_completed",
            input=[{"value": 1}],
            process=_double_value,
            executor="thread",
            store_results=True,
        )
        ms.wait_for_job(completed_job, poll_s=0.05)

        running_job = ms.run(
            name="job_running",
            input=[{"value": 2}],
            process=_slow_double,
            executor="thread",
            store_results=True,
        )

        deadline = time.time() + 5.0
        snapshot = None
        while time.time() < deadline:
            snapshot = bridge.refresh_now()
            if snapshot is not None and len(snapshot.jobs) >= 2:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("Bridge did not expose enough jobs for ordering test.")

        assert snapshot is not None
        assert snapshot.jobs[0].job_id == running_job
        tail_ids = [job.job_id for job in snapshot.jobs]
        assert completed_job in tail_ids

        ms.wait_for_job(running_job, poll_s=0.05)
    finally:
        ms.shutdown()


def test_monitor_bridge_collects_recent_events_and_resets_on_project_switch(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_a_dir = tmp_path / "monitor_events_a"
    project_b_dir = tmp_path / "monitor_events_b"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        ms.create_or_open_project(
            name="monitor_events_a",
            folder=project_a_dir,
            description="events a",
            activate=True,
        )
        job_a = ms.run(
            name="job_events_a",
            input=[{"value": 3}],
            process=_double_value,
            executor="thread",
            store_results=True,
        )
        ms.wait_for_job(job_a, poll_s=0.05)
        bridge.refresh_now()
        events_a = bridge.get_recent_events(job_a)
        assert events_a
        assert all(item.job_id == job_a for item in events_a)

        ms.create_or_open_project(
            name="monitor_events_b",
            folder=project_b_dir,
            description="events b",
            activate=True,
        )
        bridge.refresh_now()
        assert bridge.get_recent_events(job_a) == []

        job_b = ms.run(
            name="job_events_b",
            input=[{"value": 4}],
            process=_double_value,
            executor="thread",
            store_results=True,
        )
        ms.wait_for_job(job_b, poll_s=0.05)
        bridge.refresh_now()
        events_b = bridge.get_recent_events(job_b)
        assert events_b
        assert all(item.job_id == job_b for item in events_b)
    finally:
        ms.shutdown()


def test_monitor_bridge_can_fetch_recent_outputs(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_outputs"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        ms.create_or_open_project(
            name="monitor_outputs",
            folder=project_dir,
            description="outputs project",
            activate=True,
        )
        job_id = ms.run(
            name="job_outputs",
            input=[{"value": 1}, {"value": 2}],
            process=_double_value,
            executor="thread",
            store_results=True,
        )
        ms.wait_for_job(job_id, poll_s=0.05)
        bridge.refresh_now()
        outputs = bridge.get_recent_outputs(job_id, limit=1)
        assert len(outputs) == 1
        assert outputs[0]["value"] in {2, 4}
    finally:
        ms.shutdown()


def test_monitor_bridge_builds_job_detail_and_history(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_job_detail"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        ms.create_or_open_project(
            name="monitor_job_detail",
            folder=project_dir,
            description="detail project",
            activate=True,
        )
        job_id = ms.run(
            name="job_detail",
            input=[{"value": 1}, {"value": 2}],
            process=_double_value,
            executor="thread",
            store_results=True,
        )
        ms.wait_for_job(job_id, poll_s=0.05)
        bridge.refresh_now()

        monkeypatch.setattr(
            ms,
            "get_job_events",
            lambda _job_id, limit=None: [
                {"level": "info", "type": "job_completed", "message": "done", "created_at": "2026-01-01T00:00:00"},
            ],
        )
        ms.logging_manager.log_buffer.append(f"[fake] [INFO] x: ready [job_id={job_id}]")

        detail = bridge.get_job_detail(job_id, output_limit=2, event_limit=10, log_limit=10)

        assert detail is not None
        assert detail.job_id == job_id
        assert detail.job is not None
        assert detail.job.status == "completed"
        assert len(detail.events) == 1
        assert detail.events[0].event_type == "job_completed"
        assert detail.outputs
        assert detail.logs
        history = bridge.get_job_history(limit=5)
        assert any(item.job_id == job_id for item in history)
    finally:
        ms.shutdown()


def test_monitor_bridge_exposes_sync_state_and_capabilities(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_sync_state"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        ms.create_or_open_project(
            name="monitor_sync_state",
            folder=project_dir,
            description="sync state project",
            activate=True,
        )
        job_id = ms.run(
            name="job_sync_state",
            input=[{"value": 2}],
            process=_double_value,
            executor="thread",
            store_results=True,
        )
        ms.wait_for_job(job_id, poll_s=0.05)

        snapshot = bridge.resync_now()

        assert snapshot is not None
        assert bridge.sync_state.in_progress is False
        assert bridge.sync_state.last_refresh_at is not None
        caps = {item.action: item for item in bridge.get_action_capabilities(job_id)}
        assert caps["refresh"].supported is True
        assert caps["cancel_job"].supported is False
        assert caps["resubmit_job"].supported is True
        assert caps["delete_job"].supported is False
    finally:
        ms.shutdown()


def test_monitor_bridge_cancel_job_handles_missing_job_gracefully(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_cancel_missing"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        errors = []
        bridge.operator_action_failed.connect(lambda action, message: errors.append((action, message)))
        ms.create_or_open_project(
            name="monitor_cancel_missing",
            folder=project_dir,
            description="cancel missing project",
            activate=True,
        )
        bridge.refresh_now()

        ok = bridge.cancel_job("missing-job")

        assert ok is False
        assert errors
        assert errors[-1][0] == "cancel_job"
        assert "not visible" in errors[-1][1]
    finally:
        ms.shutdown()


def test_monitor_bridge_resubmit_job_uses_public_api(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_resubmit"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        successes = []
        bridge.operator_action_succeeded.connect(lambda action, payload: successes.append((action, payload)))
        ms.create_or_open_project(
            name="monitor_resubmit",
            folder=project_dir,
            description="resubmit project",
            activate=True,
        )
        job_id = ms.run(
            name="job_resubmit",
            input=[{"value": 3}],
            process=_double_value,
            executor="thread",
            store_results=True,
        )
        ms.wait_for_job(job_id, poll_s=0.05)
        bridge.refresh_now()

        monkeypatch.setattr(ms, "resubmit_job", lambda value: f"replay-{value}")

        replay_job_id = bridge.resubmit_job(job_id)

        assert replay_job_id == f"replay-{job_id}"
        assert successes[-1] == ("resubmit_job", replay_job_id)
    finally:
        ms.shutdown()


def test_monitor_bridge_prefers_public_output_api(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_outputs_public_api"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        ms.create_or_open_project(
            name="monitor_outputs_public_api",
            folder=project_dir,
            description="outputs api project",
            activate=True,
        )

        called = {"public": 0}

        def _fake_public_outputs(job_id):
            called["public"] += 1
            assert job_id == "job-123"
            return [{"value": 1}, {"value": 2}, {"value": 3}]

        monkeypatch.setattr(ms, "get_job_outputs", _fake_public_outputs)

        outputs = bridge.get_recent_outputs("job-123", limit=2)

        assert outputs == [{"value": 2}, {"value": 3}]
        assert called == {"public": 1}
    finally:
        ms.shutdown()


def test_monitor_bridge_returns_empty_outputs_when_public_api_fails(tmp_path, monkeypatch):
    _ensure_qt_app()
    _patch_fake_home(monkeypatch, tmp_path)

    project_dir = tmp_path / "monitor_outputs_fallback"

    ms = MolSuite(app_id="monitor-test")
    try:
        bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=50)
        ms.create_or_open_project(
            name="monitor_outputs_fallback",
            folder=project_dir,
            description="outputs fallback project",
            activate=True,
        )

        monkeypatch.setattr(
            ms,
            "get_job_outputs",
            lambda job_id: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        outputs = bridge.get_recent_outputs("job-456", limit=1)

        assert outputs == []
    finally:
        ms.shutdown()
