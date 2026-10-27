"""Scene helpers for an embedded PyMOL: atom coloring, an additive scene, per-molecule view
memory and the Scene menu (background, camera, render, surface, complex).

Functions take the PyMOL ``cmd`` or the dock (anything with ``cmd``, ``control_bar`` and
``pymol_widget``), so an application can call them on its own dock or a test double.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox, QWidget

from .widget import COMPARISON_COLORS

RECEPTOR_CARBON_COLOR = "slate"
HETEROATOM_COLORS = {
    "O": "red",
    "N": "blue",
    "S": "yellow",
    "P": "orange",
    "F": "cyan",
    "Cl": "green",
    "Br": "firebrick",
    "I": "purple",
    "H": "white",
}
# Residue nature → color: acidic, basic, polar, aromatic, hydrophobic.
RESIDUE_NATURE_COLORS = {
    "red": ("ASP", "GLU"),
    "blue": ("ARG", "LYS", "HIS"),
    "green": ("SER", "THR", "ASN", "GLN", "CYS"),
    "orange": ("PHE", "TRP", "TYR"),
    "gray70": ("ALA", "VAL", "LEU", "ILE", "MET", "PRO", "GLY"),
}


# --- selections and coloring ---------------------------------------------------------------

def object_list(cmd, selection: str) -> list[str]:
    """Object names in `selection`; [] on a bad selection or a cmd without get_object_list."""
    get_object_list = getattr(cmd, "get_object_list", None)
    if not callable(get_object_list):
        return []
    try:
        return [str(name) for name in (get_object_list(selection) or []) if str(name).strip()]
    except Exception:
        return []


def select_atoms(cmd, name: str, selection: str) -> bool:
    """Make the named selection; True when it holds atoms."""
    try:
        cmd.select(name, selection)
        count = cmd.count_atoms(name)
        return True if count is None else int(count) > 0
    except Exception:
        return False


def _color(cmd, color: str, selection: str) -> None:
    try:
        cmd.color(color, selection)
    except Exception:
        pass


def color_atoms(cmd, selection: str, carbon_color: str) -> None:
    """Carbons in `carbon_color`, heteroatoms by element."""
    selection = str(selection or "").strip()
    if not selection:
        return
    scoped = f"({selection})"
    _color(cmd, carbon_color, f"{scoped} and elem C")
    for element, color in HETEROATOM_COLORS.items():
        _color(cmd, color, f"{scoped} and elem {element}")


def color_by_residue_nature(cmd, selection: str) -> None:
    selection = str(selection or "").strip()
    if not selection:
        return
    for color, resns in RESIDUE_NATURE_COLORS.items():
        _color(cmd, color, f"({selection}) and resn {'+'.join(resns)}")


def _default_color_role(cmd, selection: str, role: str) -> None:
    color_atoms(cmd, selection, RECEPTOR_CARBON_COLOR if role == "receptor" else COMPARISON_COLORS[0])


def frame(cmd, selection: str, buffer: float = 2.0) -> None:
    """Move the camera so `selection` fits the panel in both directions. PyMOL's zoom fits the
    height only, so a tall, narrow panel cuts the sides off."""
    import numpy as np

    xyz = cmd.get_coords(selection)
    width, height = cmd.get_viewport()
    if xyz is None or width <= 0 or height <= 0:
        return
    view = list(cmd.get_view())
    camera = (xyz - np.asarray(view[12:15])) @ np.reshape(view[:9], (3, 3))  # model -> camera axes
    half_x, half_y = np.abs(camera[:, :2]).max(axis=0) + buffer
    tan = math.tan(math.radians(float(cmd.get("field_of_view")) / 2))
    distance = float(max(half_y, half_x * height / width) / tan + np.abs(camera[:, 2]).max())
    shift = distance - abs(view[11])
    view[11] = -distance  # negative: the camera looks down -z at the origin
    view[15] += shift  # the clipping planes are measured from the camera
    view[16] += shift
    cmd.set_view(view)


# --- additive scene ------------------------------------------------------------------------
# Additive: new structures join the scene instead of replacing it (e.g. Shift+click on rows).
# A structure loaded again under the same name keeps its comparison grid slot.

def is_additive(dock) -> bool:
    return bool(getattr(dock, "scene_additive", False))


def set_additive(dock, additive: bool) -> None:
    dock.scene_additive = bool(additive)


def clear_scene(dock) -> None:
    dock.cmd.delete("all")
    dock._scene_replaced_slots = {}


def prepare_scene(dock, *objects: str) -> None:
    """Before loading `objects`: clear the scene, or in an additive scene drop only those."""
    cmd = dock.cmd
    dock._scene_replaced_slots = {}
    if not is_additive(dock):
        cmd.delete("all")
        return
    existing = set(cmd.get_names("objects"))
    for obj in objects:
        if obj in existing:
            slot = cmd.get_setting_int("grid_slot", obj)
            if slot > 0:
                dock._scene_replaced_slots[obj] = slot
        cmd.delete(obj)


def set_scene_context(
    dock,
    kind: str,
    *,
    target: str = "all",
    selections: dict[str, str] | None = None,
    default_preset: str = "",
    restore_view: bool = True,
    grid_labels: dict[int, str] | None = None,
    complex_preset: str = "",
) -> None:
    """Set the dock's scene context, then restore the molecule's remembered style and view.

    In an additive scene the roles of the previous context are kept: a pair of receptor and
    ligand becomes a "complex" (with `complex_preset`), a comparison grows a grid slot per new
    object. `restore_view=False` keeps the camera the caller just set."""
    if is_additive(dock):
        cmd = dock.cmd
        previous = getattr(dock, "scene_context", None)
        if previous is not None and not any(object_list(cmd, s) for s in previous.selections.values()):
            previous = None
        roles = dict(selections or {})
        if previous is not None:
            for role, selection in previous.selections.items():
                names = object_list(cmd, selection)
                names.extend(object_list(cmd, roles.get(role, "none")))
                if names:
                    roles[role] = " or ".join(dict.fromkeys(names))
        selections = roles
        objects = list(dict.fromkeys(obj for selection in roles.values() for obj in object_list(cmd, selection)))
        replaced_slots = getattr(dock, "_scene_replaced_slots", {})
        for obj in objects:
            if obj in replaced_slots:
                cmd.set("grid_slot", replaced_slots.pop(obj), obj)
        target = " or ".join(objects) or target
        if (previous is not None and previous.is_comparison) or kind in {"comparison", "offtarget"}:
            kind = "comparison"
            grid_labels = {**(dict(previous.grid_labels) if previous is not None else {}), **(grid_labels or {})}
            slots = {obj: cmd.get_setting_int("grid_slot", obj) for obj in objects}
            unassigned = [obj for obj, slot in slots.items() if slot <= 0]
            if unassigned:
                slot = max([0, *slots.values()]) + 1
                for obj in unassigned:
                    cmd.set("grid_slot", slot, obj)
                grid_labels[slot] = " + ".join(unassigned)
        elif "receptor" in roles and "ligand" in roles:
            kind, default_preset = "complex", complex_preset
        elif len(roles) > 1:
            kind, default_preset = "generic", ""
    setter = getattr(dock, "set_scene_context", None)
    if callable(setter):
        setter(kind, target=target, selections=selections, default_preset=default_preset, grid_labels=grid_labels)
    memory = getattr(dock, "scene_memory", None)
    if memory is not None:
        memory.apply(kind, target, selections, restore_view=restore_view)
    if is_additive(dock) and kind not in {"comparison", "offtarget"}:
        dock.cmd.zoom(target, 3)


# --- per-molecule style and view memory ----------------------------------------------------
# Two things persist across molecule switches: the chosen style per molecule kind ("Keep
# style"), and orientation+style per molecule (an LRU of VIEW_CACHE_LIMIT; surfaces recompute).
# The embedded widget has no viewport-changed signal, so mouse release and wheel are the
# boundaries: they keep the final camera without calling into PyMOL mid-drag.
VIEW_CACHE_LIMIT = 20


class SceneMemory(QObject):
    def __init__(self, dock) -> None:
        super().__init__(dock if isinstance(dock, QObject) else None)
        self._dock = dock
        self.cache: OrderedDict[str, dict] = OrderedDict()
        self.style_by_kind: dict[str, str] = {}
        self.key = ""
        self.kind = ""
        self.keep_style = False
        self.interacting = False  # a mouse button is down on the canvas
        self._wheel_pending = False

    def apply(self, kind: str, target: str, selections: dict[str, str] | None, *, restore_view: bool = True) -> None:
        kind = str(kind or "generic")
        sel = "|".join(f"{k}={v}" for k, v in sorted((selections or {}).items()))
        self.key, self.kind = f"{kind}::{target or 'all'}::{sel}", kind
        entry = self.cache.get(self.key)
        if entry is not None:
            self.cache.move_to_end(self.key)
            if entry.get("preset"):
                self._apply_preset(entry["preset"])
            if restore_view and entry.get("view") is not None:
                try:
                    self._dock.cmd.set_view(entry["view"])  # last, over any preset zoom
                except Exception:
                    pass
        elif self.keep_style and self.style_by_kind.get(kind):
            self._apply_preset(self.style_by_kind[kind])

    def preset_applied(self, key: str) -> None:
        if not key:
            return
        if self.kind:
            self.style_by_kind[self.kind] = key
        if self.key:
            self._store(preset=key)

    def remember_view(self) -> None:
        cmd = getattr(self._dock, "cmd", None)
        if not self.key or cmd is None:
            return
        try:
            self._store(view=cmd.get_view())
        except Exception:
            pass

    def _store(self, **values) -> None:
        self.cache[self.key] = {**self.cache.get(self.key, {}), **values}
        self.cache.move_to_end(self.key)
        while len(self.cache) > VIEW_CACHE_LIMIT:
            self.cache.popitem(last=False)

    def _apply_preset(self, key: str) -> None:
        try:
            self._dock.control_bar.apply_preset(key)
        except Exception:
            pass  # preset not valid for this context: leave the scene as it is

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.MouseButtonPress:
            self.interacting = True
        elif event.type() == QEvent.MouseButtonRelease:
            self.interacting = False
            self.remember_view()
        elif event.type() == QEvent.Wheel and not self._wheel_pending:
            self._wheel_pending = True
            QTimer.singleShot(0, self._remember_after_wheel)
        return False

    def _remember_after_wheel(self) -> None:
        self._wheel_pending = False
        self.remember_view()


def install_scene_memory(dock) -> SceneMemory:
    """`dock.scene_memory`, created once, plus a "Keep style" toggle on the control bar."""
    memory = getattr(dock, "scene_memory", None)
    if memory is not None:
        return memory
    memory = dock.scene_memory = SceneMemory(dock)
    bar = getattr(dock, "control_bar", None)
    if getattr(bar, "preset_applied", None) is not None:
        bar.preset_applied.connect(memory.preset_applied)
    if hasattr(bar, "add_action"):
        keep = bar.add_action(
            "Keep style", icon_name="style.svg", checkable=True,
            tooltip="Keep the current style when switching to another molecule of the same type.",
        )
        keep.toggled.connect(lambda checked: setattr(memory, "keep_style", bool(checked)))
        memory.keep_style_action = keep
    viewer = getattr(dock, "pymol_widget", None)
    if viewer is not None:
        viewer.installEventFilter(memory)
    return memory


def is_interacting(dock) -> bool:
    """A mouse button is down on the canvas: a good moment not to redraw the scene."""
    return bool(getattr(getattr(dock, "scene_memory", None), "interacting", False))


# --- Scene menu ----------------------------------------------------------------------------

def menu_action(menu: QMenu, text: str, handler: Callable[[], None], *, tooltip: str = "") -> QAction:
    action = menu.addAction(text)
    if tooltip:
        action.setToolTip(tooltip)
    action.triggered.connect(lambda _checked=False: handler())
    return action


def add_scene_actions(
    menu: QMenu,
    dock,
    *,
    color_role: Callable[[object, str, str], None] | None = None,
) -> QMenu:
    """Append Background, Camera, Render, Surface, Complex and the internal-GUI toggle to `menu`.

    `color_role(cmd, selection, role)` colors the protein ("receptor") and ligand ("ligand")
    in the Complex actions; the default is carbons by role, heteroatoms by element."""
    color_role = color_role or _default_color_role
    parent = menu.parentWidget() if isinstance(menu.parentWidget(), QWidget) else None

    def run(label: str, work: Callable[[object], None]) -> Callable[[], None]:
        def handler() -> None:
            cmd = getattr(dock, "cmd", None)
            if cmd is None:
                return
            try:
                work(cmd)
            except Exception as exc:
                QMessageBox.warning(parent, "PyMOL", f"Could not {label}:\n{exc}")
        return handler

    def complex_selections(cmd) -> tuple[str, str]:
        protein, ligand = "ms_complex_protein", "ms_complex_ligand"
        select_atoms(cmd, protein, "polymer.protein")
        if not select_atoms(cmd, ligand, "organic and not solvent"):
            select_atoms(cmd, ligand, "not polymer.protein and not solvent")
        return protein, ligand

    def protein_ligand(cmd) -> None:
        protein, ligand = complex_selections(cmd)
        cmd.hide("everything", "all")
        cmd.show("cartoon", protein)
        cmd.show("sticks", ligand)
        color_role(cmd, protein, "receptor")
        color_role(cmd, ligand, "ligand")
        cmd.show("lines", "solvent")
        cmd.set("cartoon_transparency", 0.12, protein)
        cmd.zoom(ligand, 5)

    def focus_ligand(cmd) -> None:
        _protein, ligand = complex_selections(cmd)
        cmd.show("sticks", ligand)
        cmd.zoom(ligand, 4)
        cmd.orient(ligand)

    def pocket(cmd) -> None:
        protein, ligand = complex_selections(cmd)
        name = "ms_complex_pocket"
        cmd.select(name, f"byres ({protein} within 5 of {ligand})")
        cmd.show("sticks", name)
        color_role(cmd, name, "receptor")
        cmd.show("surface", name)
        cmd.set("transparency", 0.55, name)
        cmd.zoom(f"({name} or {ligand})", 4)

    def save_png(cmd) -> None:
        filename, _filter = QFileDialog.getSaveFileName(
            parent, "Save PyMOL Image", str(Path.home() / "pymol.png"), "PNG Images (*.png)"
        )
        if filename:
            cmd.png(filename, ray=1)

    background = menu.addMenu("Background")
    for label, color in (("White", "white"), ("Black", "black"), ("Grey", "grey20")):
        menu_action(background, label, run("set the background", lambda cmd, c=color: cmd.bg_color(c)))

    camera = menu.addMenu("Camera")
    menu_action(camera, "Orthoscopic", run("set the camera", lambda cmd: cmd.set("orthoscopic", 1)))
    menu_action(camera, "Perspective", run("set the camera", lambda cmd: cmd.set("orthoscopic", 0)))

    render = menu.addMenu("Render")
    menu_action(render, "Shadows On", run("set shadows", lambda cmd: cmd.set("ray_shadows", 1)))
    menu_action(render, "Shadows Off", run("set shadows", lambda cmd: cmd.set("ray_shadows", 0)))
    menu_action(render, "Ray", run("ray-trace", lambda cmd: cmd.ray()))
    menu_action(render, "Save PNG…", run("save the PNG", save_png))

    surface = menu.addMenu("Surface")
    menu_action(surface, "Vacuum Electrostatics…", lambda: _vacuum_electrostatics(dock, parent),
                tooltip="Generate a charge-colored surface (Generate > Vacuum electrostatics). Slow.")

    complex_menu = menu.addMenu("Complex")
    menu_action(complex_menu, "Protein–Ligand", run("apply the protein-ligand view", protein_ligand),
                tooltip="Protein cartoon, ligand sticks, ligand-focused camera.")
    menu_action(complex_menu, "Focus Ligand", run("focus the ligand", focus_ligand))
    menu_action(complex_menu, "Pocket", run("show the pocket", pocket),
                tooltip="Residues within 5 Å of the ligand as sticks + transparent surface.")

    menu.addSeparator()
    gui = menu.addAction("PyMOL Internal GUI")
    gui.setCheckable(True)
    gui.setChecked(False)  # the dock starts with internal_gui off
    gui.setToolTip("Show or hide PyMOL's built-in on-canvas menu/object panel.")
    gui.toggled.connect(lambda checked: _internal_gui(dock, checked))
    return menu


def _repaint(dock) -> None:
    widget = getattr(dock, "pymol_widget", None)
    if widget is not None:
        try:
            widget.update()
        except Exception:
            pass


def _internal_gui(dock, checked: bool) -> None:
    cmd = getattr(dock, "cmd", None)
    if cmd is not None:
        cmd.set("internal_gui", 1 if checked else 0)
        _repaint(dock)


def _vacuum_electrostatics(dock, parent) -> None:
    cmd = getattr(dock, "cmd", None)
    if cmd is None:
        return
    # protein_vacuum_esp needs a single EXISTING object name, not a selection expression.
    objects = object_list(cmd, "polymer.protein") or object_list(cmd, "all")
    if not objects:
        QMessageBox.warning(parent, "PyMOL", "Load a protein object first.")
        return
    target = objects[0]
    reply = QMessageBox.question(
        parent, "PyMOL",
        f"Generate vacuum electrostatics for '{target}'?\n\nThis can take a while and may briefly freeze the window.",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return
    try:
        from pymol import util

        # ponytail: runs on the GUI thread; PyMOL's cmd isn't safe to drive from a worker.
        util.protein_vacuum_esp(target, mode=2, quiet=0, _self=cmd)
        _repaint(dock)
    except Exception as exc:
        QMessageBox.warning(
            parent, "PyMOL",
            f"Could not generate vacuum electrostatics for '{target}':\n{exc}\n\nThe target must be a single protein object.",
        )
