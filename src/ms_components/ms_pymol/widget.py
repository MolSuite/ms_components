from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ms_components.ms_dockwidget.widget import MSDockWidget

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import QByteArray, QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon, QPainter, QPixmap
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


@dataclass(frozen=True)
class PymolSceneContext:
    kind: str = "generic"
    target: str = "all"
    selections: Mapping[str, str] = field(default_factory=dict)
    default_preset: str = ""

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
            )
        self._context = normalized
        self.refresh_context_label()
        self._refresh_preset_menu()

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
        self.pymol_widget = PyMOLGLWidget(self)
        self.pymol_widget.installEventFilter(self)
        if self.cmd is not None:
            self.cmd.set("internal_gui", False)

        self.control_bar = PymolControlBar(self.cmd, self)
        self.toolbar = self.control_bar

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
    ) -> None:
        self.control_bar.set_scene_context(
            context,
            target=target,
            selections=selections,
            default_preset=default_preset,
        )

    def register_preset(self, spec: PymolPresetSpec) -> None:
        self.control_bar.register_preset(spec)

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
        return super().eventFilter(watched, event)


__all__ = [
    "PymolControlBar",
    "PymolDockWidget",
    "PymolPresetSpec",
    "PymolSceneContext",
    "REPRESENTATIONS",
    "SELECTION_MODES",
]
