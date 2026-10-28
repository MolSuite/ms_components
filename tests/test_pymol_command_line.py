import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ms_components.ms_pymol.command_line import PymolCommandLine


def test_command_entry_completion_history_and_editing():
    app = QApplication.instance() or QApplication([])
    commands = []
    cmd = SimpleNamespace(do=commands.append,
                          _parser=SimpleNamespace(complete=lambda text: "color yellow" if text == "color ye" else None))
    bar = PymolCommandLine(cmd)
    bar.show()
    bar.input.setFocus()
    QTest.keyClicks(bar.input, "color ye")
    QTest.keyClick(bar.input, Qt.Key_Tab)
    assert bar.input.text() == "color yellow"
    QTest.keyClick(bar.input, Qt.Key_Return)
    assert commands == ["color yellow"]
    assert bar.input.text() == ""
    QTest.keyClicks(bar.input, "unfinished")
    QTest.keyClick(bar.input, Qt.Key_Up)
    assert bar.input.text() == "color yellow"
    QTest.keyClick(bar.input, Qt.Key_Down)
    assert bar.input.text() == "unfinished"
    bar.close()
    app.processEvents()


def test_failed_command_keeps_input_available():
    app = QApplication.instance() or QApplication([])
    def fail(_):
        raise ValueError("Cannot run command")
    bar = PymolCommandLine(SimpleNamespace(do=fail))
    bar.show()
    bar.input.setText("bad command")
    bar.execute()
    assert bar.input.text() == "bad command"
    assert bar.error_label.isVisible()
    assert bar.error_label.toolTip() == "Cannot run command"
    bar.close()
    app.processEvents()
