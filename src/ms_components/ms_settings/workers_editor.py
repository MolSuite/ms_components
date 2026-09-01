"""Editor for a configuration's ``workers`` collection (local + networked executors).

The generic key/value settings walker can only express scalar leaves, so the
polymorphic, dynamically-keyed ``workers`` map (process_pool / thread / ray / hpc,
each with type-specific fields) gets this dedicated editor instead. It reads and
writes through the provider's ``get_value("workers")`` / ``set_value("workers", ...)``
so persistence and validation stay in the configuration layer.
"""
from __future__ import annotations

import types
from typing import Any, Union, get_args, get_origin

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ms_components.step_dialog import run_steps_dialog
from ms_flow.core.executor.provisioning import test_steps
from ms_flow.core.settings.models import (
    HPCWorkerConfig,
    ProcessPoolWorkerConfig,
    RayWorkerConfig,
    ThreadWorkerConfig,
)

# Order matters: this drives the "Add" menu. Local types first, networked last.
_WORKER_TYPES: dict[str, type] = {
    "process_pool": ProcessPoolWorkerConfig,
    "thread": ThreadWorkerConfig,
    "ray": RayWorkerConfig,
    "hpc": HPCWorkerConfig,
}

# Not shown in the per-worker form: identity/type (managed by us) and the free-form
# command-env map (a nested dict the mini field-renderer can't express yet).
_HIDDEN_FIELDS = {"wid", "type", "name", "command_env"}


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """Return (base_type, nullable). Only simple ``Optional[T]`` is unwrapped;
    unions like ``Union[str, list[str]]`` are left as-is (rendered as text)."""
    origin = get_origin(annotation)
    if origin in (Union, getattr(types, "UnionType", None)):
        args = [a for a in get_args(annotation) if a is not type(None)]
        nullable = len(args) != len(get_args(annotation))
        if len(args) == 1:
            return args[0], nullable
        return annotation, nullable
    return annotation, False


class WorkersEditor(QWidget):
    """Edits happen in memory; nothing reaches disk until :meth:`commit` runs.

    The panel's "Save changes" drives that, so adding a worker behaves like every
    other setting instead of registering it behind the user's back.
    """

    def __init__(self, *, configuration, path: str = "workers", parent: QWidget | None = None):
        super().__init__(parent)
        self._configuration = configuration
        self._path = path
        self._workers: dict[str, dict] = {}
        self._editors: dict[str, QWidget] = {}
        self._current: str | None = None
        self._dirty = False
        self._build_ui()
        self.reload()

    # --- UI scaffold ---------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)
        self._list = QListWidget(self)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self._list, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self._add_button = QPushButton("Add…", self)
        self._add_button.clicked.connect(self._on_add_clicked)
        self._remove_button = QPushButton("Remove", self)
        self._remove_button.clicked.connect(self._on_remove_clicked)
        self._test_button = QPushButton("Test", self)
        self._test_button.setToolTip(
            "Check that this executor answers, using the settings shown here.\n"
            "SSH must already work for your user (keys/agent handled by the OS)."
        )
        self._test_button.clicked.connect(self._on_test_clicked)
        buttons.addWidget(self._add_button)
        buttons.addWidget(self._remove_button)
        buttons.addWidget(self._test_button)
        buttons.addStretch(1)
        left.addLayout(buttons)
        root.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(6)
        self._form_host = QVBoxLayout()
        self._form_group: QGroupBox | None = None
        right.addLayout(self._form_host, 1)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        right.addWidget(self._status)
        root.addLayout(right, 3)

    # --- Load / persist ------------------------------------------------------
    def reload(self) -> None:
        value = self._configuration.get_value(self._path)
        self._workers = value.model_dump() if hasattr(value, "model_dump") else dict(value or {})
        self._dirty = False
        self._repopulate_list()

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def commit(self) -> None:
        """Persist the staged workers. Raises so the panel can report the error."""
        if not self._dirty:
            return
        self._configuration.set_value(self._path, self._workers)
        self._dirty = False
        self._status.setText("Saved.")

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._status.setText("Unsaved changes — use “Save changes”.")

    def _repopulate_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for name, cfg in sorted(self._workers.items()):
            wtype = cfg.get("type", "?")
            enabled = "" if cfg.get("enabled", True) else "  (disabled)"
            item = QListWidgetItem(f"{name}  –  {wtype}{enabled}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self._list.addItem(item)
        self._list.blockSignals(False)
        if self._list.count():
            self._list.setCurrentRow(0)
        else:
            self._current = None
            self._clear_form()

    # --- Add / remove --------------------------------------------------------
    def _on_add_clicked(self) -> None:
        wtype, ok = QInputDialog.getItem(
            self, "Add worker", "Executor type:", list(_WORKER_TYPES), 0, False
        )
        if not ok or not wtype:
            return
        name, ok = QInputDialog.getText(self, "Add worker", "Name:", text=self._unique_name(wtype))
        name = name.strip()
        if not ok or not name:
            return
        if name in self._workers:
            QMessageBox.warning(self, "Add worker", f"'{name}' already exists.")
            return
        cls = _WORKER_TYPES[wtype]
        self._workers[name] = cls(name=name).model_dump()
        self._mark_dirty()
        self._repopulate_list()
        self._select_by_name(name)

    def _on_remove_clicked(self) -> None:
        if self._current and self._current in self._workers:
            del self._workers[self._current]
            self._mark_dirty()
            self._repopulate_list()

    def _on_test_clicked(self) -> None:
        worker = self._current_model()
        if worker is None:
            return
        run_steps_dialog(self, f"Test executor '{worker.name}'", test_steps(worker))

    def _current_model(self):
        """The staged config as its pydantic model (what a test/launch would use)."""
        if self._current is None:
            return None
        cfg = dict(self._workers[self._current])
        cls = _WORKER_TYPES.get(cfg.get("type", "process_pool"), ProcessPoolWorkerConfig)
        try:
            return cls(**cfg)
        except Exception as exc:  # noqa: BLE001 - invalid staged values are the user's to fix
            QMessageBox.warning(self, "Executor", f"Invalid configuration: {exc}")
            return None

    def _unique_name(self, wtype: str) -> str:
        base = wtype
        candidate = base
        counter = 1
        while candidate in self._workers:
            counter += 1
            candidate = f"{base}_{counter}"
        return candidate

    def _select_by_name(self, name: str) -> None:
        for row in range(self._list.count()):
            if self._list.item(row).data(Qt.ItemDataRole.UserRole) == name:
                self._list.setCurrentRow(row)
                return

    # --- Per-worker form -----------------------------------------------------
    def _on_selection_changed(self, current: QListWidgetItem | None, _prev=None) -> None:
        self._current = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._rebuild_form()

    def _clear_form(self) -> None:
        if self._form_group is not None:
            self._form_group.deleteLater()
            self._form_group = None
        self._editors = {}

    def _rebuild_form(self) -> None:
        self._clear_form()
        if self._current is None:
            return
        cfg = self._workers[self._current]
        cls = _WORKER_TYPES.get(cfg.get("type", "process_pool"), ProcessPoolWorkerConfig)
        group = QGroupBox(self._current, self)
        form = QFormLayout(group)
        for field_name, field in cls.model_fields.items():
            if field_name in _HIDDEN_FIELDS:
                continue
            value = cfg.get(field_name, field.default)
            editor = self._make_editor(field.annotation, value)
            self._connect_editor(editor, field_name, field.annotation)
            self._editors[field_name] = editor
            form.addRow(field_name, editor)
        self._form_host.addWidget(group)
        self._form_group = group

    def _make_editor(self, annotation: Any, value: Any) -> QWidget:
        base, _nullable = _unwrap_optional(annotation)
        if get_origin(base) is list:
            # worker_ips / setup_commands: one entry per line, no list widget needed.
            editor = QPlainTextEdit(self)
            editor.setPlaceholderText("one per line")
            editor.setPlainText("\n".join(str(item) for item in (value or [])))
            editor.setMaximumHeight(90)
            return editor
        if base is bool:
            editor = QCheckBox(self)
            editor.setChecked(bool(value))
            return editor
        if base is int:
            editor = QSpinBox(self)
            editor.setRange(-1_000_000_000, 1_000_000_000)
            editor.setValue(int(value) if value is not None else 0)
            return editor
        if base is float:
            editor = QDoubleSpinBox(self)
            editor.setRange(-1.0e12, 1.0e12)
            editor.setDecimals(3)
            editor.setValue(float(value) if value is not None else 0.0)
            return editor
        editor = QLineEdit(self)
        editor.setText("" if value is None else str(value))
        return editor

    def _connect_editor(self, editor: QWidget, field_name: str, annotation: Any) -> None:
        _base, nullable = _unwrap_optional(annotation)

        def commit(*_args):
            self._workers[self._current][field_name] = self._editor_value(editor, nullable)
            self._mark_dirty()
            # An "enabled" toggle changes the list label; refresh it in place.
            if field_name == "enabled":
                self._refresh_current_label()

        if isinstance(editor, QCheckBox):
            editor.toggled.connect(commit)
        elif isinstance(editor, (QSpinBox, QDoubleSpinBox)):
            editor.valueChanged.connect(commit)
        elif isinstance(editor, QComboBox):
            editor.currentIndexChanged.connect(commit)
        elif isinstance(editor, QPlainTextEdit):
            editor.textChanged.connect(commit)
        elif isinstance(editor, QLineEdit):
            editor.editingFinished.connect(commit)

    @staticmethod
    def _editor_value(editor: QWidget, nullable: bool) -> Any:
        if isinstance(editor, QCheckBox):
            return editor.isChecked()
        if isinstance(editor, QSpinBox):
            return int(editor.value())
        if isinstance(editor, QDoubleSpinBox):
            return float(editor.value())
        if isinstance(editor, QPlainTextEdit):
            return [line.strip() for line in editor.toPlainText().splitlines() if line.strip()]
        text = editor.text().strip()
        if not text and nullable:
            return None
        return text

    def _refresh_current_label(self) -> None:
        item = self._list.currentItem()
        if item is None or self._current is None:
            return
        cfg = self._workers[self._current]
        enabled = "" if cfg.get("enabled", True) else "  (disabled)"
        item.setText(f"{self._current}  –  {cfg.get('type', '?')}{enabled}")


__all__ = ["WorkersEditor"]
