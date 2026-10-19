"""A split button is an action button: the theme frames it and gives its arrow a segment."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QToolButton

from ms_components.theme import base_qss


def test_a_split_button_is_wider_than_a_plain_tool_button_with_the_same_text():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(base_qss())
    plain, split = QToolButton(), QToolButton()
    for button in (plain, split):
        button.setText("Run Docking")
    split.setPopupMode(QToolButton.MenuButtonPopup)
    split.ensurePolished()
    plain.ensurePolished()

    assert split.sizeHint().width() > plain.sizeHint().width() + 20  # padding + arrow segment
    app.setStyleSheet("")
