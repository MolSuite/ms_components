from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pydantic import AliasChoices, BaseModel, Field  # noqa: F401
from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QMenu, QToolButton
from shiboken6 import delete, isValid

from ms_components.ms_pymol.widget import (
    PymolControlBar,
    PymolPresetSpec,
)


class FakeCmd:
    def __init__(self):
        self.selection_mode = 1
        self.selected_atoms = 0
        self.selected_residues: set[tuple[str, str, str]] = set()
        self.calls: list[tuple] = []

    def get_setting_int(self, name):
        assert name == "mouse_selection_mode"
        return self.selection_mode

    def count_atoms(self, selection):
        return self.selected_atoms if selection == "sele" else 1

    def set(self, name, value, **kwargs):
        self.calls.append(("set", name, value, kwargs))
        if name == "mouse_selection_mode":
            self.selection_mode = int(value)

    def zoom(self, target, buffer):
        self.calls.append(("zoom", target, buffer))

    def orient(self, target):
        self.calls.append(("orient", target))

    def center(self, target):
        self.calls.append(("center", target))

    def deselect(self):
        self.selected_atoms = 0
        self.selected_residues.clear()
        self.calls.append(("deselect",))

    def iterate(self, selection, _expression, *, space):
        assert selection == "sele"
        space["residues"].update(self.selected_residues)

    def hide(self, representation, target):
        self.calls.append(("hide", representation, target))

    def show(self, representation, target):
        self.calls.append(("show", representation, target))


def _app():
    return QApplication.instance() or QApplication(["molsuite-pymol-toolbar-test"])


def test_pymol_toolbar_controls_selection_camera_and_representation():
    _app()
    cmd = FakeCmd()
    bar = PymolControlBar(cmd)

    assert bar._selection_mode_actions[1].isChecked()
    bar._selection_mode_actions[2].trigger()
    assert cmd.selection_mode == 2

    bar.set_scene_context("receptor", target="receptor_7")
    bar.zoom_active()
    bar.orient_active()
    bar.center_active()
    bar.apply_representation("cartoon")
    bar.hide_representation("cartoon")
    assert ("zoom", "receptor_7", 4) in cmd.calls
    assert ("orient", "receptor_7") in cmd.calls
    assert ("center", "receptor_7") in cmd.calls
    assert ("show", "cartoon", "receptor_7") in cmd.calls
    assert ("hide", "cartoon", "receptor_7") in cmd.calls

    cmd.selected_atoms = 4
    bar.apply_representation("sticks")
    assert ("show", "sticks", "sele") in cmd.calls


def test_pymol_toolbar_filters_and_applies_registered_presets():
    _app()
    cmd = FakeCmd()
    bar = PymolControlBar(cmd)
    applied: list[tuple[str, str]] = []
    bar.register_preset(
        PymolPresetSpec(
            key="test.receptor",
            label="Test receptor",
            contexts=frozenset({"receptor"}),
            callback=lambda _cmd, context: applied.append(
                (context.kind, context.selection("receptor"))
            ),
        )
    )

    bar.set_scene_context("ligand", target="ligand_3")
    assert "test.receptor" not in {
        spec.key for spec in bar.available_presets()
    }

    bar.set_scene_context(
        "receptor",
        target="receptor_7",
        selections={"receptor": "receptor_7"},
        default_preset="test.receptor",
    )
    assert "test.receptor" in {
        spec.key for spec in bar.available_presets()
    }
    assert "test.receptor" in {
        action.data() for action in bar.preset_menu.actions()
    }
    bar.apply_preset("test.receptor")
    assert applied == [("receptor", "receptor_7")]


def test_pymol_toolbar_summarizes_selected_residues_in_the_context_label():
    _app()
    cmd = FakeCmd()
    cmd.selected_atoms = 12
    cmd.selected_residues = {
        ("A", "GLU", "45"),
        ("A", "LYS", "50"),
        ("B", "TYR", "12"),
    }
    bar = PymolControlBar(cmd)
    bar.set_scene_context("receptor", target="receptor_7")

    assert bar.context_label.text() == "Receptor · A:45 GLU, A:50 LYS +1"
    assert "B:12 TYR" in bar.context_label.toolTip()

    bar.clear_selection()
    assert ("deselect",) in cmd.calls


def test_pymol_toolbar_uses_menu_actions_and_hover_overflow():
    app = _app()
    bar = PymolControlBar(FakeCmd())
    bar.resize(320, 40)
    bar.show()
    app.processEvents()

    assert not bar.findChildren(QComboBox)
    assert bar.toolbar.toolButtonStyle() == Qt.ToolButtonIconOnly
    actions = bar.toolbar.actions()
    assert [action.text() for action in actions] == [
        "Selection", "Actions", "Display", "Hide", "Presets",
    ]
    assert all(action.text() and not action.icon().isNull() for action in actions)
    assert bar.selection_mode_action.menu() is not None
    assert bar.actions_action.menu() is not None
    assert bar.representation_action.menu() is not None
    assert bar.hide_action.menu() is not None
    assert [action.text() for action in bar.selection_mode_action.menu().actions() if not action.isSeparator()] == [
        "Atoms", "Residues", "Chains", "Objects", "Clear selection",
    ]
    assert [action.text() for action in bar.actions_action.menu().actions()] == [
        "Zoom", "Orient", "Center",
    ]
    assert [action.text() for action in bar.hide_action.menu().actions()] == [
        "Everything", "Cartoon", "Sticks", "Lines", "Surface", "Spheres", "Ribbon", "Dots",
    ]
    assert bar.preset_action.menu() is not None
    assert bar.context_label.parent() is bar
    assert bar.context_label.text() == "Generic"

    bar.toolbar.setFixedWidth(70)
    app.processEvents()
    extension = bar._overflow_btn
    assert extension is not None and not extension.isHidden()
    assert extension.text() == ""
    assert not extension.icon().isNull()
    assert extension.arrowType() == Qt.NoArrow
    assert extension.iconSize() == QSize(14, 14)
    assert extension.width() >= extension.iconSize().width() + 4
    assert bar.layout().contentsMargins().top() == 1
    assert bar.layout().contentsMargins().bottom() == 1
    assert isinstance(extension.menu(), QMenu)
    assert bar.context_label.isVisible()

    shown: list[bool] = []
    extension.menu().aboutToShow.connect(lambda: shown.append(True))
    QTimer.singleShot(20, extension.menu().close)
    QApplication.sendEvent(extension, QEvent(QEvent.Type.Enter))
    app.processEvents()
    assert shown

    bar.close()


def test_pymol_toolbar_ignores_deleted_overflow_button_during_icon_refresh():
    _app()
    bar = PymolControlBar(FakeCmd())
    deleted_button = QToolButton()

    delete(deleted_button)
    bar._overflow_btn = deleted_button

    assert not isValid(deleted_button)
    bar._refresh_toolbar_icons()
    assert bar._overflow_btn is None

    bar.close()
