"""Editable PyMOL command entry with PyMOL's own tab completion."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QToolButton, QVBoxLayout, QWidget


class _CommandEdit(QLineEdit):
    complete_requested = Signal()
    previous_requested = Signal()
    next_requested = Signal()

    def event(self, event):
        # QWidget normally consumes Tab for focus traversal before keyPressEvent.
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Tab:
            self.complete_requested.emit()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Up:
            self.previous_requested.emit()
        elif event.key() == Qt.Key.Key_Down:
            self.next_requested.emit()
        else:
            super().keyPressEvent(event)
            return
        event.accept()


class PymolCommandLine(QWidget):
    command_failed = Signal(str)

    def __init__(self, cmd, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self._history = []
        self._history_index = 0
        self._draft = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(3)
        self.output = QPlainTextEdit(self)
        self.output.setObjectName("pymolCommandOutput")
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self.output.setFixedHeight(120)
        self.output.hide()
        layout.addWidget(self.output)
        row = QHBoxLayout()
        row.setSpacing(6)
        layout.addLayout(row)
        row.addWidget(QLabel("PyMOL>"))
        self.input = _CommandEdit(self)
        self.input.setObjectName("pymolCommandLine")
        self.input.setAccessibleName("PyMOL command line")
        self.input.setPlaceholderText("Enter a PyMOL command · Tab to complete")
        self.input.setToolTip("Enter runs a command; Tab completes it; Up and Down browse history.")
        self.input.setEnabled(cmd is not None)
        row.addWidget(self.input, 1)
        self.error_label = QLabel(self)
        self.error_label.setObjectName("pymolCommandError")
        self.error_label.setToolTip("The command could not be executed or completed.")
        self.error_label.hide()
        row.addWidget(self.error_label)
        self.output_button = QToolButton(self)
        self.output_button.setText("Output")
        self.output_button.setCheckable(True)
        self.output_button.setToolTip("Show PyMOL command output")
        self.output_button.toggled.connect(self.output.setVisible)
        row.addWidget(self.output_button)
        self.command_failed.connect(self._show_error)
        self.input.returnPressed.connect(self.execute)
        self.input.complete_requested.connect(self.complete)
        self.input.previous_requested.connect(lambda: self.navigate_history(-1))
        self.input.next_requested.connect(lambda: self.navigate_history(1))
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setInterval(500)
        self._feedback_timer.timeout.connect(self._read_feedback)
        if callable(getattr(cmd, "_get_feedback", None)):
            self._feedback_timer.start()

    def execute(self):
        text = self.input.text().strip()
        if not text or self.cmd is None:
            return
        self.error_label.hide()
        try:
            self.cmd.do(text)
        except Exception as exc:
            self.command_failed.emit(str(exc))
            return
        if not self._history or self._history[-1] != text:
            self._history.append(text)
            self._history = self._history[-255:]
        self._history_index = len(self._history)
        self._draft = ""
        self.input.clear()

    def complete(self):
        if self.cmd is None:
            return
        self.error_label.hide()
        try:
            completed = self.cmd._parser.complete(self.input.text())
        except Exception as exc:
            self.command_failed.emit(str(exc))
            return
        if completed:
            self.input.setText(completed)
            self.input.setCursorPosition(len(completed))

    def navigate_history(self, direction):
        if not self._history:
            return
        if self._history_index == len(self._history):
            self._draft = self.input.text()
        self._history_index = max(0, min(len(self._history), self._history_index + direction))
        value = self._draft if self._history_index == len(self._history) else self._history[self._history_index]
        self.input.setText(value)
        self.input.setCursorPosition(len(value))

    def _show_error(self, message):
        self.error_label.setText("Error")
        self.error_label.setToolTip(message)
        self.error_label.show()
        self.output.appendPlainText(message)
        self.output_button.setChecked(True)

    def _read_feedback(self):
        try:
            feedback = self.cmd._get_feedback()
        except Exception:
            return
        if feedback:
            self.output.appendPlainText("\n".join(feedback))
