"""The step dialog shows the steps and how each ended; the output waits behind a button."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from ms_env import Step, StepFailed

from ms_components.step_dialog import StepRunnerDialog


def _fail() -> str:
    raise StepFailed("no network")


def _run(steps):
    app = QApplication.instance() or QApplication([])  # noqa: F841  (kept alive for the dialog)
    dialog = StepRunnerDialog("Install", steps)
    dialog.show()
    loop = QEventLoop()
    dialog.finished_ok.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    dialog.start()
    loop.exec()
    return dialog, [dialog._list.item(row).text() for row in range(dialog._list.count())]


def test_the_steps_are_ticked_and_the_output_stays_out_of_the_way():
    dialog, rows = _run([Step("download", call=lambda: "fetched"), Step("verify", call=lambda: "ok")])

    assert rows == ["✓  Download", "✓  Verify"]
    assert not dialog._log.isVisible() and dialog._log.toPlainText() == "fetched\nok"


def test_a_failed_step_is_marked_and_opens_the_output():
    dialog, rows = _run([Step("download", call=_fail), Step("verify", call=lambda: "ok")])

    assert rows == ["✗  Download", "○  Verify"]
    assert dialog._log.isVisible() and "no network" in dialog._log.toPlainText()
