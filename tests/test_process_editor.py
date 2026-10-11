"""Drive the ProcessRoleEditor: what is chosen reaches ``apply`` on commit, and only then."""
from __future__ import annotations

import threading

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ms_components.ms_settings.process_editor import ProcessRoleEditor
from ms_flow.core.settings.models import ProcessRoleConfig


class _Stub:
    def get_global_value(self, path):
        assert path == "resources.process"
        return ProcessRoleConfig()


def test_the_choice_and_its_fields_reach_apply_on_commit_and_a_failure_is_raised():
    _ = QApplication.instance() or QApplication(["process-editor-test"])
    calls = []

    def apply(kind, on_line=None, **fields):
        calls.append((kind, fields, threading.current_thread() is threading.main_thread()))
        if on_line:
            on_line("reaching pc2")
        if fields.get("hosts") == ["nowhere"]:
            raise OSError("nowhere is not reached")

    editor = ProcessRoleEditor(configuration=_Stub(), apply=apply)
    assert editor.kind.currentData() == "process" and not editor.is_dirty
    editor.kind.setCurrentIndex(editor.kind.findData("ray"))
    editor.editors["ray"]["hosts"].setPlainText("pc2\n pc3 \n")
    assert editor.is_dirty and calls == []  # nothing until Save

    editor.commit()
    kind, fields, on_gui_thread = calls[0]
    assert (kind, fields["hosts"], fields["env"], fields["shared_disk"]) == ("ray", ["pc2", "pc3"], "", None)
    assert not on_gui_thread and not editor.is_dirty  # the machines are waited for elsewhere

    editor.editors["ray"]["hosts"].setPlainText("nowhere")
    with pytest.raises(OSError, match="nowhere is not reached"):
        editor.commit()
    assert editor.is_dirty

    editor.kind.setCurrentIndex(editor.kind.findData("process"))
    editor.commit()
    assert calls[-1] == ("process", {"on_login_node": False}, True)
