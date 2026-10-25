from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ms_components.ms_dockwidget.widget import MSDockWidget
from ms_components.opengl import pymol_context_error, pymol_surface_format

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import QByteArray, QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

try:
    from pmg_qt.pymol_gl_widget import PyMOLGLWidget
except ImportError:
    PyMOLGLWidget = QWidget

# Ensure helper commands like cmd.draw_box are registered on the embedded PyMOL cmd.
from . import plugins as _pymol_plugins  # noqa: F401


class _PymolGLWidget(PyMOLGLWidget):
    before_render = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self._opengl_error: str | None = None
        self._opengl_error_label: QLabel | None = None
        if hasattr(self, "setFormat"):
            self.setFormat(pymol_surface_format(self.format()))

    def initializeGL(self):
        context = self.context()
        self._opengl_error = pymol_context_error(context)
        if self._opengl_error_label is not None:
            self._opengl_error_label.hide()
        if self._opengl_error:
            logging.getLogger(__name__).error(self._opengl_error)
            if self._opengl_error_label is None:
                self._opengl_error_label = QLabel(self)
                self._opengl_error_label.setWordWrap(True)
                QVBoxLayout(self).addWidget(self._opengl_error_label)
            self._opengl_error_label.setText(f"PyMOL viewer unavailable.\n{self._opengl_error}")
            self._opengl_error_label.show()
            return
        fmt = context.format()
        logging.getLogger(__name__).info(
            "PyMOL context: %s, OpenGL %s.%s %s",
            QGuiApplication.platformName(), *fmt.version(), fmt.profile().name,
        )
        super().initializeGL()

    def paintGL(self):
        if self._opengl_error is None:
            self.before_render.emit()
            super().paintGL()

    def resizeGL(self, width, height):
        if self._opengl_error is None:
            super().resizeGL(width, height)


SELECTION_MODES = (
    ("Atoms", 0),
    ("Residues", 1),
    ("Chains", 2),
    ("Objects", 4),
)
REPRESENTATIONS = (
    ("Cartoon", "cartoon"),
    ("Sticks", "sticks"),
    ("Lines", "lines"),
    ("Surface", "surface"),
    ("Spheres", "spheres"),
    ("Ribbon", "ribbon"),
    ("Dots", "dots"),
)

_TOOLBAR_ICONS = Path(__file__).parent / "icons"
COMPARISON_COLORS = (
    "orange", "tv_green", "cyan", "magenta", "yellow",
    "salmon", "violet", "lime", "deepteal", "hotpink",
)


@dataclass(frozen=True)
class PymolSceneContext:
    kind: str = "generic"
    target: str = "all"
    selections: Mapping[str, str] = field(default_factory=dict)
    default_preset: str = ""
    grid_labels: Mapping[int, str] = field(default_factory=dict)

    @property
    def is_comparison(self) -> bool:
        return self.kind in {"comparison", "offtarget"}

    def selection(self, role: str, fallback: str = "") -> str:
        value = str(dict(self.selections or {}).get(str(role)) or "").strip()
        return value or str(fallback or "").strip()


@dataclass(frozen=True)
class PymolPresetSpec:
    key: str
    label: str
    callback: Callable[[Any, PymolSceneContext], None]
    contexts: frozenset[str] = field(default_factory=frozenset)
    tooltip: str = ""

    def supports(self, context_kind: str) -> bool:
        return not self.contexts or str(context_kind) in self.contexts


def _builtin_preset(method_name: str):
    def apply(cmd, context: PymolSceneContext) -> None:
        from pymol import preset

        method = getattr(preset, method_name)
        method(str(context.target or "all"), _self=cmd)

    return apply


class PymolControlBar(QFrame):
    """Compact, reusable controls for an embedded PyMOL scene."""

    selection_mode_changed = Signal(int)
    preset_applied = Signal(str)
    command_failed = Signal(str)

    def __init__(self, cmd, parent: QWidget | None = None):
        super().__init__(parent)
        self._cmd = cmd
        self._context = PymolSceneContext()
        self._grid_label_objects: set[str] = set()
        self._comparison_layout = "grid"
        self._hydrogen_mode = "none"
        self._presets: dict[str, PymolPresetSpec] = {}
        self.setObjectName("PymolControlBar")

        self._toolbar_action_icons: dict[QAction, str] = {}
        self._selection_mode_actions: dict[int, QAction] = {}
        self._overflow_btn: QToolButton | None = None

        # Every control is a QAction. This is required for an embedded QToolBar to
        # populate its extension menu when it is not owned by a QMainWindow.
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 1, 6, 1)
        outer.setSpacing(0)
        bar = self.toolbar = QToolBar(self)
        bar.setObjectName("PymolToolbar")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setIconSize(QSize(16, 16))
        bar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        outer.addWidget(bar, 1)

        selection_menu = QMenu("Selection", bar)
        selection_group = QActionGroup(selection_menu)
        selection_group.setExclusive(True)
        for label, value in SELECTION_MODES:
            action = selection_menu.addAction(label)
            action.setCheckable(True)
            action.setData(value)
            selection_group.addAction(action)
            action.triggered.connect(
                lambda checked=False, mode=value: self._set_selection_mode(mode)
            )
            self._selection_mode_actions[value] = action
        selection_menu.addSeparator()
        selection_menu.addAction("Clear selection", self.clear_selection)
        self.selection_mode_action = self._add_toolbar_action(
            "Selection", "selection.svg",
            "Mouse selection granularity used when clicking the 3D scene.",
            menu=selection_menu,
        )

        actions_menu = QMenu("Actions", bar)
        for label, icon_name, callback in (
            ("Zoom", "zoom.svg", self.zoom_active),
            ("Orient", "orient.svg", self.orient_active),
            ("Center", "center.svg", self.center_active),
        ):
            action = actions_menu.addAction(self._toolbar_icon(icon_name), label)
            action.triggered.connect(callback)
        self.actions_action = self._add_toolbar_action(
            "Actions", "actions.svg",
            "Zoom, orient, or center the current PyMOL selection or scene target.",
            menu=actions_menu,
        )

        representation_menu = QMenu("Display", bar)
        for label, value in REPRESENTATIONS:
            action = representation_menu.addAction(label)
            action.setData(value)
            action.triggered.connect(
                lambda checked=False, representation=value:
                self.apply_representation(representation)
            )
        self.representation_action = self._add_toolbar_action(
            "Display", "display.svg",
            "Apply a representation to the current selection or scene target.",
            menu=representation_menu,
        )
        self.comparison_menu = representation_menu.addMenu("Comparison")
        self.comparison_menu.menuAction().setVisible(False)
        comparison_group = QActionGroup(self.comparison_menu)
        comparison_group.setExclusive(True)
        self._comparison_layout_actions: dict[str, QAction] = {}
        for label, value in (("Grid", "grid"), ("Overlay", "overlay")):
            action = self.comparison_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(value == self._comparison_layout)
            comparison_group.addAction(action)
            action.triggered.connect(lambda checked=False, layout=value: self.set_comparison_layout(layout))
            self._comparison_layout_actions[value] = action

        hide_menu = QMenu("Hide", bar)
        for label, value in (("Everything", "everything"), *REPRESENTATIONS):
            action = hide_menu.addAction(label)
            action.setData(value)
            action.triggered.connect(
                lambda checked=False, representation=value:
                self.hide_representation(representation)
            )
        self.hide_action = self._add_toolbar_action(
            "Hide", "hide.svg",
            "Hide a representation from the current selection or scene target.",
            menu=hide_menu,
        )

        self.hydrogens_action = self._add_toolbar_action(
            "Hydrogens", "hydrogens.svg",
            "Hydrogens: hidden. Click to show all H in this PyMOL session.",
            self.toggle_hydrogens,
            checkable=True,
        )
        self.hydrogens_action.setData("none")

        self.preset_menu = QMenu("Presets", bar)
        self.preset_action = self._add_toolbar_action(
            "Presets", "presets.svg",
            "Apply a preset compatible with the current molecular scene.",
            menu=self.preset_menu,
        )

        self.context_label = QLabel("Generic", self)
        self.context_label.setObjectName("PymolSceneContext")
        self.context_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.context_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.context_label.setToolTip("Current molecular scene context.")
        outer.addWidget(self.context_label)

        self._register_builtin_presets()
        self._sync_selection_mode()
        self.refresh_context_label()
        self._refresh_preset_menu()
        self.apply_hydrogen_visibility()
        self._configure_overflow_button()
        if self._cmd is None:
            self.setEnabled(False)

    def _add_toolbar_action(
        self,
        text: str,
        icon_name: str,
        tooltip: str,
        callback: Callable[[], None] | None = None,
        *,
        menu: QMenu | None = None,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(self._toolbar_icon(icon_name), text, self.toolbar)
        action.setToolTip(tooltip)
        action.setCheckable(checkable)
        if menu is not None:
            action.setMenu(menu)
        if callback is not None:
            action.triggered.connect(lambda checked=False: callback())
        self.toolbar.addAction(action)
        self._toolbar_action_icons[action] = icon_name

        button = self.toolbar.widgetForAction(action)
        if isinstance(button, QToolButton):
            button.setObjectName("PymolToolbarButton")
            if menu is not None:
                button.setPopupMode(QToolButton.InstantPopup)
        return action

    def add_menu_action(
        self,
        text: str,
        menu: QMenu,
        *,
        icon_name: str = "settings.svg",
        tooltip: str = "",
    ) -> QAction:
        """Add an application menu that participates in native toolbar overflow."""
        action = self._add_toolbar_action(
            text, icon_name, tooltip or text, menu=menu
        )
        self._configure_overflow_button()
        return action

    def add_action(
        self,
        text: str,
        *,
        icon_name: str,
        tooltip: str = "",
        callback: Callable[[], None] | None = None,
        checkable: bool = False,
    ) -> QAction:
        """Add one application action to the embedded toolbar."""
        action = self._add_toolbar_action(
            text,
            icon_name,
            tooltip or text,
            callback,
            checkable=checkable,
        )
        self._configure_overflow_button()
        return action

    def _toolbar_icon(self, name: str) -> QIcon:
        svg = (_TOOLBAR_ICONS / name).read_bytes().replace(
            b"currentColor", self.palette().buttonText().color().name().encode()
        )
        dpr = max(1.0, self.devicePixelRatioF())
        toolbar = self.toolbar
        size = toolbar.iconSize() if toolbar is not None and isValid(toolbar) else QSize(16, 16)
        pixmap = QPixmap(
            max(1, round(size.width() * dpr)),
            max(1, round(size.height() * dpr)),
        )
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg)).render(painter)
        painter.end()
        return QIcon(pixmap)

    def _refresh_toolbar_icons(self) -> None:
        for action, icon_name in tuple(self._toolbar_action_icons.items()):
            if not isValid(action):
                self._toolbar_action_icons.pop(action, None)
                continue
            action.setIcon(self._toolbar_icon(icon_name))
        button = self._overflow_btn
        if button is None:
            return
        if not isValid(button):
            self._overflow_btn = None
            return
        button.setIcon(self._toolbar_icon("menu.svg"))

    def _configure_overflow_button(self) -> None:
        toolbar = self.toolbar
        if toolbar is None or not isValid(toolbar):
            self._overflow_btn = None
            return
        button = toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
        if button is None or not isValid(button):
            self._overflow_btn = None
            return
        if self._overflow_btn is not button:
            self._overflow_btn = button
            button.installEventFilter(self)
            button.destroyed.connect(self._on_overflow_button_destroyed)
        button.setArrowType(Qt.NoArrow)
        button.setText("")
        button.setIcon(self._toolbar_icon("menu.svg"))
        button.setIconSize(QSize(14, 14))
        button.setFixedWidth(20)
        button.setMinimumHeight(18)
        button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        button.setToolTip("More PyMOL actions")

    def _on_overflow_button_destroyed(self, *_args) -> None:
        self._overflow_btn = None

    def eventFilter(self, watched, event):
        if watched is self._overflow_btn and event.type() == QEvent.Type.Enter:
            QTimer.singleShot(0, self._show_overflow_menu)
        return super().eventFilter(watched, event)

    def _show_overflow_menu(self) -> None:
        button = self._overflow_btn
        if button is None:
            return
        if not isValid(button):
            self._overflow_btn = None
            return
        if button.isHidden() or not button.isEnabled():
            return
        menu = button.menu()
        if menu is None or menu.isVisible():
            return
        button.showMenu()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._refresh_toolbar_icons()

    @property
    def scene_context(self) -> PymolSceneContext:
        return self._context

    def set_scene_context(
        self,
        context: PymolSceneContext | str,
        *,
        target: str = "all",
        selections: Mapping[str, str] | None = None,
        default_preset: str = "",
        grid_labels: Mapping[int, str] | None = None,
    ) -> None:
        if isinstance(context, PymolSceneContext):
            normalized = context
        else:
            normalized = PymolSceneContext(
                kind=str(context or "generic").strip().lower() or "generic",
                target=str(target or "all").strip() or "all",
                selections={
                    str(key): str(value)
                    for key, value in dict(selections or {}).items()
                    if str(key).strip() and str(value).strip()
                },
                default_preset=str(default_preset or "").strip(),
                grid_labels=dict(grid_labels or {}),
            )
        was_comparison = self._context.is_comparison
        self._context = normalized
        self.comparison_menu.menuAction().setVisible(normalized.is_comparison)
        if was_comparison or normalized.is_comparison:
            self._run_command("Grid labels", self._sync_grid_labels)
        self.apply_hydrogen_visibility()
        self.refresh_context_label()
        self._refresh_preset_menu()

    @property
    def comparison_layout(self) -> str:
        return self._comparison_layout

    def set_comparison_layout(self, layout: str) -> None:
        if layout not in self._comparison_layout_actions:
            raise ValueError(f"Unsupported comparison layout: {layout}")
        if not self._context.is_comparison:
            raise ValueError("A comparison scene is required to change its layout.")
        previous = self._comparison_layout
        self._comparison_layout = layout

        def apply() -> None:
            self._sync_grid_labels()
            self._cmd.refresh()

        if not self._run_command("Comparison layout", apply):
            self._comparison_layout = previous
        for value, action in self._comparison_layout_actions.items():
            action.setChecked(value == self._comparison_layout)

    def _sync_grid_labels(self, *, color_objects: bool = True) -> None:
        labels = dict(self._context.grid_labels)
        if self._context.is_comparison:
            self._cmd.set("grid_mode", int(self._comparison_layout == "grid"))
            slot_names: dict[int, list[str]] = {}
            for obj in self._cmd.get_object_list(self._context.target):
                if obj in self._grid_label_objects:
                    continue
                slot = self._cmd.get_setting_int("grid_slot", obj)
                if slot > 0:
                    color = COMPARISON_COLORS[(slot - 1) % len(COMPARISON_COLORS)]
                    if color_objects:
                        self._cmd.set("cartoon_color", color, selection=obj)
                        self._cmd.color(color, f"({obj}) and elem C")
                    slot_names.setdefault(slot, []).append(self._cmd.get_title(obj, 1) or obj)
            if not labels:
                labels = {slot: " + ".join(names) for slot, names in slot_names.items()}
        else:
            labels = {}
            self._cmd.set("grid_mode", 0)

        wanted = {f"panel_text{slot}" for slot in labels}
        for obj in self._grid_label_objects - wanted:
            self._cmd.delete(obj)
        self._grid_label_objects.intersection_update(wanted)
        existing = set(self._cmd.get_names("objects"))
        for slot, title in sorted(labels.items()):
            if slot <= 0:
                raise ValueError("Grid label slots must be positive integers.")
            obj = f"panel_text{slot}"
            if obj not in existing:
                self._cmd.pseudoatom(obj, label=title)
                self._grid_label_objects.add(obj)
                self._cmd.hide("everything", obj)
                self._cmd.set("label_relative_mode", 1, selection=obj)
                self._cmd.set("label_size", 14, selection=obj)
                self._cmd.set("label_position", [1, -1, 0], selection=obj)
                self._cmd.set("grid_slot", slot, selection=obj)
            elif obj in self._grid_label_objects:
                self._cmd.label(obj, repr(title))
            else:
                raise ValueError(f"Grid label object '{obj}' already exists.")
            color = COMPARISON_COLORS[(slot - 1) % len(COMPARISON_COLORS)]
            self._cmd.set("label_color", color, selection=obj)
            self._cmd.set("label_outline_color", "front", selection=obj)
            self._cmd.show("labels", obj)
        self._position_comparison_labels()

    def _position_comparison_labels(self) -> None:
        if not self._context.is_comparison:
            return
        existing = set(self._cmd.get_names("objects"))
        height = max(1, self._cmd.get_viewport()[1])
        offset = 0.0
        for obj in sorted(self._grid_label_objects & existing,
                          key=lambda name: self._cmd.get_setting_int("grid_slot", name)):
            self._cmd.set("label_screen_point", [-1, 1 - offset, 0], selection=obj)
            if self._comparison_layout == "overlay":
                offset += 2 * (abs(self._cmd.get_setting_float("label_size", obj)) + 6) / height

    def replace_comparison_object(
        self, name: str, data: bytes, fmt: str, *, reference: str, label: str,
    ) -> bool:
        def apply() -> None:
            if not self._context.is_comparison:
                raise ValueError("A comparison scene is required to replace an object.")
            objects = self._cmd.get_names("objects")
            if name not in objects or reference not in objects:
                raise ValueError("The comparison object and its reference must already exist.")
            if name == reference:
                raise ValueError("The comparison object must differ from its reference.")
            slot = self._cmd.get_setting_int("grid_slot", reference)
            if slot <= 0:
                raise ValueError("The comparison reference must have a positive grid slot.")
            auto_zoom = self._cmd.get_setting_int("auto_zoom")
            temporary = self._cmd.get_unused_name("_comparison_pose")
            try:
                self._cmd.set("auto_zoom", 0)
                self._cmd.load_raw(data, fmt, temporary)
                self._cmd.matrix_copy(reference, temporary)
                self._cmd.set("grid_slot", slot, temporary)
                self._cmd.show("sticks", temporary)
                self._cmd.color("atomic", temporary)
                color = COMPARISON_COLORS[(slot - 1) % len(COMPARISON_COLORS)]
                self._cmd.set("cartoon_color", color, temporary)
                self._cmd.color(color, f"({temporary}) and elem C")
                self._cmd.delete(name)
                self._cmd.set_name(temporary, name)
                self._context = replace(
                    self._context, grid_labels={**self._context.grid_labels, slot: label},
                )
                self._sync_grid_labels(color_objects=False)
            finally:
                if temporary in self._cmd.get_names("objects"):
                    self._cmd.delete(temporary)
                self._cmd.set("auto_zoom", auto_zoom)

        return self._run_command("Replace comparison object", apply)

    def register_preset(self, spec: PymolPresetSpec) -> None:
        key = str(spec.key or "").strip()
        if not key:
            raise ValueError("A PyMOL preset requires a non-empty key.")
        if not callable(spec.callback):
            raise TypeError("A PyMOL preset callback must be callable.")
        self._presets[key] = spec
        self._refresh_preset_menu()

    def unregister_preset(self, key: str) -> None:
        self._presets.pop(str(key or "").strip(), None)
        self._refresh_preset_menu()

    def available_presets(self) -> list[PymolPresetSpec]:
        kind = str(self._context.kind or "generic")
        return [
            spec
            for spec in self._presets.values()
            if spec.supports(kind)
        ]

    def active_target(self) -> str:
        if self._cmd is not None:
            try:
                if int(self._cmd.count_atoms("sele") or 0) > 0:
                    return "sele"
            except Exception:
                pass
        return str(self._context.target or "all").strip() or "all"

    def zoom_active(self) -> None:
        self._run_command(
            "Zoom",
            lambda: self._cmd.zoom(self.active_target(), 4),
        )

    def orient_active(self) -> None:
        self._run_command(
            "Orient",
            lambda: self._cmd.orient(self.active_target()),
        )

    def center_active(self) -> None:
        self._run_command(
            "Center",
            lambda: self._cmd.center(self.active_target()),
        )

    def apply_representation(self, representation: str) -> None:
        normalized = str(representation or "").strip().lower()
        if normalized not in {value for _label, value in REPRESENTATIONS}:
            raise ValueError(f"Unsupported PyMOL representation: {representation}")
        target = self.active_target()

        def apply() -> None:
            self._cmd.hide("everything", target)
            self._cmd.show(normalized, target)
            self.apply_hydrogen_visibility()

        self._run_command(f"Display {normalized}", apply)

    def hide_representation(self, representation: str) -> None:
        normalized = str(representation or "").strip().lower()
        valid = {"everything", *(value for _label, value in REPRESENTATIONS)}
        if normalized not in valid:
            raise ValueError(f"Unsupported PyMOL representation: {representation}")
        self._run_command(
            f"Hide {normalized}",
            lambda: self._cmd.hide(normalized, self.active_target()),
        )

    def toggle_hydrogens(self) -> None:
        previous = self._hydrogen_mode
        modes = ("none", "all", "polar")
        self._hydrogen_mode = modes[(modes.index(previous) + 1) % len(modes)]
        if not self.apply_hydrogen_visibility():
            self._hydrogen_mode = previous
        mode = self._hydrogen_mode
        icon = "hydrogens-polar.svg" if mode == "polar" else "hydrogens.svg"
        self._toolbar_action_icons[self.hydrogens_action] = icon
        self.hydrogens_action.setIcon(self._toolbar_icon(icon))
        self.hydrogens_action.setChecked(mode != "none")
        self.hydrogens_action.setData(mode)
        state, next_state = {
            "none": ("hidden", "show all H"),
            "all": ("all H", "show only polar H"),
            "polar": ("polar H only (bonded to N, O or S)", "hide all H"),
        }[mode]
        self.hydrogens_action.setToolTip(
            f"Hydrogens: {state}. Click to {next_state} in this PyMOL session."
        )

    def apply_hydrogen_visibility(self) -> bool:
        # Enforce the session policy before drawing, including externally loaded objects.
        polar = "hydro and neighbor (elem N+O+S)"
        shown = {"none": "", "all": "hydro", "polar": polar}[self._hydrogen_mode]
        hidden = {"none": "hydro", "all": "", "polar": f"hydro and not ({polar})"}[self._hydrogen_mode]

        def apply() -> None:
            if hidden and self._cmd.count_atoms(f"({hidden}) and visible"):
                self._cmd.hide("everything", hidden)
            if shown and self._cmd.count_atoms(f"({shown}) and not rep sticks"):
                self._cmd.show("sticks", shown)

        return self._run_command("Hydrogens", apply)

    def clear_selection(self) -> None:
        if self._run_command("Clear selection", self._cmd.deselect):
            self.refresh_context_label()

    def refresh_context_label(self) -> None:
        """Keep the compact context label useful without turning it into a second status bar."""
        kind = str(self._context.kind or "generic").replace("_", " ").title()
        target = str(self._context.target or "all").strip() or "all"
        summary, details = self._active_selection_summary()
        if not summary and target != "all":
            summary = target
        self.context_label.setText(f"{kind} · {summary}" if summary else kind)
        context_lines = [f"Scene: {kind}", f"Target: {target}"]
        for role, selection in dict(self._context.selections or {}).items():
            context_lines.append(f"{str(role).title()}: {selection}")
        self.context_label.setToolTip("\n".join([*context_lines, *details]))

    def _active_selection_summary(self) -> tuple[str, list[str]]:
        if self._cmd is None:
            return "", []
        try:
            atom_count = int(self._cmd.count_atoms("sele") or 0)
        except Exception:
            return "", []
        if atom_count <= 0:
            return "", []
        residues: set[tuple[str, str, str]] = set()
        try:
            self._cmd.iterate(
                "sele",
                "residues.add((chain, resn, resi))",
                space={"residues": residues},
            )
        except Exception:
            return f"{atom_count} selected atom{'s' if atom_count != 1 else ''}", []
        labels = [
            f"{chain + ':' if chain else ''}{resi} {resn}"
            for chain, resn, resi in sorted(residues)
        ]
        if not labels:
            return f"{atom_count} selected atom{'s' if atom_count != 1 else ''}", []
        compact = ", ".join(labels[:2])
        if len(labels) > 2:
            compact += f" +{len(labels) - 2}"
        full = labels[:20]
        if len(labels) > 20:
            full.append(f"… +{len(labels) - 20} more")
        return compact, ["Selected residues:", *full]

    def apply_preset(self, key: str) -> None:
        normalized_key = str(key or "").strip()
        spec = self._presets.get(normalized_key)
        if spec is None or not spec.supports(self._context.kind):
            raise ValueError(
                f"PyMOL preset '{normalized_key}' is not available for "
                f"context '{self._context.kind}'."
            )

        def apply() -> None:
            spec.callback(self._cmd, self._context)
            self.apply_hydrogen_visibility()
            if self._context.is_comparison:
                self._sync_grid_labels()

        if self._run_command(spec.label, apply):
            self.preset_applied.emit(normalized_key)

    def _register_builtin_presets(self) -> None:
        for key, label, method in (
            ("pymol.default", "PyMOL · Default", "default"),
            ("pymol.simple", "PyMOL · Simple", "simple"),
            ("pymol.ball_and_stick", "PyMOL · Ball and stick", "ball_and_stick"),
            ("pymol.pretty", "PyMOL · Pretty", "pretty"),
            ("pymol.publication", "PyMOL · Publication", "publication"),
        ):
            self._presets[key] = PymolPresetSpec(
                key=key,
                label=label,
                callback=_builtin_preset(method),
            )

    def _sync_selection_mode(self) -> None:
        current = 1
        if self._cmd is not None:
            try:
                current = int(self._cmd.get_setting_int("mouse_selection_mode"))
            except Exception:
                pass
        selected = self._selection_mode_actions.get(current)
        if selected is None:
            selected = self._selection_mode_actions.get(1)
        if selected is not None:
            selected.setChecked(True)

    def _set_selection_mode(self, mode: int) -> None:
        mode = int(mode)
        if self._run_command(
            "Selection mode",
            lambda: self._cmd.set("mouse_selection_mode", mode, quiet=1),
        ):
            self.selection_mode_changed.emit(mode)
            self.refresh_context_label()

    def _refresh_preset_menu(self) -> None:
        available = self.available_presets()
        default_key = str(self._context.default_preset or "").strip()
        if default_key:
            available.sort(key=lambda spec: spec.key != default_key)
        self.preset_menu.clear()
        for spec in available:
            action = self.preset_menu.addAction(spec.label)
            action.setData(spec.key)
            if spec.tooltip:
                action.setToolTip(spec.tooltip)
            action.triggered.connect(
                lambda checked=False, key=spec.key: self._apply_preset_from_menu(key)
            )

    def _apply_preset_from_menu(self, key: str) -> None:
        try:
            self.apply_preset(key)
        except (TypeError, ValueError) as exc:
            self.command_failed.emit(str(exc))

    def _run_command(self, label: str, callback: Callable[[], None]) -> bool:
        if self._cmd is None:
            self.command_failed.emit(f"{label}: PyMOL is not available.")
            return False
        try:
            callback()
            return True
        except Exception as exc:
            self.command_failed.emit(f"{label}: {exc}")
            return False


class PymolDockWidget(MSDockWidget):
    side_panel_visibility_changed = Signal(bool)

    def __init__(self, title: str, manager, parent=None):
        super().__init__(title, manager, parent)
        self.pymol_widget = _PymolGLWidget(self)
        if self.cmd is not None:
            self.cmd.set("internal_gui", False)

        self.control_bar = PymolControlBar(self.cmd, self)
        self.pymol_widget.before_render.connect(self.control_bar.apply_hydrogen_visibility)
        self.toolbar = self.control_bar
        self.pymol_widget.installEventFilter(self)

        self._side_panel_widget: QWidget | None = None
        self._splitter = QSplitter(Qt.Horizontal, self)
        self._splitter.setChildrenCollapsible(False)
        # The side container has a 220px minimum and the viewer had none, so in a narrow dock
        # the panel took everything and the 3D view vanished. Floor the viewer instead.
        self.pymol_widget.setMinimumWidth(240)
        self._splitter.addWidget(self.pymol_widget)

        self._side_container = QWidget(self)
        self._side_container.setMinimumWidth(220)
        self._side_container.setMaximumWidth(360)
        self._side_container.hide()
        self._side_layout = QVBoxLayout(self._side_container)
        self._side_layout.setContentsMargins(0, 0, 0, 0)
        self._side_layout.setSpacing(0)
        self._side_title = QLabel("", self._side_container)
        self._side_title.setStyleSheet("font-weight: 600; padding: 4px 6px;")
        self._side_layout.addWidget(self._side_title)
        self._splitter.addWidget(self._side_container)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.control_bar)
        layout.addWidget(self._splitter, 1)

        container = QWidget()
        container.setLayout(layout)
        self.setWidget(container)

    @property
    def cmd(self):
        return getattr(self.pymol_widget, "cmd", None)

    @property
    def scene_context(self) -> PymolSceneContext:
        return self.control_bar.scene_context

    def set_scene_context(
        self,
        context: PymolSceneContext | str,
        *,
        target: str = "all",
        selections: Mapping[str, str] | None = None,
        default_preset: str = "",
        grid_labels: Mapping[int, str] | None = None,
    ) -> None:
        self.control_bar.set_scene_context(
            context,
            target=target,
            selections=selections,
            default_preset=default_preset,
            grid_labels=grid_labels,
        )

    def register_preset(self, spec: PymolPresetSpec) -> None:
        self.control_bar.register_preset(spec)

    def set_comparison_layout(self, layout: str) -> None:
        self.control_bar.set_comparison_layout(layout)

    @property
    def comparison_layout(self) -> str:
        return self.control_bar.comparison_layout

    def replace_comparison_object(
        self, name: str, data: bytes, fmt: str, *, reference: str, label: str,
    ) -> bool:
        return self.control_bar.replace_comparison_object(name, data, fmt, reference=reference, label=label)

    def unregister_preset(self, key: str) -> None:
        self.control_bar.unregister_preset(key)

    def set_side_panel(self, widget: QWidget | None, *, title: str = "", visible: bool = False) -> None:
        if self._side_panel_widget is widget and widget is not None:
            self._side_title.setText(str(title or ""))
            self.set_side_panel_visible(visible)
            return
        if self._side_panel_widget is not None:
            self._side_layout.removeWidget(self._side_panel_widget)
            self._side_panel_widget.setParent(None)
        self._side_panel_widget = widget
        self._side_title.setText(str(title or ""))
        if widget is not None:
            self._side_layout.addWidget(widget, 1)
        self.set_side_panel_visible(visible)

    def set_side_panel_visible(self, visible: bool) -> None:
        was_visible = self.is_side_panel_visible()
        visible = bool(visible and self._side_panel_widget is not None)
        self._side_container.setVisible(visible)
        if self._side_panel_widget is not None:
            self._side_panel_widget.setVisible(visible)
        if visible:
            self._splitter.setSizes([max(480, self.width() - 280), 280])
        else:
            self._splitter.setSizes([1, 0])
        if visible != was_visible:
            self.side_panel_visibility_changed.emit(visible)

    def is_side_panel_visible(self) -> bool:
        return bool(self._side_container.isVisible())

    def eventFilter(self, watched, event):
        if watched is self.pymol_widget and event.type() == QEvent.Type.MouseButtonRelease:
            QTimer.singleShot(0, self.control_bar.refresh_context_label)
        elif watched is self.pymol_widget and event.type() == QEvent.Type.Resize and self.scene_context.is_comparison:
            QTimer.singleShot(0, self.control_bar._position_comparison_labels)
        return super().eventFilter(watched, event)


__all__ = [
    "COMPARISON_COLORS",
    "PymolControlBar",
    "PymolDockWidget",
    "PymolPresetSpec",
    "PymolSceneContext",
    "REPRESENTATIONS",
    "SELECTION_MODES",
]
