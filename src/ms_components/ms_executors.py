"""The machines that run jobs and who runs them on them.

`KeptPage` is a Settings page: the entries kept under one name each (`hosts` or `executors`)
and the form of the one chosen. `ExecutorsPanel` is the quick window that starts and stops the
executors. Both go through a `ms_flow.Workspace` (`save_host`, `remove_host`, `save_executor`,
`remove_executor`, `executors`, `activate`, `deactivate`), which is who refuses what is not to
be done now, and says why.
"""
from __future__ import annotations

import threading
import types
from typing import Any, Literal, Union, get_args, get_origin

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def _editor(field, value: Any, parent: QWidget, hosts=()) -> QWidget:
    annotation, options = field.annotation, get_args(field.annotation)
    if get_origin(annotation) in (Union, types.UnionType) and options == (bool, type(None)):
        editor = QComboBox(parent)
        for text, data in (("Automatic", None), ("Yes", True), ("No", False)):
            editor.addItem(text, data)
    elif get_origin(annotation) is Literal:
        editor = QComboBox(parent)
        for option in options:
            editor.addItem(str(option), option)
    elif get_origin(annotation) is list:  # names of hosts: the ones kept, to tick
        editor = QListWidget(parent)
        editor.setMaximumHeight(110)
        for host in hosts:
            item = QListWidgetItem("local (this computer)" if host == "local" else host, editor)
            item.setData(Qt.ItemDataRole.UserRole, host)
            item.setCheckState(Qt.CheckState.Checked if host in (value or ()) else Qt.CheckState.Unchecked)
        return editor
    elif get_origin(annotation) is dict:
        editor = QPlainTextEdit("\n".join(f"{key} = {path}" for key, path in (value or {}).items()), parent)
        editor.setPlaceholderText("vina = /opt/vina/bin/vina")
        editor.setMaximumHeight(90)
        return editor
    elif annotation is bool:
        editor = QCheckBox(parent)
        editor.setChecked(bool(value))
        return editor
    elif annotation in (int, float):
        editor = QSpinBox(parent) if annotation is int else QDoubleSpinBox(parent)
        # A number with a limit here is one that starts at 0; the others also say "all but".
        editor.setRange(0 if field.metadata else -4096, 1_000_000)
        editor.setValue(value or 0)
        return editor
    else:
        return QLineEdit(str(value or ""), parent)
    editor.setCurrentIndex(max(0, editor.findData(value)))
    return editor


def _value(editor: QWidget) -> Any:
    if isinstance(editor, QComboBox):
        return editor.currentData()
    if isinstance(editor, QCheckBox):
        return editor.isChecked()
    if isinstance(editor, (QSpinBox, QDoubleSpinBox)):
        return editor.value()
    if isinstance(editor, QListWidget):
        items = [editor.item(row) for row in range(editor.count())]
        return [item.data(Qt.ItemDataRole.UserRole) for item in items if item.checkState() == Qt.CheckState.Checked]
    if isinstance(editor, QPlainTextEdit):
        pairs = (line.partition("=") for line in editor.toPlainText().splitlines() if "=" in line)
        return {key.strip(): path.strip() for key, _, path in pairs}
    return editor.text().strip()


class KeptPage(QWidget):
    """The entries kept in `table` (`hosts` or `executors`) and the form of the chosen one.

    "Save" and "Remove" act at once, through the workspace: an entry is whole or it is not
    kept, so the "Save changes" of the dialog around this page is not for it.
    """

    changed = Signal()

    def __init__(self, workspace, table: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._workspace, self._table, self._one = workspace, table, table[:-1]
        settings = type(workspace.settings_manager.settings)
        self._model = get_args(settings.model_fields[table].annotation)[1]
        self._editors: dict[str, QWidget] = {}
        self._body: QWidget | None = None

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.names = QListWidget(self)
        self.names.setMaximumWidth(190)
        self.names.currentTextChanged.connect(lambda name: name and self._show(name))
        left.addWidget(self.names, 1)
        buttons = QHBoxLayout()
        self.new_button = QPushButton("New", self)
        self.new_button.clicked.connect(lambda: self._show(None))
        self.remove_button = QPushButton("Remove", self)
        self.remove_button.clicked.connect(self._remove)
        buttons.addWidget(self.new_button)
        buttons.addWidget(self.remove_button)
        left.addLayout(buttons)
        root.addLayout(left)

        self._right = QVBoxLayout()
        self.said = QLabel(self)
        self.said.setWordWrap(True)
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self._save)
        foot = QHBoxLayout()
        foot.addWidget(self.said, 1)
        foot.addWidget(self.save_button)
        self._right.addStretch(1)
        self._right.addLayout(foot)
        root.addLayout(self._right, 1)
        self.reload()

    def _kept(self) -> dict:
        return getattr(self._workspace.settings_manager.settings, self._table)

    def showEvent(self, event) -> None:  # the other page may have changed what this one lists
        self.reload()
        super().showEvent(event)

    def reload(self, select: str | None = None) -> None:
        select = select or (self.names.currentItem() and self.names.currentItem().text())
        names = list(self._kept())
        self.names.blockSignals(True)
        self.names.clear()
        self.names.addItems(names)
        self.names.setCurrentRow(names.index(select) if select in names else 0)
        self.names.blockSignals(False)
        self._show(self.names.currentItem().text())

    def _show(self, name: str | None) -> None:
        """The form of the entry kept as `name`, or of one that has no name yet."""
        if self._body is not None:
            self._body.setParent(None)
            self._body.deleteLater()
        if name is None:
            self.names.setCurrentRow(-1)
        entry = self._kept()[name] if name else self._model.model_construct()
        self._body = body = QWidget(self)
        self._form = form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        self.name = QLineEdit(name or "", body)
        self.name.setReadOnly(bool(name))
        self.name.setPlaceholderText("letters, digits, _ and -")
        form.addRow("Name", self.name)
        hosts = self._workspace.settings_manager.settings.hosts
        self._editors = {}
        for key, field in self._model.model_fields.items():
            editor = self._editors[key] = _editor(field, getattr(entry, key, None), body, hosts)
            editor.setToolTip(field.description or "")
            form.addRow(field.title or key.replace("_", " ").capitalize(), editor)
        kind = self._editors.get("kind")
        if name == "local":  # this machine and its pool: what they are is not a choice
            for fixed in ("address", "kind", "hosts"):
                if fixed in self._editors:
                    self._editors[fixed].setEnabled(False)
        elif kind is not None:
            kind.removeItem(kind.findData("loky"))
        if kind is not None:
            kind.currentIndexChanged.connect(self._only_of_kind)
            self._only_of_kind()
        self.remove_button.setEnabled(bool(name) and name != "local")
        self.said.setText("")
        self._right.insertWidget(0, body)

    def _only_of_kind(self) -> None:
        kind = self._editors["kind"].currentData()
        for key, field in self._model.model_fields.items():
            only = (field.json_schema_extra or {}).get("kind")
            self._form.setRowVisible(self._editors[key], only in (None, kind))

    def _save(self) -> None:
        name = self.name.text().strip()
        if not self.name.isReadOnly() and name in self._kept():
            self.said.setText(f"`{name}` is kept already.")
            return
        fields = {key: _value(editor) for key, editor in self._editors.items() if not editor.isHidden()}
        try:
            getattr(self._workspace, f"save_{self._one}")(name, **fields)
        except (ValueError, RuntimeError) as error:
            self.said.setText(str(error))
            return
        self.reload(select=name)
        self.said.setText(f"`{name}` is kept.")
        self.changed.emit()

    def _remove(self) -> None:
        name = self.name.text().strip()
        asked = QMessageBox.question(self, "Remove", f"Remove `{name}` from the {self._table} kept?")
        if asked != QMessageBox.StandardButton.Yes:
            return
        try:
            getattr(self._workspace, f"remove_{self._one}")(name)
        except (ValueError, RuntimeError) as error:
            self.said.setText(str(error))
            return
        self.reload()
        self.changed.emit()


class ExecutorsPanel(QDialog):
    """Who runs jobs now: a row for each executor kept, started and stopped from here.

    Starting one waits for its machines, so it is done in a thread, and what is done on a
    machine that is being prepared is shown line by line. The round mark is the executor a job
    goes to when nobody is named.
    """

    line, ended = Signal(str), Signal(str, str)
    settings_requested = Signal()
    _STATES = {"on": "On", "off": "Off", "starting": "Starting…", "blocked": "Blocked"}

    def __init__(self, workspace, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Executors")
        self.setModal(False)
        self.resize(640, 260)
        self._workspace = workspace
        self._busy: set[str] = set()  # the ones a thread of this panel is starting or stopping
        self._shown: Any = None
        self._body: QWidget | None = None
        self.buttons: dict[str, QPushButton] = {}
        self.states: dict[str, QLabel] = {}
        self.defaults: dict[str, QRadioButton] = {}

        self._layout = QVBoxLayout(self)
        self.said = QPlainTextEdit(self)
        self.said.setReadOnly(True)
        self.said.setVisible(False)
        self._layout.addWidget(self.said, 1)
        self._layout.addStretch(0)  # takes the room left only while nothing is said
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.settings_button = QPushButton("Hosts and executors…", self)
        self.settings_button.setToolTip("They are made and changed in Settings.")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        foot.addWidget(self.settings_button)
        self._layout.addLayout(foot)

        self.line.connect(self._say)
        self.ended.connect(self._ended)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def showEvent(self, event) -> None:
        self.refresh()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def refresh(self) -> None:
        rows = self._workspace.executors()
        if (rows, self._busy) == self._shown:
            return
        self._shown = (rows, set(self._busy))
        if self._body is not None:
            self._body.setParent(None)
            self._body.deleteLater()
        self._body = body = QWidget(self)
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(4, 1)
        for column, title in enumerate(("Default", "Name", "Kind", "Hosts", "State")):
            grid.addWidget(QLabel(f"<b>{title}</b>", body), 0, column)
        for at, row in enumerate(rows, start=1):
            name, state, busy = row["name"], row["state"], row["name"] in self._busy
            default = self.defaults[name] = QRadioButton(body)
            default.setChecked(row["default"])
            default.setToolTip("A job that names nobody goes to this one.")
            default.clicked.connect(lambda _checked, name=name: self._default(name))
            grid.addWidget(default, at, 0)
            grid.addWidget(QLabel(name, body), at, 1)
            grid.addWidget(QLabel(row["kind"], body), at, 2)
            grid.addWidget(QLabel(", ".join(row["hosts"]), body), at, 3)
            said = self.states[name] = QLabel(
                "Stopping…" if busy and state == "on" else self._STATES[state] + (f": {row['why']}" if row["why"] else ""),
                body)
            said.setWordWrap(True)
            grid.addWidget(said, at, 4)
            button = self.buttons[name] = QPushButton("Deactivate" if state == "on" else "Activate", body)
            button.setEnabled(state in ("on", "off") and not busy)
            button.setToolTip(row["why"])
            button.clicked.connect(lambda _checked, name=name, stop=state == "on": self._do(name, stop))
            grid.addWidget(button, at, 5)
        self._layout.insertWidget(0, body)

    def _default(self, name: str) -> None:
        self._workspace.settings_manager.set_default_executor(name)
        self.refresh()

    def _do(self, name: str, stop: bool) -> None:
        def work() -> None:
            try:
                self._workspace.deactivate(name) if stop else self._workspace.activate(name, self.line.emit)
            except Exception as error:  # noqa: BLE001 - said in the panel, where it was asked for
                self.ended.emit(name, str(error))
            else:
                self.ended.emit(name, "")

        self._busy.add(name)
        self.refresh()
        threading.Thread(target=work, name=f"executor-{name}", daemon=True).start()

    def _say(self, text: str) -> None:
        self.said.setVisible(True)
        self.said.appendPlainText(text)

    def _ended(self, name: str, error: str) -> None:
        self._busy.discard(name)
        if error:
            self._say(f"{name}: {error}")
        self.refresh()


__all__ = ["ExecutorsPanel", "KeptPage"]
