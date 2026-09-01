from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from ms_components.wheel import install_shift_hscroll, uninstall_shift_hscroll


def _wheel(modifier):
    return QWheelEvent(QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, -120),
                       Qt.MouseButton.NoButton, modifier, Qt.ScrollPhase.NoScrollPhase, False)


def test_shift_wheel_scrolls_horizontally_and_plain_wheel_still_vertical():
    app = QApplication.instance() or QApplication(["shift-hscroll-test"])
    install_shift_hscroll(app)

    table = QTableWidget(30, 20)
    for row in range(30):
        for col in range(20):
            table.setItem(row, col, QTableWidgetItem(f"{row}-{col}"))
    table.resize(400, 300)
    table.show()
    app.processEvents()
    hbar, vbar = table.horizontalScrollBar(), table.verticalScrollBar()
    assert hbar.maximum() > 0 and vbar.maximum() > 0

    QApplication.sendEvent(table.viewport(), _wheel(Qt.KeyboardModifier.ShiftModifier))
    assert hbar.value() > 0 and vbar.value() == 0

    hbar.setValue(0)
    QApplication.sendEvent(table.viewport(), _wheel(Qt.KeyboardModifier.NoModifier))
    assert vbar.value() > 0 and hbar.value() == 0


def test_shift_hscroll_filter_can_be_removed_before_app_shutdown():
    app = QApplication.instance() or QApplication(["shift-hscroll-test"])
    install_shift_hscroll(app)

    assert app._shift_hscroll_filter is not None

    uninstall_shift_hscroll(app)

    assert app._shift_hscroll_filter is None
