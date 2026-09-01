"""Drive the WorkersEditor's add / edit / remove against a stub configuration."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit, QPlainTextEdit, QSpinBox

from ms_components.ms_settings.workers_editor import WorkersEditor
from ms_flow.core.settings.models import WorkersConfig


class _StubConfig:
    """Minimal provider: validates through WorkersConfig like the real manager."""

    def __init__(self):
        self._workers = WorkersConfig()
        self.writes = 0

    def get_value(self, path):
        assert path == "workers"
        return self._workers

    def set_value(self, path, value):
        assert path == "workers"
        self._workers = WorkersConfig(**value)
        self.writes += 1


def _app():
    return QApplication.instance() or QApplication(["workers-editor-test"])


def test_edits_are_staged_until_commit():
    _app()
    cfg = _StubConfig()
    editor = WorkersEditor(configuration=cfg, path="workers")

    from ms_flow.core.settings.models import RayWorkerConfig

    editor._workers["ray"] = RayWorkerConfig(name="ray").model_dump()
    editor._mark_dirty()
    editor._repopulate_list()
    editor._select_by_name("ray")

    # Nothing reaches the configuration until commit() — what "Save changes" calls.
    assert cfg.writes == 0
    assert editor.is_dirty is True
    assert "ray" not in cfg._workers.model_dump()

    address_editor = editor._editors["address"]
    assert isinstance(address_editor, QLineEdit)
    address_editor.setText("10.0.0.5:6379")
    address_editor.editingFinished.emit()

    cpus_editor = editor._editors["cpus"]
    assert isinstance(cpus_editor, QSpinBox)
    cpus_editor.setValue(16)

    enabled_editor = editor._editors["enabled"]
    assert isinstance(enabled_editor, QCheckBox)
    enabled_editor.setChecked(False)

    # List fields (worker_ips / setup_commands) are one entry per line.
    ips_editor = editor._editors["worker_ips"]
    assert isinstance(ips_editor, QPlainTextEdit)
    ips_editor.setPlainText("10.0.0.2\n10.0.0.3\n")

    assert cfg.writes == 0
    editor.commit()
    assert cfg.writes == 1
    assert editor.is_dirty is False

    saved = getattr(cfg._workers, "ray")
    assert saved.address == "10.0.0.5:6379"
    assert saved.cpus == 16
    assert saved.enabled is False
    assert saved.worker_ips == ["10.0.0.2", "10.0.0.3"]


def test_remove_is_also_staged():
    _app()
    cfg = _StubConfig()
    from ms_flow.core.settings.models import RayWorkerConfig

    cfg.set_value("workers", {"ray": RayWorkerConfig(name="ray").model_dump()})
    editor = WorkersEditor(configuration=cfg, path="workers")
    editor._current = "ray"
    editor._on_remove_clicked()
    assert "ray" in cfg._workers.model_dump()  # still there: not committed yet
    editor.commit()
    assert "ray" not in cfg._workers.model_dump()


def test_reload_discards_staged_edits():
    _app()
    cfg = _StubConfig()
    editor = WorkersEditor(configuration=cfg, path="workers")
    from ms_flow.core.settings.models import ThreadWorkerConfig

    editor._workers["thread"] = ThreadWorkerConfig(name="thread").model_dump()
    editor._mark_dirty()
    editor.reload()
    assert editor.is_dirty is False
    assert editor._workers == {}
