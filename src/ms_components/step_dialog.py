"""Runs a list of provisioning ``Step``s off the GUI thread and shows the output.

Used for anything that touches a remote host or boots a cluster: testing an
executor, preparing its environment, ``ray up``. Modality is the caller's call —
``blocking=True`` for the compute backend the app is about to depend on,
non-modal for everything else so HPC/cluster setup can run in the background.
"""
from __future__ import annotations

from typing import Callable, Iterable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ms_flow.core.executor.provisioning import Step, run_step


class StepWorker(QThread):
    line = Signal(str)
    step_started = Signal(int, str)
    completed = Signal(bool, str)

    def __init__(self, steps: list[Step], parent=None):
        super().__init__(parent)
        self._steps = list(steps)

    def run(self) -> None:  # QThread entry point
        for index, step in enumerate(self._steps):
            self.step_started.emit(index, step.name)
            try:
                run_step(step, self.line.emit)
            except Exception as exc:  # noqa: BLE001 - any failure ends the sequence
                self.line.emit(f"! {exc}")
                self.completed.emit(False, str(exc))
                return
        self.completed.emit(True, "")


class StepRunnerDialog(QDialog):
    finished_ok = Signal(bool)

    def __init__(
        self,
        title: str,
        steps: Iterable[Step],
        *,
        blocking: bool = False,
        parent: QWidget | None = None,
        on_success: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self._steps = list(steps)
        self._on_success = on_success
        self.setWindowTitle(title)
        self.setModal(blocking)
        self.resize(720, 420)

        layout = QVBoxLayout(self)
        self._status = QLabel("Starting…", self)
        self._progress = QProgressBar(self)
        self._progress.setRange(0, max(1, len(self._steps)))
        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        self._buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        self._buttons.rejected.connect(self.reject)
        # No cancel: killing a half-finished `ray up`/conda create leaves worse
        # state than letting it end. Close is enabled once the run is over.
        self._buttons.button(QDialogButtonBox.Close).setEnabled(False)
        layout.addWidget(self._status)
        layout.addWidget(self._progress)
        layout.addWidget(self._log, 1)
        layout.addWidget(self._buttons)

        self._worker = StepWorker(self._steps, self)
        self._worker.line.connect(self._log.appendPlainText)
        self._worker.step_started.connect(self._on_step_started)
        self._worker.completed.connect(self._on_completed)

    def start(self) -> None:
        if not self._steps:
            self._status.setText("Nothing to do.")
            self._progress.setValue(self._progress.maximum())
            self._buttons.button(QDialogButtonBox.Close).setEnabled(True)
            self.finished_ok.emit(True)
            return
        self._worker.start()

    def _on_step_started(self, index: int, name: str) -> None:
        self._status.setText(f"[{index + 1}/{len(self._steps)}] {name}")
        self._progress.setValue(index)

    def _on_completed(self, ok: bool, error: str) -> None:
        self._progress.setValue(self._progress.maximum())
        self._status.setText("Done." if ok else f"Failed: {error}")
        self._buttons.button(QDialogButtonBox.Close).setEnabled(True)
        if ok and self._on_success is not None:
            self._on_success()
        self.finished_ok.emit(ok)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._worker.isRunning():
            self._worker.wait(50)
        super().closeEvent(event)


def run_steps_dialog(
    parent: QWidget | None,
    title: str,
    steps: Iterable[Step],
    *,
    blocking: bool = False,
    on_success: Callable[[], None] | None = None,
) -> StepRunnerDialog:
    """Show the dialog and start the run. Blocking calls exec(), the rest show()."""
    dialog = StepRunnerDialog(title, steps, blocking=blocking, parent=parent, on_success=on_success)
    if blocking:
        dialog.show()
        dialog.start()
        dialog.exec()
    else:
        dialog.show()
        dialog.start()
    return dialog


__all__ = ["StepRunnerDialog", "StepWorker", "run_steps_dialog"]
