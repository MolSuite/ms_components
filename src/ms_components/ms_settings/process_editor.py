"""Editor for ``resources.process``: who runs the jobs, and the fields of that choice.

It is one choice out of a few, so not a list of rows: only the fields of what is chosen are
shown. Saving puts it in place through ``apply`` (``Workspace.run_process_on``), which also
gives the other machines what they need: that is waited for in a dialog, off the GUI thread.
"""
from __future__ import annotations

import threading
import types
from typing import Any, Callable, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

_KINDS = {
    "process": ("This computer", "Jobs run in the processes of this computer."),
    "ray": ("This computer and others (Ray)",
            "Name the other machines as ssh reaches them, one per line. Each has to take your ssh key "
            "without asking for a password. What they need to run the jobs is installed there on saving."),
    "queue": ("The queue of another machine",
              "Name the login node as ssh reaches it. It has to take your ssh key without asking for a "
              "password. What it needs to run the jobs is installed there on saving."),
}


def _editor(annotation: Any, value: Any, parent: QWidget) -> QWidget:
    options = get_args(annotation)
    if get_origin(annotation) in (Union, types.UnionType) and options == (bool, type(None)):
        editor = QComboBox(parent)
        for text, data in (("Automatic", None), ("Yes", True), ("No", False)):
            editor.addItem(text, data)
    elif get_origin(annotation) is Literal:
        editor = QComboBox(parent)
        for option in options:
            editor.addItem(str(option), option)
    elif get_origin(annotation) is list:
        editor = QPlainTextEdit("\n".join(value), parent)
        editor.setPlaceholderText("one per line")
        editor.setMaximumHeight(90)
        return editor
    elif annotation is bool:
        editor = QCheckBox(parent)
        editor.setChecked(value)
        return editor
    elif annotation in (int, float):
        editor = QSpinBox(parent) if annotation is int else QDoubleSpinBox(parent)
        editor.setRange(0, 1_000_000_000)
        editor.setValue(value)
        return editor
    else:
        return QLineEdit(str(value), parent)
    editor.setCurrentIndex(editor.findData(value))
    return editor


def _value(editor: QWidget) -> Any:
    if isinstance(editor, QComboBox):
        return editor.currentData()
    if isinstance(editor, QCheckBox):
        return editor.isChecked()
    if isinstance(editor, (QSpinBox, QDoubleSpinBox)):
        return editor.value()
    if isinstance(editor, QPlainTextEdit):
        return [line.strip() for line in editor.toPlainText().splitlines() if line.strip()]
    return editor.text().strip()


class _Waiting(QDialog):
    """Runs ``work(on_line)`` in a thread and stays open, showing its lines, until it ends."""

    line, ended = Signal(str), Signal(object)

    def __init__(self, parent: QWidget, work: Callable[[Callable[[str], None]], None]):
        super().__init__(parent)
        self.setWindowTitle("Preparing where jobs run")
        self.resize(680, 380)
        self.error: BaseException | None = None
        layout = QVBoxLayout(self)
        note = QLabel("Reaching the other machines and giving them what the jobs need. "
                      "The first time takes minutes.", self)
        note.setWordWrap(True)
        layout.addWidget(note)
        bar = QProgressBar(self)
        bar.setRange(0, 0)
        layout.addWidget(bar)
        said = QPlainTextEdit(self)
        said.setReadOnly(True)
        layout.addWidget(said, 1)
        self.line.connect(said.appendPlainText)
        self.ended.connect(self._end)
        threading.Thread(target=self._run, args=(work,), name="where-jobs-run", daemon=True).start()

    def _run(self, work) -> None:
        try:
            work(self.line.emit)
        except BaseException as error:  # noqa: BLE001 - raised again by whoever opened this
            self.ended.emit(error)
        else:
            self.ended.emit(None)

    def _end(self, error) -> None:
        self.error = error
        self.done(0)

    def reject(self) -> None:
        # ponytail: no way out while it runs: what is being installed there goes on anyway.
        pass


class ProcessRoleEditor(QWidget):
    """Edits stay here until :meth:`commit`, which the panel's "Save changes" calls."""

    def __init__(self, *, configuration, apply: Callable[..., None], path: str = "resources.process",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._configuration, self._apply, self._path = configuration, apply, path
        self._body: QWidget | None = None
        self._dirty = False
        QVBoxLayout(self).setContentsMargins(0, 0, 0, 0)
        self.reload()

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def reload(self) -> None:
        if self._body is not None:
            self._body.setParent(None)
            self._body.deleteLater()
        role = self._configuration.get_global_value(self._path)
        self._body = body = QWidget(self)
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        self.kind, pages, hint = QComboBox(body), [], QLabel(body)
        hint.setWordWrap(True)
        self.editors: dict[str, dict[str, QWidget]] = {}
        for kind in get_args(type(role).model_fields["kind"].annotation):
            title, _ = _KINDS.get(kind, (kind, ""))
            self.kind.addItem(title, kind)
            section = role if kind == "process" else getattr(role, kind)
            page = QWidget(body)
            fields, self.editors[kind] = QFormLayout(page), {}
            fields.setContentsMargins(0, 0, 0, 0)
            for name, field in type(section).model_fields.items():
                if name == "kind" or isinstance(getattr(section, name), BaseModel):
                    continue
                editor = self.editors[kind][name] = _editor(field.annotation, getattr(section, name), page)
                editor.setToolTip(field.description or "")
                self._watch(editor)
                fields.addRow(name.replace("_", " ").capitalize(), editor)
            pages.append(page)

        def show(index: int) -> None:  # only the fields of what is chosen take room
            hint.setText(_KINDS.get(self.kind.itemData(index), ("", ""))[1])
            for at, page in enumerate(pages):
                page.setVisible(at == index)

        self.kind.setCurrentIndex(self.kind.findData(role.kind))
        self.kind.currentIndexChanged.connect(show)
        self._watch(self.kind)
        form.addRow("Run jobs on", self.kind)
        form.addRow(hint)
        for page in pages:
            form.addRow(page)
        show(self.kind.currentIndex())
        self.layout().addWidget(body)
        self._dirty = False

    def _watch(self, editor: QWidget) -> None:
        changed = (getattr(editor, "currentIndexChanged", None) or getattr(editor, "toggled", None)
                   or getattr(editor, "valueChanged", None) or editor.textChanged)
        changed.connect(self._changed)

    def _changed(self, *_) -> None:
        self._dirty = True

    def commit(self, *, target: str = "global") -> None:
        """Save the choice and put it in place. Raises what ``apply`` raised, with nothing changed.

        ponytail: always for the user, whatever ``target`` says: a project does not say where
        the jobs of this computer run.
        """
        kind = self.kind.currentData()
        fields = {name: _value(editor) for name, editor in self.editors[kind].items()}
        if kind == "process":
            self._apply(kind, **fields)
        else:
            waiting = _Waiting(self, lambda on_line: self._apply(kind, on_line=on_line, **fields))
            waiting.exec()
            if waiting.error is not None:
                raise waiting.error
        self._dirty = False


__all__ = ["ProcessRoleEditor"]
