from __future__ import annotations

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from ms_components.ms_dockwidget.widget import (
    Behavior,
    DockManager,
    MSDockWidget,
    Region,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(["molsuite-dock-window-test"])


def _add_dock(
    manager: DockManager,
    window: QMainWindow,
    dock_id: str,
    *,
    visible: bool,
) -> MSDockWidget:
    dock = MSDockWidget(dock_id.title(), manager, window)
    dock.setWidget(QWidget())
    manager.add_dock(
        dock,
        dock_id=dock_id,
        region=Region.RIGHT_TOP,
        order=len(manager.docks),
        behavior=Behavior.EXCLUSIVE,
        starts_visible=visible,
    )
    return dock


def test_detached_dock_is_normal_independent_window(app):
    window = QMainWindow()
    manager = DockManager(window)
    first = _add_dock(manager, window, "first", visible=True)
    second = _add_dock(manager, window, "second", visible=False)
    manager.build()
    window.show()
    app.processEvents()

    manager.open_in_window("first")
    app.processEvents()
    app.processEvents()

    assert first.isFloating()
    assert first.isVisible()
    assert first.parent() is None
    assert first.titleBarWidget() is first._title_bar
    assert first.windowFlags() & Qt.WindowType.CustomizeWindowHint
    assert (
        first.windowFlags() & Qt.WindowType.WindowType_Mask
    ) == Qt.WindowType.Window
    assert manager.buttons["first"].isChecked()

    manager.toggle("second", True)
    app.processEvents()

    assert first.isVisible()
    assert second.isVisible()
    assert manager.buttons["first"].isChecked()
    assert manager.buttons["second"].isChecked()

    manager.dock_to_main_window("first")
    app.processEvents()

    assert not first.isFloating()
    assert first.isVisible()
    assert first.parent() is window
    assert first.titleBarWidget() is first._title_bar
    assert not second.isVisible()
    assert manager.buttons["first"].isChecked()

    window.close()
    app.processEvents()


def test_hidden_windowed_dock_reopens_as_window(app):
    window = QMainWindow()
    manager = DockManager(window)
    dock = _add_dock(manager, window, "tool", visible=True)
    manager.build()
    window.show()
    app.processEvents()

    manager.open_in_window("tool")
    app.processEvents()
    manager.toggle("tool", False)
    app.processEvents()

    assert dock.isFloating()
    assert not dock.isVisible()
    assert not manager.buttons["tool"].isChecked()

    manager.toggle("tool", True)
    app.processEvents()

    assert dock.isFloating()
    assert dock.isVisible()
    assert (
        dock.windowFlags() & Qt.WindowType.WindowType_Mask
    ) == Qt.WindowType.Window

    window.close()
    app.processEvents()


def test_dock_title_actions_keep_a_visible_icon_area(app):
    window = QMainWindow()
    manager = DockManager(window)
    dock = _add_dock(manager, window, "controls", visible=True)

    assert dock._title_bar.options_button.size() == QSize(24, 24)
    assert dock._title_bar.close_button.size() == QSize(24, 24)
    assert dock._title_bar.close_button.iconSize() == QSize(16, 16)
    assert "padding: 0" in dock._title_bar.options_button.styleSheet()
    assert "padding: 0" in dock._title_bar.close_button.styleSheet()
    window.close()


def test_title_double_click_and_drop_over_main_window_redock(app):
    window = QMainWindow()
    window.resize(600, 400)
    manager = DockManager(window)
    dock = _add_dock(manager, window, "movable", visible=True)
    manager.build()
    window.show()
    app.processEvents()

    manager.open_in_window("movable")
    app.processEvents()
    QTest.mouseDClick(dock._title_bar, Qt.MouseButton.LeftButton)
    app.processEvents()

    assert not manager.is_windowed("movable")
    assert dock.parent() is window

    outside = window.mapToGlobal(window.rect().bottomRight()) + dock.pos()
    manager.begin_native_window_drag("movable", outside, dock._title_bar.pos())
    app.processEvents()

    assert manager.is_windowed("movable")
    assert dock.parent() is None

    manager.finish_native_window_drag(
        window.mapToGlobal(window.rect().center())
    )
    app.processEvents()

    assert not manager.is_windowed("movable")
    assert dock.parent() is window

    window.close()
    app.processEvents()
