from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from ms_components.ms_pymol import (
    PymolSceneContext,
    add_scene_actions,
    clear_scene,
    install_scene_memory,
    is_interacting,
    prepare_scene,
    set_additive,
    set_scene_context,
)


class _Cmd:
    def __init__(self):
        self.view = (1.0, 2.0, 3.0)
        self.restored = None
        self.objects: dict[str, int] = {}  # name -> grid_slot
        self.calls: list[tuple] = []

    def get_view(self):
        return self.view

    def set_view(self, view):
        self.restored = view

    def get_names(self, _kind):
        return list(self.objects)

    def get_object_list(self, selection):
        names = [part.strip() for part in selection.split(" or ")]
        return [name for name in names if name in self.objects]

    def get_setting_int(self, _name, obj):
        return self.objects.get(obj, 0)

    def set(self, name, value, obj=None):
        if name == "grid_slot":
            self.objects[obj] = value

    def delete(self, name):
        self.calls.append(("delete", name))
        if name == "all":
            self.objects.clear()
        self.objects.pop(name, None)

    def zoom(self, *args):
        self.calls.append(("zoom", *args))


class _Dock(QWidget):
    def __init__(self):
        super().__init__()
        self.pymol_widget = QWidget(self)
        self.cmd = _Cmd()
        self.control_bar = None
        self.scene_context = PymolSceneContext()

    def set_scene_context(self, kind, *, target, selections, default_preset, grid_labels):
        self.scene_context = PymolSceneContext(
            kind=kind, target=target, selections=dict(selections or {}),
            default_preset=default_preset, grid_labels=dict(grid_labels or {}),
        )


def _app():
    return QApplication.instance() or QApplication(["ms-pymol-scene-test"])


def test_the_camera_is_saved_after_interaction_without_a_polling_timer():
    _app()
    dock = _Dock()
    memory = install_scene_memory(dock)
    set_scene_context(dock, "ligand", target="ligand_1")

    memory.eventFilter(dock.pymol_widget, QEvent(QEvent.MouseButtonPress))
    assert is_interacting(dock)
    memory.eventFilter(dock.pymol_widget, QEvent(QEvent.MouseButtonRelease))

    assert not is_interacting(dock)
    assert next(iter(memory.cache.values()))["view"] == (1.0, 2.0, 3.0)


def test_an_oriented_row_keeps_its_camera_over_the_remembered_one():
    _app()
    dock = _Dock()
    memory = install_scene_memory(dock)
    set_scene_context(dock, "receptor", target="receptor_1")
    memory.eventFilter(dock.pymol_widget, QEvent(QEvent.MouseButtonRelease))

    set_scene_context(dock, "receptor", target="receptor_1", restore_view=False)
    assert dock.cmd.restored is None
    set_scene_context(dock, "receptor", target="receptor_1")
    assert dock.cmd.restored == (1.0, 2.0, 3.0)


def test_an_additive_scene_keeps_earlier_roles_and_makes_a_complex():
    _app()
    dock = _Dock()
    set_additive(dock, True)
    dock.cmd.objects["rec"] = 0
    set_scene_context(dock, "receptor", target="rec", selections={"receptor": "rec"})
    dock.cmd.objects["lig"] = 0
    set_scene_context(dock, "ligand", target="lig", selections={"ligand": "lig"}, complex_preset="app.complex")

    context = dock.scene_context
    assert (context.kind, context.default_preset) == ("complex", "app.complex")
    assert context.selections == {"receptor": "rec", "ligand": "lig"}
    assert dock.cmd.calls[-1] == ("zoom", "lig or rec", 3)


def test_reloading_an_object_in_a_comparison_keeps_its_grid_slot():
    _app()
    dock = _Dock()
    set_additive(dock, True)
    dock.cmd.objects.update({"a": 1, "b": 2})
    set_scene_context(dock, "comparison", target="a or b", selections={"pose": "a or b"})

    prepare_scene(dock, "b")
    assert ("delete", "b") in dock.cmd.calls and "a" in dock.cmd.objects
    dock.cmd.objects["b"] = 0
    set_scene_context(dock, "comparison", target="b", selections={"pose": "b"})
    assert dock.cmd.objects == {"a": 1, "b": 2}


def test_a_replacing_scene_clears_everything():
    dock = _Dock()
    dock.cmd.objects.update({"a": 1})
    prepare_scene(dock, "b")
    assert dock.cmd.calls == [("delete", "all")] and not dock.cmd.objects


def test_clearing_the_scene_resets_its_context_without_replaying_a_style():
    _app()
    dock = _Dock()
    applied = []
    dock.control_bar = SimpleNamespace(apply_preset=applied.append)
    memory = install_scene_memory(dock)
    memory.keep_style = True
    dock.cmd.objects["lig"] = 0
    set_scene_context(dock, "ligand", target="lig", selections={"ligand": "lig"})
    memory.preset_applied("app.ligand")
    memory.eventFilter(dock.pymol_widget, QEvent(QEvent.MouseButtonRelease))
    remembered = dict(memory.cache)

    clear_scene(dock)

    assert ("delete", "all") in dock.cmd.calls and not dock.cmd.objects
    context = dock.scene_context
    assert (context.kind, context.target, context.selections) == ("generic", "all", {})
    assert (memory.key, memory.kind) == ("", "")
    assert not applied
    # The molecule's style and camera survive, and a later view change is not stored for it.
    dock.cmd.view = (9.0, 9.0, 9.0)
    memory.eventFilter(dock.pymol_widget, QEvent(QEvent.MouseButtonRelease))
    assert memory.cache == remembered
    assert memory.style_by_kind["ligand"].preset == "app.ligand"


def test_scene_menu_lists_its_sections():
    _app()
    menu = QMenu()
    add_scene_actions(menu, _Dock())
    titles = [action.text() for action in menu.actions() if action.text()]
    assert titles == ["Background", "Camera", "Render", "Surface", "Complex", "PyMOL Internal GUI"]
    render = next(action.menu() for action in menu.actions() if action.text() == "Render")
    assert [action.text() for action in render.actions()] == ["Shadows On", "Shadows Off", "Ray"]


def test_the_control_bar_registers_every_pymol_preset():
    from ms_components.ms_pymol.widget import PymolControlBar

    _app()
    keys = {spec.key for spec in PymolControlBar(None).available_presets()}
    assert {"pymol.default", "pymol.publication", "pymol.b_factor_putty", "pymol.protein_interface"} <= keys
