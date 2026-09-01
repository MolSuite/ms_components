from __future__ import annotations

import enum
import json
from decimal import Decimal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_origin

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ms_flow.api import ConfigurationEntry


_SOURCE_LABELS = {
    "default": "DEFAULT",
    "global": "GLOBAL",
    "project": "PROJECT",
}


def _muted(label: QLabel, *, size: int = 11) -> None:
    palette = label.palette()
    color = palette.color(QPalette.ColorRole.WindowText)
    color.setAlphaF(0.62)
    palette.setColor(QPalette.ColorRole.WindowText, color)
    label.setPalette(palette)
    label.setStyleSheet(f"font-size: {size}px;")


def _path_text(value: Any) -> str:
    return str(value) if value is not None else "—"


def _decimals_for(default: Any) -> int:
    """How many decimals the default itself uses, 1..3. A fixed 6 turned every float
    into `2,000000`; the packaged default is the honest hint of the useful precision."""
    try:
        exponent = Decimal(str(float(default))).normalize().as_tuple().exponent
    except (TypeError, ValueError, ArithmeticError):
        return 2
    return min(3, max(1, -int(exponent))) if isinstance(exponent, int) else 2


def _titleize(segment: str) -> str:
    return segment.replace("_", " ").title()


def _set_hit(label: QLabel, hit: bool) -> None:
    label.setProperty("searchHit", "true" if hit else "false")
    label.style().unpolish(label)
    label.style().polish(label)


def _jsonable(value):
    """Last resort for `json.dumps`: pydantic model -> dict, anything else -> text."""
    dump = getattr(value, "model_dump", None)
    return dump(mode="json") if callable(dump) else str(value)


@dataclass
class _ParameterRow:
    configuration: Any
    entry: ConfigurationEntry
    editor: QWidget
    source_label: QLabel
    reset_target: QComboBox
    reset_button: QToolButton
    name_label: QLabel


@dataclass
class _Node:
    """One tree node = one settings page. Depth is capped at three (provider ▸ section
    ▸ subsection); anything deeper stays as rows on its grandparent's page."""

    key: str
    title: str
    parent_key: str | None
    configuration: Any = None
    entries: list = field(default_factory=list)
    child_keys: list = field(default_factory=list)
    custom: list = field(default_factory=list)
    widget: QWidget | None = None


class _NullableNumberEditor(QWidget):
    valueChanged = Signal()

    def __init__(self, *, floating_point: bool, minimum, maximum, decimals: int = 2, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.number = QDoubleSpinBox(self) if floating_point else QSpinBox(self)
        if floating_point:
            self.number.setRange(
                float(minimum) if minimum is not None else -1.0e12,
                float(maximum) if maximum is not None else 1.0e12,
            )
            self.number.setDecimals(decimals)
            self.number.setSingleStep(10.0**-decimals)
        else:
            self.number.setRange(
                int(minimum) if minimum is not None else -2147483648,
                int(maximum) if maximum is not None else 2147483647,
            )
        layout.addWidget(self.number, 1)
        self.none = QCheckBox("None", self)
        layout.addWidget(self.none)
        self.none.toggled.connect(self._toggle_none)
        self.number.valueChanged.connect(self.valueChanged.emit)

    def _toggle_none(self, checked: bool) -> None:
        self.number.setEnabled(not checked)
        self.valueChanged.emit()

    def setValue(self, value: Any) -> None:
        self.blockSignals(True)
        self.number.blockSignals(True)
        self.none.blockSignals(True)
        try:
            self.none.setChecked(value is None)
            self.number.setEnabled(value is not None)
            if value is not None:
                self.number.setValue(value)
        finally:
            self.none.blockSignals(False)
            self.number.blockSignals(False)
            self.blockSignals(False)

    def value(self) -> Any:
        return None if self.none.isChecked() else self.number.value()


class AppSettingsPanel(QWidget):
    """Tree + page typed editor for one or more layered MolSuite configurations.

    Layout follows the IDE convention: search box and a three-level tree on the left,
    breadcrumb and the selected page on the right."""

    settings_saved = Signal()

    def __init__(
        self,
        *,
        runtime=None,
        configurations=None,
        app_name: str | None = None,
        icon_provider=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.runtime = runtime
        self.app_name = str(app_name or getattr(runtime, "app_id", "Application")).strip()
        # Host app injects its themed icon(name)->QIcon loader so the dialog's icons match
        # the rest of the app; falls back to Qt standard icons when not provided.
        self._icon_provider = icon_provider
        self._configurations: dict[str, Any] = {}
        self._rows: dict[tuple[str, str], _ParameterRow] = {}
        self._nodes: dict[str, _Node] = {}
        self._items: dict[str, QTreeWidgetItem] = {}
        self._pages: dict[str, QWidget] = {}
        self._search_hits: dict[str, list[str]] = {}
        self._highlighted: list[QLabel] = []
        self._dirty_rows: set[tuple[str, str]] = set()
        # Editors that own a whole collection (workers map) and stage it themselves.
        self._custom_editors: list[Any] = []
        self._setup_ui()

        sources = configurations
        if sources is None and runtime is not None and hasattr(runtime, "configuration_sources"):
            sources = runtime.configuration_sources()
        for configuration in tuple(sources or ()):
            self.add_config(configuration)
        self._update_empty_state()

    def _icon(self, name: str, fallback: QStyle.StandardPixmap):
        if self._icon_provider is not None:
            try:
                candidate = self._icon_provider(name)
                if candidate is not None and not candidate.isNull():
                    return candidate
            except Exception:  # noqa: BLE001 - a missing asset falls back to the Qt standard icon
                pass
        return self.style().standardIcon(fallback)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        left = QWidget(self.splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        self.search_box = QLineEdit(left)
        self.search_box.setPlaceholderText("Search settings")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._apply_filter)
        left_layout.addWidget(self.search_box)
        self.tree = QTreeWidget(left)
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        left_layout.addWidget(self.tree, 1)
        self.splitter.addWidget(left)

        right = QWidget(self.splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        self.breadcrumb = QLabel(right)
        self.breadcrumb.setObjectName("breadcrumb")
        self.breadcrumb.setTextFormat(Qt.TextFormat.RichText)
        self.breadcrumb.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        # The inheritance note rides the breadcrumb: it is the only always-visible header.
        self.breadcrumb.setToolTip(
            "Values inherit from packaged defaults, then the user profile, then the active project."
        )
        self.breadcrumb.linkActivated.connect(self.select_node)
        right_layout.addWidget(self.breadcrumb)
        self.stack = QStackedWidget(right)
        right_layout.addWidget(self.stack, 1)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([250, 690])
        root.addWidget(self.splitter, 1)

        self.empty_label = QLabel("No configuration providers have been added.", self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _muted(self.empty_label, size=12)
        root.addWidget(self.empty_label, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.status_label = QLabel("", self)
        _muted(self.status_label, size=11)
        footer.addWidget(self.status_label, 1)
        self.reload_button = QPushButton("Reload", self)
        self.reload_button.clicked.connect(self.reload_values)
        footer.addWidget(self.reload_button)
        self.save_button = QPushButton("Save changes", self)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save_settings)
        footer.addWidget(self.save_button)
        # Optional Close button so the host dialog keeps all actions on one row
        # (see set_close_action); hidden until a host wires it up.
        self.close_button = QPushButton("Close", self)
        self.close_button.setVisible(False)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

        # ponytail: one application-wide filter, scoped by isAncestorOf, instead of one
        # filter per page widget — a click anywhere in the page area drops the search marks.
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)

        # No control-sizing overrides here: those made the widgets taller than the rest of
        # the app. Inherit the application theme; only style the bits the theme doesn't know
        # about (source badges, header labels, search hits), using palette roles so they
        # track the active theme instead of hardcoded colors.
        self.setStyleSheet(
            """
            QLabel#breadcrumb { font-size: 13px; font-weight: 600; padding: 2px 0 4px 0; }
            QLabel#columnHeader {
                font-size: 10px;
                font-weight: 650;
                color: palette(text);
            }
            QLabel[searchHit="true"] {
                background: rgba(255, 197, 66, 0.32);
                border-radius: 3px;
            }
            QLabel#sourceDefault, QLabel#sourceGlobal, QLabel#sourceProject {
                border-radius: 3px;
                padding: 2px 5px;
                font-size: 9px;
                font-weight: 700;
            }
            QLabel#sourceDefault { color: palette(text); background: rgba(128, 128, 128, 0.18); }
            QLabel#sourceGlobal { color: #4c9be8; background: rgba(76, 155, 232, 0.16); }
            QLabel#sourceProject { color: #34c88a; background: rgba(52, 200, 138, 0.16); }
            """
        )

    def eventFilter(self, watched, event):
        if (
            self._highlighted
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(watched, QWidget)
            and self.stack.isAncestorOf(watched)
        ):
            self._clear_highlight()
        return super().eventFilter(watched, event)

    def set_close_action(self, callback) -> None:
        """Show a Close button in the footer wired to ``callback`` (used by the host
        dialog so Reload / Save / Close share one row)."""
        self.close_button.setVisible(True)
        self.close_button.clicked.connect(callback)

    def _update_empty_state(self) -> None:
        has_configs = bool(self._configurations)
        has_pages = bool(self._pages)
        self.splitter.setVisible(has_pages)
        self.empty_label.setVisible(not has_pages)
        self.save_button.setEnabled(has_configs)
        self.reload_button.setEnabled(has_configs)

    def add_config(self, configuration) -> None:
        config_id = str(configuration.config_id)
        if config_id in self._configurations:
            raise ValueError(f"Configuration '{config_id}' has already been added.")
        self._configurations[config_id] = configuration
        root = self._node(config_id, str(configuration.display_name), None)
        root.configuration = configuration
        for entry in configuration.entries():
            segments = entry.path.split(".")
            node = root
            for segment in segments[:-1][:2]:
                node = self._node(f"{node.key}/{segment}", _titleize(segment), node.key)
                node.configuration = configuration
            node.entries.append(entry)
        provider = getattr(configuration, "custom_editors", None)
        for kind, path, title in provider() if callable(provider) else ():
            node = self._node(f"{config_id}/{path.split('.')[0]}", str(title), config_id)
            node.configuration = configuration
            node.custom.append((kind, path, title))
        self._build_branch(root.key)
        if self.tree.currentItem() is None:
            self.select_node(root.key)
        self._update_empty_state()

    def _node(self, key: str, title: str, parent_key: str | None) -> _Node:
        node = self._nodes.get(key)
        if node is None:
            node = _Node(key=key, title=title, parent_key=parent_key)
            self._nodes[key] = node
            if parent_key is not None:
                self._nodes[parent_key].child_keys.append(key)
        return node

    def _build_branch(self, key: str) -> None:
        node = self._nodes[key]
        item = QTreeWidgetItem(self._items[node.parent_key] if node.parent_key else self.tree)
        item.setText(0, node.title)
        item.setData(0, Qt.ItemDataRole.UserRole, node.key)
        item.setExpanded(node.parent_key is None)
        self._items[key] = item
        page = node.widget if node.widget is not None else self._build_page(node)
        self._pages[key] = page
        self.stack.addWidget(page)
        for child_key in tuple(node.child_keys):
            self._build_branch(child_key)

    def _build_page(self, node: _Node) -> QWidget:
        scroll = QScrollArea(self.stack)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 18)
        layout.setSpacing(12)

        configuration = node.configuration
        if node.parent_key is None and configuration is not None:
            description = QLabel(str(getattr(configuration, "description", "") or ""), content)
            description.setWordWrap(True)
            description.setVisible(bool(description.text()))
            _muted(description, size=11)
            layout.addWidget(description)

            paths = QLabel(self._layer_paths(configuration), content)
            paths.setWordWrap(True)
            paths.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            _muted(paths, size=10)
            paths.setObjectName(f"paths_{configuration.config_id}")
            layout.addWidget(paths)

            separator = QFrame(content)
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Plain)
            layout.addWidget(separator)

        if node.entries:
            layout.addWidget(self._build_grid(node, content))
        elif node.child_keys:
            # A node with no values of its own is a landing page: description + contents.
            toc = QLabel(content)
            toc.setTextFormat(Qt.TextFormat.RichText)
            toc.setText(
                "<br>".join(
                    f'<a href="{child_key}">{self._nodes[child_key].title}</a>'
                    for child_key in node.child_keys
                )
            )
            toc.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            toc.linkActivated.connect(self.select_node)
            layout.addWidget(toc)
        elif not node.custom:
            empty = QLabel("This section does not expose editable values.", content)
            _muted(empty)
            layout.addWidget(empty)

        self._add_custom_editors(node, layout, content)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _build_grid(self, node: _Node, parent: QWidget) -> QWidget:
        table = QWidget(parent)
        grid = QGridLayout(table)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)

        for column, span, text in ((0, 1, "NAME"), (1, 1, "VARIABLE"), (2, 2, "VALUE / SOURCE"), (4, 2, "RESET TO")):
            header = QLabel(text, table)
            header.setObjectName("columnHeader")
            grid.addWidget(header, 0, column, 1, span)

        for row_index, entry in enumerate(node.entries, start=1):
            row = self._add_parameter_row(grid, row_index, node.configuration, entry, table)
            self._rows[(node.configuration.config_id, entry.path)] = row
            if isinstance(row.editor, QLineEdit):
                grid.setColumnStretch(2, 1)
        return table

    def select_node(self, key: str) -> None:
        item = self._items.get(str(key))
        if item is not None:
            self.tree.setCurrentItem(item)

    def _on_tree_selection(self, current, _previous=None) -> None:
        if current is None:
            return
        key = str(current.data(0, Qt.ItemDataRole.UserRole))
        page = self._pages.get(key)
        if page is not None:
            self.stack.setCurrentWidget(page)
        self._update_breadcrumb(key)
        self._clear_highlight()
        self._apply_highlight(key)

    def _update_breadcrumb(self, key: str) -> None:
        trail = []
        cursor = self._nodes.get(key)
        while cursor is not None:
            trail.append(f'<a style="text-decoration:none;" href="{cursor.key}">{cursor.title}</a>')
            cursor = self._nodes.get(cursor.parent_key) if cursor.parent_key else None
        self.breadcrumb.setText(" &rsaquo; ".join(reversed(trail)))

    def _apply_filter(self, text: str) -> None:
        query = str(text).strip().lower()
        self._clear_highlight()
        self._search_hits = {}
        if not query:
            for key, item in self._items.items():
                item.setHidden(False)
                item.setExpanded(self._nodes[key].parent_key is None)
            return
        matched: set[str] = set()
        for key, node in self._nodes.items():
            hits = [
                entry.path
                for entry in node.entries
                if query in entry.name.lower()
                or query in entry.path.lower()
                or query in (entry.description or "").lower()
            ]
            if hits:
                self._search_hits[key] = hits
            if hits or query in node.title.lower():
                matched.add(key)
        visible: set[str] = set()
        for key in matched:
            cursor: str | None = key
            while cursor is not None:
                visible.add(cursor)
                cursor = self._nodes[cursor].parent_key
        for key, item in self._items.items():
            item.setHidden(key not in visible)
            item.setExpanded(True)
        first = next((key for key in self._nodes if key in matched), None)
        if first is not None:
            self.select_node(first)
            self._apply_highlight(first)

    def _apply_highlight(self, key: str) -> None:
        node = self._nodes.get(key)
        if node is None or node.configuration is None:
            return
        config_id = node.configuration.config_id
        for path in self._search_hits.get(key, ()):
            row = self._rows.get((config_id, path))
            if row is not None:
                _set_hit(row.name_label, True)
                self._highlighted.append(row.name_label)
        page = self._pages.get(key)
        if self._highlighted and isinstance(page, QScrollArea):
            target = self._highlighted[0]
            # Deferred: the page has just been swapped in, so it has no geometry yet.
            QTimer.singleShot(0, lambda: page.ensureWidgetVisible(target))

    def _clear_highlight(self) -> None:
        for label in self._highlighted:
            _set_hit(label, False)
        self._highlighted.clear()

    def _add_custom_editors(self, node: _Node, layout, parent) -> None:
        """A provider may expose ``custom_editors() -> [(kind, path, title), ...]`` to
        get a dedicated widget for a collection the scalar walker can't render (e.g. the
        ``workers`` executor map). Unknown kinds are skipped."""
        for kind, path, _title in node.custom:
            if kind != "workers":
                continue
            from ms_components.ms_settings.workers_editor import WorkersEditor

            widget = WorkersEditor(configuration=node.configuration, path=path, parent=parent)
            self._custom_editors.append(widget)
            layout.addWidget(widget)

    @staticmethod
    def _layer_paths(configuration) -> str:
        project_path = getattr(configuration, "project_path", None)
        return (
            f"Default  {_path_text(getattr(configuration, 'default_path', None))}\n"
            f"Global   {_path_text(getattr(configuration, 'global_path', None))}\n"
            f"Project  {_path_text(project_path) if project_path else 'No active project'}"
        )

    def _add_parameter_row(self, grid, row_index, configuration, entry, parent) -> _ParameterRow:
        name = QLabel(entry.name, parent)
        # One line, hugging the text: the column is sized by its widest name, and the
        # search highlight then marks the name instead of a whole empty cell.
        name.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        # The description lives on the label's tooltip instead of a dedicated info icon.
        name.setToolTip(entry.description or entry.name)
        grid.addWidget(name, row_index, 0)

        variable = QLabel(entry.path, parent)
        variable.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        variable.setToolTip(entry.path)
        variable.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        variable.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        _muted(variable, size=10)
        grid.addWidget(variable, row_index, 1)

        editor = self._create_editor(entry, parent)
        editor.setObjectName(f"config_{configuration.config_id}_{entry.path.replace('.', '_')}")
        if isinstance(editor, QLineEdit):
            # Free text (paths, JSON) is the only value worth the leftover width; a
            # spin box or combo just looks stretched.
            editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            editor.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            editor.setMaximumWidth(200)
        self._connect_dirty(editor, (configuration.config_id, entry.path))
        grid.addWidget(editor, row_index, 2)

        source_label = QLabel(parent)
        source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(source_label, row_index, 3)

        reset_target = QComboBox(parent)
        if bool(configuration.has_project):
            reset_target.addItem("Global", "global")
        reset_target.addItem("Default", "default")
        reset_target.setMaximumWidth(110)
        grid.addWidget(reset_target, row_index, 4)

        reset_button = QToolButton(parent)
        reset_button.setObjectName("resetButton")
        reset_button.setAutoRaise(True)
        reset_button.setIcon(self._icon("reset.svg", QStyle.StandardPixmap.SP_BrowserReload))
        reset_button.setToolTip("Apply the selected reset now")
        reset_button.setAccessibleName(f"Reset {entry.name}")
        grid.addWidget(reset_button, row_index, 5)

        row = _ParameterRow(configuration, entry, editor, source_label, reset_target, reset_button, name)
        reset_button.clicked.connect(lambda _checked=False, item=row: self._reset_row(item))
        self._load_row(row)
        return row

    @staticmethod
    def _create_editor(entry: ConfigurationEntry, parent: QWidget) -> QWidget:
        annotation = entry.annotation
        if entry.choices:
            editor = QComboBox(parent)
            if entry.nullable:
                editor.addItem("None", None)
            for choice in entry.choices:
                editor.addItem(str(choice), choice)
            return editor
        try:
            is_enum = isinstance(annotation, type) and issubclass(annotation, enum.Enum)
        except TypeError:
            is_enum = False
        if is_enum:
            editor = QComboBox(parent)
            for choice in annotation:
                editor.addItem(str(choice.value), choice.value)
            return editor
        if entry.nullable and annotation in (int, float):
            return _NullableNumberEditor(
                floating_point=annotation is float,
                minimum=entry.minimum,
                maximum=entry.maximum,
                decimals=_decimals_for(entry.default),
                parent=parent,
            )
        if entry.nullable and annotation is bool:
            editor = QComboBox(parent)
            editor.addItem("None", None)
            editor.addItem("Enabled", True)
            editor.addItem("Disabled", False)
            return editor
        if annotation is bool:
            return QCheckBox("Enabled", parent)
        if annotation is int:
            editor = QSpinBox(parent)
            minimum = int(entry.minimum) if entry.minimum is not None else -2147483648
            maximum = int(entry.maximum) if entry.maximum is not None else 2147483647
            editor.setRange(minimum, maximum)
            return editor
        if annotation is float:
            editor = QDoubleSpinBox(parent)
            editor.setRange(
                float(entry.minimum) if entry.minimum is not None else -1.0e12,
                float(entry.maximum) if entry.maximum is not None else 1.0e12,
            )
            decimals = _decimals_for(entry.default)
            editor.setDecimals(decimals)
            editor.setSingleStep(10.0**-decimals)
            return editor
        editor = QLineEdit(parent)
        if get_origin(annotation) in (list, dict, tuple, set):
            editor.setPlaceholderText("JSON value")
        elif annotation is Path:
            editor.setPlaceholderText("Filesystem path")
        elif entry.nullable:
            editor.setPlaceholderText("Empty means None")
        return editor

    def _connect_dirty(self, editor: QWidget, key: tuple[str, str]) -> None:
        callback = lambda *_args: self._mark_dirty(key)
        if isinstance(editor, QCheckBox):
            editor.toggled.connect(callback)
        elif isinstance(editor, _NullableNumberEditor):
            editor.valueChanged.connect(callback)
        elif isinstance(editor, (QSpinBox, QDoubleSpinBox)):
            editor.valueChanged.connect(callback)
        elif isinstance(editor, QComboBox):
            editor.currentIndexChanged.connect(callback)
        elif isinstance(editor, QLineEdit):
            editor.textEdited.connect(callback)

    def _mark_dirty(self, key: tuple[str, str]) -> None:
        self._dirty_rows.add(key)
        self.status_label.setText("Unsaved changes.")

    @staticmethod
    def _set_editor_value(editor: QWidget, value: Any) -> None:
        editor.blockSignals(True)
        try:
            if isinstance(editor, QCheckBox):
                editor.setChecked(bool(value))
            elif isinstance(editor, _NullableNumberEditor):
                editor.setValue(value)
            elif isinstance(editor, QSpinBox):
                editor.setValue(int(value))
            elif isinstance(editor, QDoubleSpinBox):
                editor.setValue(float(value))
            elif isinstance(editor, QComboBox):
                index = editor.findData(value)
                if index < 0:
                    index = editor.findText(str(value))
                editor.setCurrentIndex(max(0, index))
            elif isinstance(editor, QLineEdit):
                if value is None:
                    text = ""
                elif isinstance(value, (dict, list, tuple, set)):
                    # `default=` because a collection may carry pydantic models inside
                    # (per-table state, worker maps): showing them must not blow up.
                    text = json.dumps(value, separators=(",", ":"), default=_jsonable)
                else:
                    text = str(value)
                editor.setText(text)
        finally:
            editor.blockSignals(False)

    @staticmethod
    def _editor_value(row: _ParameterRow) -> Any:
        editor = row.editor
        entry = row.entry
        if isinstance(editor, QCheckBox):
            return editor.isChecked()
        if isinstance(editor, _NullableNumberEditor):
            return editor.value()
        if isinstance(editor, QSpinBox):
            return int(editor.value())
        if isinstance(editor, QDoubleSpinBox):
            return float(editor.value())
        if isinstance(editor, QComboBox):
            return editor.currentData()
        if isinstance(editor, QLineEdit):
            text = editor.text().strip()
            if not text and entry.nullable:
                return None
            if get_origin(entry.annotation) in (list, dict, tuple, set):
                return json.loads(text)
            return text
        raise TypeError(f"Unsupported configuration editor: {type(editor).__name__}")

    @staticmethod
    def _update_source_label(label: QLabel, source: str) -> None:
        normalized = source if source in _SOURCE_LABELS else "default"
        label.setText(_SOURCE_LABELS[normalized])
        label.setObjectName(f"source{normalized.title()}")
        label.style().unpolish(label)
        label.style().polish(label)

    def _load_row(self, row: _ParameterRow) -> None:
        self._set_editor_value(row.editor, row.configuration.get_value(row.entry.path))
        self._update_source_label(row.source_label, row.configuration.get_source(row.entry.path))
        selected = row.reset_target.currentData()
        row.reset_target.blockSignals(True)
        row.reset_target.clear()
        if bool(row.configuration.has_project):
            row.reset_target.addItem("Global", "global")
        row.reset_target.addItem("Default", "default")
        selected_index = row.reset_target.findData(selected)
        if selected_index >= 0:
            row.reset_target.setCurrentIndex(selected_index)
        row.reset_target.blockSignals(False)

    def editor(self, config_id: str, path: str | None = None) -> QWidget:
        if path is None:
            matches = [row.editor for (candidate_id, candidate_path), row in self._rows.items() if candidate_path == config_id]
            if len(matches) == 1:
                return matches[0]
            raise KeyError(config_id)
        return self._rows[(config_id, path)].editor

    def add_page(self, widget: QWidget, title: str) -> None:
        """Host a self-managing page (no config rows) as one more top-level tree node.

        The page saves on its own -- "Save changes" and "Reload" ignore it."""
        node = self._node(f"page:{title}", str(title), None)
        node.widget = widget
        self._build_branch(node.key)
        self._update_empty_state()

    def parameter_row(self, config_id: str, path: str) -> _ParameterRow:
        return self._rows[(config_id, path)]

    def tab_ids(self) -> tuple[str, ...]:
        return tuple(self._configurations)

    def reload_values(self) -> None:
        for row in self._rows.values():
            self._load_row(row)
        for config_id, configuration in self._configurations.items():
            label = self._pages[config_id].findChild(QLabel, f"paths_{config_id}")
            if label is not None:
                label.setText(self._layer_paths(configuration))
        for editor in self._custom_editors:
            editor.reload()
        self._dirty_rows.clear()
        self.status_label.setText("Values reloaded.")

    def save_settings(self) -> None:
        pending_custom = [editor for editor in self._custom_editors if editor.is_dirty]
        if not self._dirty_rows and not pending_custom:
            self.status_label.setText("No changes to save.")
            return
        try:
            values = [
                (self._rows[key], self._editor_value(self._rows[key]))
                for key in tuple(self._dirty_rows)
            ]
            for row, value in values:
                row.configuration.set_value(row.entry.path, value)
            # Custom editors (the workers map) stage their own state; Save is what
            # writes it, same as every scalar row.
            for editor in pending_custom:
                editor.commit()
        except Exception as exc:
            self.status_label.setText("Changes were not saved.")
            QMessageBox.critical(self, f"{self.app_name} configuration", str(exc))
            return
        self.reload_values()
        self.status_label.setText("Changes saved.")
        self.settings_saved.emit()

    def _reset_row(self, row: _ParameterRow) -> None:
        target = str(row.reset_target.currentData())
        try:
            row.configuration.reset_value(row.entry.path, target)
        except Exception as exc:
            self.status_label.setText("Value was not reset.")
            QMessageBox.critical(self, f"{self.app_name} configuration", str(exc))
            return
        self._load_row(row)
        self._dirty_rows.discard((row.configuration.config_id, row.entry.path))
        suffix = " Other changes are still unsaved." if self._dirty_rows else ""
        self.status_label.setText(f"{row.entry.name} reset to {target}.{suffix}")
        self.settings_saved.emit()


class AppSettingsDialog(QDialog):
    settings_saved = Signal()

    def __init__(
        self,
        *,
        runtime=None,
        configurations=None,
        app_name: str | None = None,
        icon_provider=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        title = str(app_name or getattr(runtime, "app_id", "Application")).strip()
        self.setWindowTitle(f"{title} Configuration")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(1000, 660)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.panel = AppSettingsPanel(
            runtime=runtime,
            configurations=configurations,
            app_name=title,
            icon_provider=icon_provider,
            parent=self,
        )
        self.panel.settings_saved.connect(self.settings_saved.emit)
        # Close joins Reload / Save changes in the panel's own footer row.
        self.panel.set_close_action(self.close)
        layout.addWidget(self.panel, 1)


__all__ = ["AppSettingsDialog", "AppSettingsPanel"]
