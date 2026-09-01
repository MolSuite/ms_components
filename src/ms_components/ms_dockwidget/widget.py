import faulthandler
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QSize, QMimeData, QPoint, QByteArray, QObject, QEvent, QTimer, QtMsgType, \
    qInstallMessageHandler
from PySide6.QtGui import QAction, QCursor, QDrag, QIcon
from PySide6.QtWidgets import (QDockWidget, QFrame, QMainWindow, QMenu, QSizePolicy, QToolBar, QToolButton, QVBoxLayout,
                               QHBoxLayout, QLabel, QStyle,
                               QApplication, QWidget)

from .resources.icons import icon as load_icon

faulthandler.enable(all_threads=True)

def qt_message_handler(mode, context, message):
    if mode == QtMsgType.QtInfoMsg:
        mode_str = "INFO"
    elif mode == QtMsgType.QtWarningMsg:
        mode_str = "WARNING"
    elif mode == QtMsgType.QtCriticalMsg:
        mode_str = "CRITICAL"
    elif mode == QtMsgType.QtFatalMsg:
        mode_str = "FATAL"
    else:
        mode_str = "DEBUG"
    print(f"[{mode_str}] {context.file}:{context.line} - {message}")


# Install the interceptor before creating the QApplication
qInstallMessageHandler(qt_message_handler)

DOCK_BUTTON_MIME_TYPE = "application/x-dock-id"
DOCK_BUTTON_DRAG_THRESHOLD = 6
TOOLBAR_COLLAPSED_WIDTH = 32
TOOLBAR_EXPANDED_WIDTH = 64
DEFAULT_TOOL_ICON = load_icon("folder.svg")
MENU_STYLE_SHEET = (
    "QMenu { background: palette(window); color: palette(text); border: 1px solid palette(mid); }"
    "QMenu::item:selected { background: palette(highlight); color: palette(highlighted-text); }"
    "QMenu::separator { height: 1px; background: palette(mid); margin: 3px 0; }"
)


# ══════════════════════════════════════════════════════════════════
# Region
# ══════════════════════════════════════════════════════════════════

class Region(Enum):
    LEFT_TOP = auto()
    LEFT_BOTTOM = auto()
    BOTTOM_LEFT = auto()
    RIGHT_TOP = auto()
    RIGHT_BOTTOM = auto()
    BOTTOM_RIGHT = auto()

    def is_left(self) -> bool:
        return self in (Region.LEFT_TOP, Region.LEFT_BOTTOM, Region.BOTTOM_LEFT)

    def is_right(self) -> bool:
        return self in (Region.RIGHT_TOP, Region.RIGHT_BOTTOM, Region.BOTTOM_RIGHT)

    def is_bottom(self) -> bool:
        return self in (Region.BOTTOM_LEFT, Region.BOTTOM_RIGHT)

    def is_lateral(self) -> bool:
        return not self.is_bottom()

    def qt_area(self) -> Qt.DockWidgetArea:
        if self.is_bottom():
            return Qt.DockWidgetArea.BottomDockWidgetArea
        if self in (Region.LEFT_TOP, Region.LEFT_BOTTOM):
            return Qt.LeftDockWidgetArea
        return Qt.RightDockWidgetArea

    def toolbar_side(self) -> "ToolbarSide":
        return ToolbarSide.LEFT if self.is_left() else ToolbarSide.RIGHT

    def toolbar_section(self) -> "ToolbarSection":
        if self in (Region.LEFT_TOP, Region.RIGHT_TOP):
            return ToolbarSection.TOP
        if self in (Region.LEFT_BOTTOM, Region.RIGHT_BOTTOM):
            return ToolbarSection.MIDDLE
        return ToolbarSection.BOTTOM


class ToolbarSide(Enum):
    LEFT = auto()
    RIGHT = auto()


class ToolbarSection(Enum):
    TOP = auto()
    MIDDLE = auto()
    BOTTOM = auto()


# ══════════════════════════════════════════════════════════════════
# Behavior / BottomMode
# ══════════════════════════════════════════════════════════════════

class Behavior(Enum):
    EXCLUSIVE = auto()
    MIXED_TAB = auto()
    MIXED_EXCLUSIVE = auto()


class BottomMode(Enum):
    SHARE = auto()
    STACK = auto()





@dataclass
class RegionState:
    order: List[str]
    visible: List[str]


# ══════════════════════════════════════════════════════════════════
# TitleBarWidget
# ══════════════════════════════════════════════════════════════════

class TitleBarWidget(QWidget):
    _MENU_SS = MENU_STYLE_SHEET

    def __init__(self, dock: "MSDockWidget"):
        super().__init__(dock)
        self._dock = dock
        self._drag_start: QPoint | None = None
        self._system_move_started = False
        self._manual_move = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        self.title_label = QLabel(dock.windowTitle())
        self.title_label.setStyleSheet("color: palette(text); font-size: 11px;")
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.options_button = QToolButton()
        self.options_button.setText("⋯")
        self.options_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.options_button.setAutoRaise(True)
        self.options_button.setFixedSize(24, 24)
        self.options_button.setStyleSheet(
            "QToolButton { color: palette(text); border: none; padding: 0;"
            " font-size: 18px; font-weight: 600; }"
            "QToolButton:hover { color: palette(highlighted-text); background: palette(highlight); border-radius: 3px; }"
        )
        self.options_button.clicked.connect(self._show_menu)
        layout.addWidget(self.options_button)

        self.close_button = QToolButton()
        self.close_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DockWidgetCloseButton)
        )
        self.close_button.setAutoRaise(True)
        self.close_button.setFixedSize(24, 24)
        self.close_button.setIconSize(QSize(16, 16))
        self.close_button.setStyleSheet(
            "QToolButton { border: none; padding: 0; }"
            "QToolButton:hover { background: #C0392B; border-radius: 3px; }"
        )
        self.close_button.clicked.connect(dock.close)
        self.close_button.setVisible(
            bool(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetClosable)
        )
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self._system_move_started = False
            self._manual_move = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._drag_start is None
            or not (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            super().mouseMoveEvent(event)
            return
        if not self._system_move_started:
            distance = (event.position().toPoint() - self._drag_start).manhattanLength()
            if distance < QApplication.startDragDistance():
                event.accept()
                return
            self._system_move_started = True
            started = self._dock.begin_native_window_drag(
                event.globalPosition().toPoint(),
                self._drag_start,
            )
            self._manual_move = not started
        elif self._manual_move:
            self._dock.move(event.globalPosition().toPoint() - self._drag_start)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            if self._system_move_started:
                self._dock.finish_native_window_drag()
            self._drag_start = None
            self._system_move_started = False
            self._manual_move = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            manager = self._dock._manager
            dock_id = self._dock.objectName()
            if manager is not None and manager.is_windowed(dock_id):
                self._dock.dock_to_main_window()
            else:
                self._dock.open_in_window()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def update_title(self, title: str):
        self.title_label.setText(title)

    def _show_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(self._MENU_SS)

        custom = self._dock.get_custom_actions()
        if custom:
            for item in custom:
                if item is None:
                    menu.addSeparator()
                elif isinstance(item, QAction):
                    menu.addAction(item)
                elif isinstance(item, QMenu):
                    menu.addMenu(item)
            menu.addSeparator()

        window_act = QAction(
            "Dock to Main Window" if self._dock.isFloating() else "Open in Window",
            menu,
        )
        if self._dock.isFloating():
            window_act.triggered.connect(self._dock.dock_to_main_window)
        else:
            window_act.triggered.connect(self._dock.open_in_window)
        menu.addAction(window_act)
        menu.addSeparator()

        settings_act = QAction("Settings", menu)
        settings_act.triggered.connect(self._dock.open_settings)
        menu.addAction(settings_act)
        menu.addSeparator()

        move_menu = menu.addMenu("Move to")
        move_menu.setStyleSheet(self._MENU_SS)
        self._build_move_menu(move_menu)

        resize_menu = menu.addMenu("Resize")
        resize_menu.setStyleSheet(self._MENU_SS)
        self._build_resize_menu(resize_menu)

        menu.exec(self.options_button.mapToGlobal(
            self.options_button.rect().bottomLeft()
        ))

    def _build_move_menu(self, menu: QMenu):
        manager = self._dock._manager
        if manager is None:
            menu.addAction("(no manager)").setEnabled(False)
            return
        manager.populate_move_menu(menu, self._dock.objectName())

    def _build_resize_menu(self, menu: QMenu):
        mw = self._find_main_window()
        entries = [
            ("Stretch to Left", Qt.Orientation.Horizontal, True),
            ("Stretch to Right", Qt.Orientation.Horizontal, False),
            ("Stretch to Top", Qt.Orientation.Vertical, True),
            ("Stretch to Bottom", Qt.Orientation.Vertical, False),
        ]
        for label, orientation, stretch_max in entries:
            act = QAction(label, menu)
            if mw is None:
                act.setEnabled(False)
            else:
                act.triggered.connect(
                    lambda checked=False, o=orientation, s=stretch_max:
                    self._resize(o, s)
                )
            menu.addAction(act)

        menu.addSeparator()
        restore_act = QAction("Restore Size", menu)
        if mw is None:
            restore_act.setEnabled(False)
        else:
            restore_act.triggered.connect(self._restore_size)
        menu.addAction(restore_act)

    def _resize(self, orientation: Qt.Orientation, stretch_max: bool):
        mw = self._find_main_window()
        if mw is None:
            return
        size = (mw.width() if stretch_max else 1) if orientation == Qt.Orientation.Horizontal \
            else (mw.height() if stretch_max else 1)
        mw.resizeDocks([self._dock], [size], orientation)

    def _restore_size(self):
        mw = self._find_main_window()
        if mw is None:
            return
        hint = self._dock.sizeHint()
        mw.resizeDocks([self._dock], [hint.width()], Qt.Orientation.Horizontal)
        mw.resizeDocks([self._dock], [hint.height()], Qt.Orientation.Vertical)

    def _find_main_window(self) -> Optional[QMainWindow]:
        p = self._dock.parent()
        while p:
            if isinstance(p, QMainWindow):
                return p
            p = p.parent()
        return None


# ══════════════════════════════════════════════════════════════════
# MSDockWidget
# ══════════════════════════════════════════════════════════════════

class MSDockWidget(QDockWidget):
    def __init__(self, title: str, manager: "DockManager", parent=None):
        super().__init__(title, parent)
        self._manager = manager
        self._title_bar = TitleBarWidget(self)
        self.setTitleBarWidget(self._title_bar)

    def setWindowTitle(self, title: str):
        super().setWindowTitle(title)
        if hasattr(self, "_title_bar"):
            self._title_bar.update_title(title)

    def get_custom_actions(self) -> list:
        return []

    def open_in_window(self) -> None:
        """Show this dock as a normal OS-managed top-level window."""
        if self._manager is None:
            self._promote_floating_window()
            return
        self._manager.open_in_window(self.objectName())

    def dock_to_main_window(self) -> None:
        """Return this top-level window to its configured dock region."""
        if self._manager is None:
            self.setFloating(False)
            return
        self._manager.dock_to_main_window(self.objectName())

    def _promote_floating_window(self) -> None:
        """Make this dock an OS-managed window while retaining its dock frame."""
        flags = self.windowFlags()
        if (
            self.parent() is None
            and self.titleBarWidget() is self._title_bar
            and (flags & Qt.WindowType.WindowType_Mask) == Qt.WindowType.Window
        ):
            return
        geometry = self.geometry()
        was_visible = self.isVisible()
        # Window|CustomizeWindowHint is the useful hybrid on X11/KWin: it is
        # published as a NORMAL non-transient window (so startSystemMove gets OS
        # snapping), while the existing dock title bar remains the only frame.
        # Calling setFloating(True) first would permanently mark it as a Qt/KDE
        # utility override and break this behavior.
        self.setTitleBarWidget(self._title_bar)
        self.setParent(
            None,
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint,
        )
        if geometry.isValid():
            self.setGeometry(geometry)
        if was_visible:
            self.show()
            self.raise_()

    def begin_native_window_drag(self, global_pos: QPoint, title_offset: QPoint) -> bool:
        if self._manager is None:
            return False
        return self._manager.begin_native_window_drag(
            self.objectName(),
            global_pos,
            title_offset,
        )

    def finish_native_window_drag(self) -> None:
        if self._manager is not None:
            self._manager.finish_native_window_drag()


    def open_settings(self):
        print(f"[{self.windowTitle()}] open_settings — override me")


# ══════════════════════════════════════════════════════════════════
# DockEntry
# ══════════════════════════════════════════════════════════════════

@dataclass
class DockEntry:
    id: str
    dock: "MSDockWidget"
    title: str
    region: Region
    order: int
    behavior: Behavior
    icon: Optional[QIcon] = None
    starts_visible: bool = False
    bottom_mode: BottomMode = BottomMode.SHARE

# ══════════════════════════════════════════════════════════════════
# Toolbar button helpers
# ══════════════════════════════════════════════════════════════════

def _is_dock_button(widget: Optional[QWidget]) -> bool:
    return isinstance(widget, QToolButton) and bool(widget.property("dock_id"))


def _create_toolbar_button(title: str, icon: Optional[QIcon] = None) -> QToolButton:
    button = QToolButton()
    effective_icon = icon if icon and not icon.isNull() else DEFAULT_TOOL_ICON
    button.setText(title)
    button.setToolTip(title)
    # Kept unwrapped so set_button_style can re-derive the label for each mode.
    button.setProperty("full_title", title)
    button.setCheckable(True)
    button.setCursor(Qt.PointingHandCursor)
    button.setAutoRaise(True)
    button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    button.setIcon(effective_icon)
    button.setIconSize(QSize(24, 24))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setStyleSheet(
        "QToolButton {"
        " color: palette(text);"
        " border: none;"
        " border-radius: 4px;"
        " padding: 0px;"
        " }"
        "QToolButton:hover { background: palette(alternate-base); color: palette(text); }"
        "QToolButton:checked { background: palette(highlight); color: palette(highlighted-text); }"
    )
    return button


class DockButtonDragFilter(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start: Dict[int, QPoint] = {}
        self._dragging: Dict[int, bool] = {}

    def register(self, button: QToolButton):
        button.installEventFilter(self)

    def eventFilter(self, watched, event):
        if not isinstance(watched, QToolButton):
            return super().eventFilter(watched, event)

        key = id(watched)
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            self._drag_start[key] = event.position().toPoint()
            self._dragging[key] = False
        elif event.type() == QEvent.Type.MouseMove:
            start = self._drag_start.get(key)
            if (
                    start is not None
                    and not self._dragging.get(key, False)
                    and (event.position().toPoint() - start).manhattanLength()
                    >= DOCK_BUTTON_DRAG_THRESHOLD
            ):
                self._dragging[key] = True
                watched.setDown(False)
                self._start_drag(watched)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._drag_start.pop(key, None)
            if self._dragging.pop(key, False):
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _start_drag(self, button: QToolButton):
        dock_id = button.property("dock_id")
        if not dock_id:
            return

        pixmap = button.grab()
        mime = QMimeData()
        mime.setData(DOCK_BUTTON_MIME_TYPE, QByteArray(str(dock_id).encode()))

        drag = QDrag(button)
        drag.setMimeData(mime)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        drag.exec(Qt.MoveAction)


# ══════════════════════════════════════════════════════════════════
# ToolbarSeparator
# ══════════════════════════════════════════════════════════════════

class ToolbarSeparator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setFrameShape(QFrame.HLine)
        self.setStyleSheet("background: palette(mid); margin: 2px 4px;")


# ══════════════════════════════════════════════════════════════════
# VerticalToolbar
# ══════════════════════════════════════════════════════════════════

class VerticalToolbar(QWidget):
    INDICATOR_H = 2

    def __init__(self, side: ToolbarSide,
                 manager_ref: "Optional[DockManager]" = None,
                 parent=None):
        super().__init__(parent)
        self.side = side
        self._manager = manager_ref
        self._indicator: Optional[QFrame] = None

        self.setFixedWidth(TOOLBAR_COLLAPSED_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setStyleSheet("background: palette(window);")
        self.setAcceptDrops(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(5)

        self._top_widget = QWidget()
        self._top_layout = QVBoxLayout(self._top_widget)
        self._top_layout.setContentsMargins(4, 0, 4, 0)
        self._top_layout.setSpacing(5)
        self._top_layout.setAlignment(Qt.AlignTop)

        self._separator = ToolbarSeparator()

        self._middle_widget = QWidget()
        self._middle_layout = QVBoxLayout(self._middle_widget)
        self._middle_layout.setContentsMargins(4, 4, 4, 0)
        self._middle_layout.setSpacing(5)
        self._middle_layout.setAlignment(Qt.AlignTop)

        self._bottom_widget = QWidget()
        self._bottom_layout = QVBoxLayout(self._bottom_widget)
        self._bottom_layout.setContentsMargins(4, 0, 4, 0)
        self._bottom_layout.setSpacing(5)
        self._bottom_layout.setAlignment(Qt.AlignBottom)

        outer.addWidget(self._top_widget)
        outer.addWidget(self._separator)
        outer.addWidget(self._middle_widget)
        outer.addStretch(1)
        outer.addWidget(self._bottom_widget)
        self._update_separator_visibility()
        self._install_context_menu_target(self)
        self._install_context_menu_target(self._top_widget)
        self._install_context_menu_target(self._middle_widget)
        self._install_context_menu_target(self._bottom_widget)
        self._install_context_menu_target(self._separator)

    def layout_for_section(self, section: ToolbarSection) -> QVBoxLayout:
        if section == ToolbarSection.TOP:
            return self._top_layout
        if section == ToolbarSection.MIDDLE:
            return self._middle_layout
        return self._bottom_layout

    def layout_for_region(self, region: Region) -> QVBoxLayout:
        return self.layout_for_section(region.toolbar_section())

    def add_button(self, region: Region, button: QToolButton):
        self.layout_for_region(region).addWidget(button)
        self._update_separator_visibility()

    def remove_button(self, region: Region, button: QToolButton):
        layout = self.layout_for_region(region)
        layout.removeWidget(button)
        button.setParent(None)
        self._update_separator_visibility()

    def insert_button_before(self, region: Region, button: QToolButton,
                             before_id: Optional[str]):
        layout = self.layout_for_region(region)
        if before_id is None:
            layout.addWidget(button)
            self._update_separator_visibility()
            return
        for i in range(layout.count()):
            w = layout.itemAt(i).widget() if layout.itemAt(i) else None
            if _is_dock_button(w) and w.property("dock_id") == before_id:
                layout.insertWidget(i, button)
                self._update_separator_visibility()
                return
        layout.addWidget(button)
        self._update_separator_visibility()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(DOCK_BUTTON_MIME_TYPE):
            event.acceptProposedAction()
            self._update_indicator(event.position().toPoint())
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(DOCK_BUTTON_MIME_TYPE):
            event.acceptProposedAction()
            self._update_indicator(event.position().toPoint())
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._remove_indicator()

    def dropEvent(self, event):
        self._remove_indicator()
        if not event.mimeData().hasFormat(DOCK_BUTTON_MIME_TYPE):
            event.ignore()
            return

        dock_id = event.mimeData().data(DOCK_BUTTON_MIME_TYPE).toStdString()
        drop_pos = event.position().toPoint()
        section = self._section_at(drop_pos)
        before_id = self._button_after_cursor(drop_pos, section)

        event.acceptProposedAction()
        if self._manager is not None:
            self._manager.drop_button(dock_id, self, section, before_id)

    def _update_indicator(self, pos: QPoint):
        section = self._section_at(pos)
        before_id = self._button_after_cursor(pos, section)
        insert_y = self._indicator_y(section, before_id)

        if self._indicator is None:
            self._indicator = QFrame(self)
            self._indicator.setFixedHeight(self.INDICATOR_H)
            self._indicator.setStyleSheet("background: palette(highlight);")
            self._indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._indicator.show()
            self._indicator.raise_()

        self._indicator.setGeometry(0, insert_y, self.width(), self.INDICATOR_H)

    def _remove_indicator(self):
        if self._indicator is not None:
            self._indicator.deleteLater()
            self._indicator = None

    def _indicator_y(self, section: ToolbarSection, before_id: Optional[str]) -> int:
        layout = self.layout_for_section(section)
        if before_id is None:
            buttons = list(self._iter_buttons(layout))
            if not buttons:
                return self._section_start_y(section)
            last_button = buttons[-1]
            return last_button.mapTo(self, QPoint(0, last_button.height())).y()
        for i in range(layout.count()):
            w = layout.itemAt(i).widget() if layout.itemAt(i) else None
            if _is_dock_button(w) and w.property("dock_id") == before_id:
                return w.mapTo(self, QPoint(0, 0)).y()
        return self._section_start_y(section)

    def _section_at(self, pos: QPoint) -> ToolbarSection:
        upper_split = (
                              self._section_end_y(ToolbarSection.TOP)
                              + self._section_start_y(ToolbarSection.MIDDLE)
                      ) // 2
        lower_split = (
                              self._section_end_y(ToolbarSection.MIDDLE)
                              + self._section_start_y(ToolbarSection.BOTTOM)
                      ) // 2
        if pos.y() < upper_split:
            return ToolbarSection.TOP
        if pos.y() < lower_split:
            return ToolbarSection.MIDDLE
        return ToolbarSection.BOTTOM

    def _section_start_y(self, section: ToolbarSection) -> int:
        buttons = list(self._iter_buttons(self.layout_for_section(section)))
        if buttons:
            return buttons[0].mapTo(self, QPoint(0, 0)).y()
        widget = self._widget_for_section(section)
        return widget.mapTo(self, QPoint(0, 0)).y()

    def _section_end_y(self, section: ToolbarSection) -> int:
        buttons = list(self._iter_buttons(self.layout_for_section(section)))
        if buttons:
            last_button = buttons[-1]
            return last_button.mapTo(self, QPoint(0, last_button.height())).y()
        return self._section_start_y(section)

    def _button_after_cursor(self, pos: QPoint,
                             section: ToolbarSection) -> Optional[str]:
        layout = self.layout_for_section(section)
        for w in self._iter_buttons(layout):
            btn_mid_y = w.mapTo(self, QPoint(0, w.height() // 2)).y()
            if pos.y() < btn_mid_y:
                return w.property("dock_id")
        return None

    def _widget_for_section(self, section: ToolbarSection) -> QWidget:
        if section == ToolbarSection.TOP:
            return self._top_widget
        if section == ToolbarSection.MIDDLE:
            return self._middle_widget
        return self._bottom_widget

    def _iter_buttons(self, layout: QVBoxLayout):
        for i in range(layout.count()):
            w = layout.itemAt(i).widget() if layout.itemAt(i) else None
            if _is_dock_button(w):
                yield w

    def _layout_has_buttons(self, layout: QVBoxLayout) -> bool:
        return any(True for _ in self._iter_buttons(layout))

    def _update_separator_visibility(self):
        self._separator.setVisible(
            self._layout_has_buttons(self._top_layout)
            and self._layout_has_buttons(self._middle_layout)
        )

    def set_show_tool_names(self, show: bool):
        self.setFixedWidth(
            TOOLBAR_EXPANDED_WIDTH if show else TOOLBAR_COLLAPSED_WIDTH
        )

    def _install_context_menu_target(self, widget: QWidget):
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda pos, target=widget: self._show_context_menu_for_target(target, pos)
        )

    def _show_context_menu_for_target(self, target: QWidget, pos: QPoint):
        global_pos = target.mapToGlobal(pos)
        local_pos = self.mapFromGlobal(global_pos)
        child = self.childAt(local_pos)
        if _is_dock_button(child):
            return
        if self._manager is not None:
            self._manager.show_toolbar_context_menu(global_pos)


# ══════════════════════════════════════════════════════════════════
# DockManager
# ══════════════════════════════════════════════════════════════════

class DockManager:
    def __init__(self, mw: QMainWindow):
        self.mw = mw
        self.entries: Dict[str, DockEntry] = {}
        self.docks: Dict[str, MSDockWidget] = {}
        self.buttons: Dict[str, QToolButton] = {}
        # Standalone action buttons (no dock): a click runs a callback instead of toggling a dock.
        # action_id -> {"region", "order", "button"}. Re-added on every _build_toolbars().
        self.action_buttons: Dict[str, dict] = {}
        self.region_states: Dict[Region, RegionState] = {
            region: RegionState(order=[], visible=[]) for region in Region
        }
        self._region_defaults: Dict[Region, tuple[Behavior, BottomMode]] = {}
        self._show_tool_names = False
        self._bottom_rebuild_pending = False
        self._lateral_rebuild_pending = False
        # When True the BOTTOM_* regions stack at the bottom of their side's vertical column
        # instead of the shared full-width bottom strip, so the central widget spans full height.
        self._bottom_in_lateral = False
        self._button_drag_filter = DockButtonDragFilter(mw)
        # A windowed dock is visible independently of the exclusive/tab state of
        # the region it came from. This lets users keep (for example) PyMOL on a
        # second monitor while opening another tool in the original side panel.
        self._windowed: set[str] = set()
        self._moving_window_id: str | None = None
        self._native_move_poll = QTimer(mw)
        self._native_move_poll.setInterval(30)
        self._native_move_poll.timeout.connect(self._poll_native_window_move)

        # ── FIX P2: single flag that blocks ALL reactive handlers ──
        # While True, _on_dock_visibility_changed and
        # _on_dock_location_changed do nothing.
        self._updating = False

        self.left_toolbar = VerticalToolbar(ToolbarSide.LEFT, self, mw)
        self.right_toolbar = VerticalToolbar(ToolbarSide.RIGHT, self, mw)
        self._add_toolbar_widget(self.left_toolbar, Qt.LeftToolBarArea)
        self._add_toolbar_widget(self.right_toolbar, Qt.RightToolBarArea)

        self._bottom_left_anchor: Optional[str] = None
        self._bottom_right_anchor: Optional[str] = None

    # ── Registro ────────────────────────────────────────────────

    def add_dock(
        self,
        dock: MSDockWidget,
        *,
        dock_id: str,
        region: Region,
        order: int,
        behavior: Behavior,
        title: Optional[str] = None,
        icon: Optional[QIcon] = None,
        starts_visible: bool = False,
        bottom_mode: BottomMode = BottomMode.SHARE,
    ) -> None:
        if not isinstance(dock, MSDockWidget):
            raise TypeError("DockManager.add_dock requires an MSDockWidget instance")
        if dock_id in self.entries:
            raise ValueError(f"Duplicate dock id: {dock_id}")

        entry = DockEntry(
            id=dock_id,
            dock=dock,
            title=title or dock.windowTitle() or dock_id,
            region=region,
            order=order,
            behavior=behavior,
            icon=icon,
            starts_visible=starts_visible,
            bottom_mode=bottom_mode,
        )
        self.entries[dock_id] = entry
        self.docks[dock_id] = dock

        state = self.region_states[region]
        state.order.append(dock_id)
        if starts_visible:
            state.visible.append(dock_id)
        self._region_defaults.setdefault(region, (behavior, bottom_mode))

        for region_key in Region:
            self._sort_region_state(region_key)

    def add_action_button(
        self,
        action_id: str,
        *,
        region: Region,
        order: int,
        on_click,
        title: str = "",
        icon: Optional[QIcon] = None,
        tooltip: Optional[str] = None,
        checkable: bool = False,
    ) -> QToolButton:
        """Add a standalone action button to a toolbar region — NOT a dock. Ordered among the
        region's dock buttons by ``order`` and re-added on every toolbar rebuild, so it survives
        drag/drop and toggles.

        Non-checkable (default): a click runs ``on_click()``.
        Checkable: the button toggles (shows the :checked accent) and ``on_click(checked: bool)``
        is called with the new state — use it to mirror a tab/panel that the action governs.
        """
        if action_id in self.action_buttons:
            raise ValueError(f"Action button id duplicado: {action_id}")
        button = _create_toolbar_button(title or action_id, icon)
        button.setCheckable(bool(checkable))
        if tooltip:
            button.setToolTip(tooltip)
        if checkable:
            button.toggled.connect(lambda checked: on_click(checked))
        else:
            button.clicked.connect(lambda _checked=False: on_click())
        self.action_buttons[action_id] = {"region": region, "order": int(order), "button": button}
        self._build_toolbars()
        return button

    # ── Build ────────────────────────────────────────────────────

    def build(self):
        ordered = sorted(self.entries.values(), key=self._sort_key)

        for entry in ordered:
            self._configure_dock(entry)
            button = _create_toolbar_button(entry.title, entry.icon)
            button.setProperty("dock_id", entry.id)
            self._button_drag_filter.register(button)
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, did=entry.id, btn=button: self.show_button_context_menu(btn, did, pos)
            )
            button.toggled.connect(
                lambda checked, did=entry.id: self.toggle(did, checked)
            )
            self.buttons[entry.id] = button

        self._build_toolbars()
        self.set_show_tool_names(self._show_tool_names)
        self._init_bottom_anchors()

        self._apply_all_region_visibility()
        self._schedule_lateral_rebuild()
        self._schedule_bottom_rebuild()
        self.sync_buttons()

    def _configure_dock(self, entry: DockEntry) -> None:
        dock = entry.dock
        dock.setObjectName(entry.id)
        dock.setWindowTitle(entry.title)
        if dock.parent() is not self.mw:
            dock.setParent(self.mw)
        content = dock.widget()
        if content is None:
            raise ValueError(f"Dock '{entry.id}' must have a widget configured before build")
        dock.setFeatures(
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable |
            QDockWidget.DockWidgetClosable
        )
        self.mw.addDockWidget(self._area_for_region(entry.region), dock)
        dock.hide()

        dock.visibilityChanged.connect(
            lambda visible, did=entry.id: self._on_dock_visibility_changed(did, visible)
        )
        dock.dockLocationChanged.connect(
            lambda area, did=entry.id: self._on_dock_location_changed(did, area)
        )
        dock.topLevelChanged.connect(
            lambda floating, did=entry.id: self._on_dock_top_level_changed(did, floating)
        )

    def _on_dock_top_level_changed(self, dock_id: str, floating: bool) -> None:
        dock = self.docks.get(dock_id)
        if dock is None:
            return
        entry = self.entries[dock_id]
        if floating:
            self._windowed.add(dock_id)
            self._remove_region_visible(entry.region, dock_id)
            # Manual dragging/double-clicking may still make Qt enter its utility
            # floating mode. Reset that mode and perform our direct native detach.
            if not (
                dock.parent() is None
                and dock.titleBarWidget() is dock._title_bar
            ):
                QTimer.singleShot(0, lambda did=dock_id: self._make_native_window(did))
            if self._uses_bottom_area(entry.region):
                self._schedule_bottom_rebuild()
            else:
                self._schedule_lateral_rebuild()
        else:
            self._windowed.discard(dock_id)
            if self._updating:
                self.sync_buttons()
                return
            if dock.isVisible():
                self._activate_dock_in_state(dock_id)
                self._apply_region_visibility(entry.region)
                if self._uses_bottom_area(entry.region):
                    self._schedule_bottom_rebuild()
                else:
                    self._schedule_lateral_rebuild()
        self.sync_buttons()

    def open_in_window(self, dock_id: str) -> None:
        """Detach a dock as a normal OS window without consuming its old region."""
        dock = self.docks.get(dock_id)
        if dock is None:
            return
        entry = self.entries[dock_id]
        self._windowed.add(dock_id)
        self._remove_region_visible(entry.region, dock_id)
        self._make_native_window(dock_id)
        QTimer.singleShot(0, dock.activateWindow)
        self.sync_buttons()

    def _make_native_window(self, dock_id: str) -> None:
        """Detach directly, clearing any prior QDockWidget utility-window mode."""
        dock = self.docks.get(dock_id)
        if dock is None:
            return
        was_updating = self._updating
        self._updating = True
        try:
            if dock.parent() is self.mw and dock.isFloating():
                dock.setFloating(False)
            self._windowed.add(dock_id)
            self._remove_region_visible(self.entries[dock_id].region, dock_id)
            dock._promote_floating_window()
        finally:
            self._updating = was_updating
        self.sync_buttons()

    def is_windowed(self, dock_id: str) -> bool:
        return dock_id in self._windowed

    def begin_native_window_drag(
        self,
        dock_id: str,
        global_pos: QPoint,
        title_offset: QPoint,
    ) -> bool:
        """Detach if needed, then delegate movement/snapping to the window manager."""
        dock = self.docks.get(dock_id)
        if dock is None:
            return False
        if dock_id not in self._windowed:
            self.open_in_window(dock_id)
            dock.move(global_pos - title_offset)
        self._moving_window_id = dock_id
        self._native_move_poll.start()
        handle = dock.windowHandle()
        return bool(handle is not None and handle.startSystemMove())

    def _poll_native_window_move(self) -> None:
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            return
        self.finish_native_window_drag()

    def finish_native_window_drag(self, global_pos: QPoint | None = None) -> None:
        """Redock in the original region when a native drag ends over AMDock."""
        dock_id = self._moving_window_id
        self._moving_window_id = None
        self._native_move_poll.stop()
        if dock_id is None or dock_id not in self._windowed:
            return
        cursor_pos = global_pos if global_pos is not None else QCursor.pos()
        local_pos = self.mw.mapFromGlobal(cursor_pos)
        if self.mw.isVisible() and self.mw.rect().contains(local_pos):
            self.dock_to_main_window(dock_id)

    def dock_to_main_window(self, dock_id: str) -> None:
        """Return a detached dock to its configured region."""
        dock = self.docks.get(dock_id)
        if dock is None:
            return
        entry = self.entries[dock_id]
        self._updating = True
        try:
            self._windowed.discard(dock_id)
            self._attach_dock_widget(dock_id)
            self._activate_dock_in_state(dock_id)
            self._apply_region_visibility(entry.region)
            dock.show()
            dock.raise_()
        finally:
            self._updating = False
        if self._uses_bottom_area(entry.region):
            self._schedule_bottom_rebuild()
        else:
            self._schedule_lateral_rebuild()
        self.sync_buttons()

    def _attach_dock_widget(self, dock_id: str) -> None:
        """Restore a native external window to QMainWindow dock ownership."""
        dock = self.docks[dock_id]
        dock.hide()
        if dock.parent() is not self.mw:
            dock.setParent(self.mw)
        elif dock.isFloating():
            dock.setFloating(False)
        dock.setTitleBarWidget(dock._title_bar)
        self.mw.addDockWidget(self._area_for_region(self.entries[dock_id].region), dock)

    def close_windowed_docks(self) -> None:
        """Reattach hidden external windows so they die with the main window."""
        self._moving_window_id = None
        self._native_move_poll.stop()
        self._updating = True
        try:
            for dock_id in tuple(self._windowed):
                dock = self.docks.get(dock_id)
                if dock is None:
                    continue
                self._attach_dock_widget(dock_id)
                dock.hide()
            self._windowed.clear()
        finally:
            self._updating = False
        self.sync_buttons()

    # ══════════════════════════════════════════════════════════════
    # FIX P4 / P5 — manual move detection
    # ══════════════════════════════════════════════════════════════

    def _on_dock_location_changed(self, dock_id: str, area: Qt.DockWidgetArea):
        """
        Fires when the user drags a dock to another area.
        We infer the sub-region (lateral TOP vs BOTTOM) with a singleShot
        so Qt has time to settle the layout.
        """
        if self._updating:
            return
        # Ignore if the dock has just floated (invalid area)
        if area == Qt.NoDockWidgetArea:
            return
        QTimer.singleShot(0, lambda: self._infer_and_update_region(dock_id, area))

    def _infer_and_update_region(self, dock_id: str, area: Qt.DockWidgetArea):
        """
        Infer the Region (sub-region) of a dock after a manual move, update the
        internal record and move the toolbar button.
        It does not call removeDockWidget/addDockWidget because Qt already moved it.
        """
        dock = self.docks.get(dock_id)
        if dock is None or dock.isFloating():
            return

        entry = self.entries[dock_id]
        old_region = entry.region

        # Determine the new Region from the Qt area
        new_region = self._infer_region_from_geometry(dock_id, area)
        if new_region == old_region:
            return  # No real change

        # Update internal state without touching the Qt layout
        self._updating = True
        try:
            was_visible = dock_id in self.region_states[old_region].visible

            new_behavior, new_bottom_mode = self._defaults_for_region(new_region)
            self._remove_from_region_state(old_region, dock_id)
            entry.region = new_region
            entry.behavior = new_behavior
            entry.bottom_mode = new_bottom_mode
            self._insert_into_region_state(new_region, dock_id)
            if was_visible:
                self._activate_dock_in_state(dock_id)

            # Move the toolbar button (FIX P5)
            self._build_toolbars()

            if self._uses_bottom_area(new_region) or self._uses_bottom_area(old_region):
                self._init_bottom_anchors()
                self._schedule_bottom_rebuild()
            else:
                self._schedule_lateral_rebuild()

            self.sync_buttons()
        finally:
            self._updating = False

    def _infer_region_from_geometry(self, dock_id: str,
                                    area: Qt.DockWidgetArea) -> Region:
        """
        Given the Qt area and the dock's current geometry, infer the sub-region.
        For lateral areas it compares the dock's Y centre with the window's Y
        centre to decide TOP vs BOTTOM.
        For the bottom area it decides LEFT vs RIGHT by the X centre.
        """
        dock = self.docks[dock_id]
        geo = dock.geometry()

        if area == Qt.DockWidgetArea.BottomDockWidgetArea:
            mw_center_x = self.mw.width() / 2
            return Region.BOTTOM_LEFT if geo.center().x() < mw_center_x else Region.BOTTOM_RIGHT

        mw_center_y = self.mw.height() / 2
        is_top_half = geo.center().y() < mw_center_y

        if area == Qt.DockWidgetArea.LeftDockWidgetArea:
            return Region.LEFT_TOP if is_top_half else Region.LEFT_BOTTOM
        if area == Qt.DockWidgetArea.RightDockWidgetArea:
            return Region.RIGHT_TOP if is_top_half else Region.RIGHT_BOTTOM

        # Fallback: keep the current region
        return self.entries[dock_id].region

    # ══════════════════════════════════════════════════════════════
    # move_to  (FIX P3 + P2)
    # ══════════════════════════════════════════════════════════════

    def move_to(self, dock_id: str, new_region: Region):
        """
        Move the dock to new_region via menu or button drag.
        FIX P3: preserves was_visible and restores visibility with a singleShot
                so Qt has time to settle the layout.
        FIX P2: wraps the whole operation in _updating=True so that
                visibilityChanged / dockLocationChanged do not fire reactive
                handlers during the relocation.
        """
        entry = self.entries[dock_id]
        old_region = entry.region
        dock = self.docks[dock_id]
        was_windowed = dock_id in self._windowed or dock.isFloating()
        was_visible = (
            dock.isVisible()
            if was_windowed
            else dock_id in self.region_states[old_region].visible
        )

        if old_region == new_region:
            if was_windowed:
                self.dock_to_main_window(dock_id)
            return

        self._updating = True
        try:
            if was_windowed:
                self._windowed.discard(dock_id)
                self._attach_dock_widget(dock_id)
            new_behavior, new_bottom_mode = self._defaults_for_region(new_region)

            # 1. Update internal state
            self._remove_from_region_state(old_region, dock_id)
            entry.region = new_region
            entry.behavior = new_behavior
            entry.bottom_mode = new_bottom_mode
            self._insert_into_region_state(new_region, dock_id)
            if was_visible:
                self._activate_dock_in_state(dock_id)

            # 2. Relocate the toolbar button
            self._build_toolbars()

            # 3. Move the QDockWidget to the right Qt area
            dock.hide()
            self.mw.removeDockWidget(dock)
            self.mw.addDockWidget(self._area_for_region(new_region), dock)

            bottom_changed = self._uses_bottom_area(old_region) or self._uses_bottom_area(new_region)
            if bottom_changed:
                self._init_bottom_anchors()

            # 4. Apply visibility for both affected regions
            self._apply_region_visibility(old_region)
            self._apply_region_visibility(new_region)

            # 5. Rebuild layouts
            if not self._uses_bottom_area(new_region):
                self._schedule_lateral_rebuild()
            if bottom_changed:
                self._schedule_bottom_rebuild()

        finally:
            self._updating = False

        # FIX P3: restore visibility AFTER Qt settles the layout.
        # raise_ also happens outside the _updating block.
        if was_visible:
            QTimer.singleShot(0, lambda: self._restore_visible_after_move(dock_id))

        self.sync_buttons()

    def _restore_visible_after_move(self, dock_id: str):
        """Show and raise the dock after a move_to, outside the _updating lock."""
        dock = self.docks.get(dock_id)
        if dock is None:
            return
        self._updating = True
        try:
            dock.show()
            dock.raise_()
            entry = self.entries[dock_id]
            self._anchor_in_region(dock_id, entry.region, True)
        finally:
            self._updating = False
        self.sync_buttons()

    # ── _anchor_in_region ────────────────────────────────────────

    def _anchor_in_region(self, dock_id: str, region: Region, was_visible: bool):
        if region.is_bottom():
            return

        dock = self.docks[dock_id]
        region_entries = self._region_entries(region)

        visible_siblings = [
            self.docks[entry.id]
            for entry in region_entries
            if entry.id != dock_id
            and entry.id not in self._windowed
            and self.docks[entry.id].isVisible()
            and not self.docks[entry.id].isFloating()
        ]

        if visible_siblings:
            self.mw.tabifyDockWidget(visible_siblings[0], dock)
            return

        other_region = self._other_lateral_region(region)
        if other_region is not None:
            other_visible = [
                self.docks[entry.id]
                for entry in self._region_entries(other_region)
                if entry.id not in self._windowed
                and self.docks[entry.id].isVisible()
                and not self.docks[entry.id].isFloating()
            ]
            if other_visible:
                ref = other_visible[0]
                if region in (Region.LEFT_TOP, Region.RIGHT_TOP):
                    self.mw.splitDockWidget(dock, ref, Qt.Vertical)
                else:
                    self.mw.splitDockWidget(ref, dock, Qt.Vertical)

    def _other_lateral_region(self, region: Region) -> Optional[Region]:
        pairs = {
            Region.LEFT_TOP: Region.LEFT_BOTTOM,
            Region.LEFT_BOTTOM: Region.LEFT_TOP,
            Region.RIGHT_TOP: Region.RIGHT_BOTTOM,
            Region.RIGHT_BOTTOM: Region.RIGHT_TOP,
        }
        return pairs.get(region)

    # ── drop_button ──────────────────────────────────────────────

    def drop_button(self, dock_id: str, target_toolbar: VerticalToolbar,
                    section: ToolbarSection, before_id: Optional[str]):
        entry = self.entries.get(dock_id)
        if entry is None:
            return

        new_region = self._region_from_toolbar_section(target_toolbar, section)
        same_pos = (entry.region == new_region)

        if same_pos:
            self.reorder(dock_id, new_region, before_id)
        else:
            self.move_to(dock_id, new_region)
            if before_id is not None:
                self.reorder(dock_id, new_region, before_id)

    def _region_from_toolbar_section(self, toolbar: VerticalToolbar,
                                     section: ToolbarSection) -> Region:
        is_left = toolbar.side == ToolbarSide.LEFT
        if section == ToolbarSection.TOP:
            return Region.LEFT_TOP if is_left else Region.RIGHT_TOP
        if section == ToolbarSection.MIDDLE:
            return Region.LEFT_BOTTOM if is_left else Region.RIGHT_BOTTOM
        return Region.BOTTOM_LEFT if is_left else Region.BOTTOM_RIGHT

    # ── reorder ──────────────────────────────────────────────────

    def reorder(self, dock_id: str, region: Region, before_id: Optional[str]):
        self._insert_into_region_state(region, dock_id, before_id)
        self._build_toolbars()

    # ── Toolbar/region helpers ───────────────────────────────────

    def _toolbar_for_region(self, region: Region) -> VerticalToolbar:
        return self.left_toolbar if region.is_left() else self.right_toolbar

    def set_bottom_in_lateral(self, enabled: bool) -> None:
        """If True, BOTTOM_LEFT/BOTTOM_RIGHT docks live at the bottom of the left/right
        vertical columns (freeing the central widget to fill full height) instead of the
        shared full-width bottom strip. Call before build(); a later call re-lays-out."""
        if self._bottom_in_lateral == enabled:
            return
        self._bottom_in_lateral = enabled
        if not self.docks:
            return
        for dock_id, entry in self.entries.items():
            if entry.region.is_bottom() and dock_id not in self._windowed:
                dock = self.docks[dock_id]
                self.mw.removeDockWidget(dock)
                self.mw.addDockWidget(self._area_for_region(entry.region), dock)
        self._init_bottom_anchors()
        self._apply_all_region_visibility()
        self._schedule_lateral_rebuild()
        self._schedule_bottom_rebuild()
        self.sync_buttons()

    def _area_for_region(self, region: Region) -> Qt.DockWidgetArea:
        if self._bottom_in_lateral and region.is_bottom():
            return Qt.LeftDockWidgetArea if region == Region.BOTTOM_LEFT else Qt.RightDockWidgetArea
        return region.qt_area()

    def _uses_bottom_area(self, region: Region) -> bool:
        """True when the region is laid out in Qt's shared bottom strip (vs. lateralized)."""
        return region.is_bottom() and not self._bottom_in_lateral

    def _bottom_region_for_side(self, lateral_region: Region) -> Region:
        return Region.BOTTOM_LEFT if lateral_region.is_left() else Region.BOTTOM_RIGHT

    def _sort_key(self, entry: DockEntry):
        region_order = {
            Region.LEFT_TOP: 0,
            Region.LEFT_BOTTOM: 1,
            Region.BOTTOM_LEFT: 2,
            Region.RIGHT_TOP: 3,
            Region.RIGHT_BOTTOM: 4,
            Region.BOTTOM_RIGHT: 5,
        }
        return (region_order[entry.region], entry.order)

    def _sort_region_state(self, region: Region):
        state = self.region_states[region]
        state.order.sort(key=lambda dock_id: self.entries[dock_id].order)
        order_index = {dock_id: idx for idx, dock_id in enumerate(state.order)}
        state.visible.sort(key=lambda dock_id: order_index.get(dock_id, 10_000))

    def _remove_from_region_state(self, region: Region, dock_id: str):
        state = self.region_states[region]
        if dock_id in state.order:
            state.order.remove(dock_id)
        if dock_id in state.visible:
            state.visible.remove(dock_id)

    def _insert_into_region_state(self, region: Region, dock_id: str,
                                  before_id: Optional[str] = None):
        state = self.region_states[region]
        if dock_id in state.order:
            state.order.remove(dock_id)
        if before_id and before_id in state.order:
            index = state.order.index(before_id)
            state.order.insert(index, dock_id)
        else:
            state.order.append(dock_id)
        if dock_id in state.visible:
            state.visible.sort(key=lambda item: state.order.index(item))

    def _set_region_visible(self, region: Region, dock_ids: List[str]):
        state = self.region_states[region]
        unique_ids = [dock_id for dock_id in state.order if dock_id in dock_ids]
        state.visible = unique_ids

    def _add_region_visible(self, region: Region, dock_id: str):
        state = self.region_states[region]
        if dock_id not in state.visible:
            state.visible.append(dock_id)
            state.visible.sort(key=lambda item: state.order.index(item))

    def _remove_region_visible(self, region: Region, dock_id: str):
        state = self.region_states[region]
        if dock_id in state.visible:
            state.visible.remove(dock_id)

    def _activate_dock_in_state(self, dock_id: str):
        entry = self.entries[dock_id]
        region = entry.region
        state = self.region_states[region]

        if self._uses_bottom_area(region):
            if entry.bottom_mode == BottomMode.SHARE:
                self._set_region_visible(region, [dock_id])
            else:
                self._add_region_visible(region, dock_id)
            return

        if entry.behavior in (Behavior.EXCLUSIVE, Behavior.MIXED_EXCLUSIVE):
            self._set_region_visible(region, [dock_id])
            return

        visible = [
            visible_id for visible_id in state.visible
            if self.entries[visible_id].behavior != Behavior.MIXED_EXCLUSIVE
        ]
        if dock_id not in visible:
            visible.append(dock_id)
        self._set_region_visible(region, visible)

    def _deactivate_dock_in_state(self, dock_id: str):
        entry = self.entries[dock_id]
        self._remove_region_visible(entry.region, dock_id)

    def _apply_region_visibility(self, region: Region):
        state = self.region_states[region]
        visible_ids = set(state.visible)
        for dock_id in state.order:
            dock = self.docks[dock_id]
            if dock_id in self._windowed:
                continue
            if dock_id in visible_ids:
                dock.show()
            else:
                dock.hide()

    def _apply_all_region_visibility(self):
        for region in Region:
            self._apply_region_visibility(region)

    def populate_move_menu(self, menu: QMenu, dock_id: str):
        entry = self.entries.get(dock_id)
        if entry is None:
            menu.addAction("(unknown dock)").setEnabled(False)
            return

        destinations = [
            ("Left Top", Region.LEFT_TOP),
            ("Left Bottom", Region.LEFT_BOTTOM),
            ("Bottom Left", Region.BOTTOM_LEFT),
            ("Right Top", Region.RIGHT_TOP),
            ("Right Bottom", Region.RIGHT_BOTTOM),
            ("Bottom Right", Region.BOTTOM_RIGHT),
        ]

        for label, region in destinations:
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(entry.region == region)
            act.triggered.connect(
                lambda checked=False, r=region, did=dock_id:
                QTimer.singleShot(0, lambda: self.move_to(did, r))
            )
            menu.addAction(act)

    def show_button_context_menu(self, button: QToolButton, dock_id: str, pos: QPoint):
        menu = QMenu(button)
        menu.setStyleSheet(MENU_STYLE_SHEET)
        window_action = menu.addAction(
            "Dock to Main Window" if self.docks[dock_id].isFloating() else "Open in Window"
        )
        if self.docks[dock_id].isFloating():
            window_action.triggered.connect(
                lambda checked=False, did=dock_id: self.dock_to_main_window(did)
            )
        else:
            window_action.triggered.connect(
                lambda checked=False, did=dock_id: self.open_in_window(did)
            )
        menu.addSeparator()
        move_menu = menu.addMenu("Move to")
        move_menu.setStyleSheet(MENU_STYLE_SHEET)
        self.populate_move_menu(move_menu, dock_id)
        menu.exec(button.mapToGlobal(pos))

    def show_toolbar_context_menu(self, global_pos: QPoint):
        menu = QMenu(self.mw)
        menu.setStyleSheet(MENU_STYLE_SHEET)
        action = QAction("Show Tool Names", menu)
        action.setCheckable(True)
        action.setChecked(self._show_tool_names)
        action.toggled.connect(self.set_show_tool_names)
        menu.addAction(action)
        menu.exec(global_pos)

    def set_show_tool_names(self, show: bool):
        self.set_button_style(
            Qt.ToolButtonStyle.ToolButtonTextUnderIcon
            if show else Qt.ToolButtonStyle.ToolButtonIconOnly
        )

    def _all_toolbar_buttons(self):
        yield from self.buttons.values()
        yield from (entry["button"] for entry in self.action_buttons.values())

    def set_button_style(
        self,
        style: Qt.ToolButtonStyle,
        *,
        icon_px: int = 24,
        font_px: int | None = None,
        width: int | None = None,
    ):
        """Icon-only / icon+text / text-only for every button in the side toolbars — dock
        buttons *and* action buttons (set_show_tool_names only ever reached the dock ones).
        Font goes through setFont, not a stylesheet, so it doesn't clobber the button's own
        palette-driven QSS. ``width`` overrides the toolbar width, which the collapsed/expanded
        defaults get wrong for text-only labels."""
        icon_only = style == Qt.ToolButtonStyle.ToolButtonIconOnly
        self._show_tool_names = not icon_only
        toolbar_width = width or (
            TOOLBAR_COLLAPSED_WIDTH if icon_only else TOOLBAR_EXPANDED_WIDTH
        )
        for toolbar in (self.left_toolbar, self.right_toolbar):
            toolbar.setFixedWidth(toolbar_width)
        wrap = style == Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        for button in self._all_toolbar_buttons():
            button.setToolButtonStyle(style)
            button.setIconSize(QSize(icon_px, icon_px))
            # QToolButton elides ("Molec…Tools") instead of wrapping; it only breaks on an
            # explicit newline, so under-icon labels wrap on their spaces.
            title = str(button.property("full_title") or button.text())
            button.setText(title.replace(" ", "\n") if wrap else title)
            if font_px:
                font = button.font()
                font.setPixelSize(int(font_px))
                button.setFont(font)

    def _defaults_for_region(self, region: Region) -> tuple[Behavior, BottomMode]:
        defaults = self._region_defaults.get(region)
        if defaults is not None:
            return defaults

        fallback = {
            Region.LEFT_TOP: (Behavior.EXCLUSIVE, BottomMode.SHARE),
            Region.LEFT_BOTTOM: (Behavior.MIXED_TAB, BottomMode.SHARE),
            Region.BOTTOM_LEFT: (Behavior.EXCLUSIVE, BottomMode.STACK),
            Region.RIGHT_TOP: (Behavior.EXCLUSIVE, BottomMode.SHARE),
            Region.RIGHT_BOTTOM: (Behavior.MIXED_TAB, BottomMode.SHARE),
            Region.BOTTOM_RIGHT: (Behavior.EXCLUSIVE, BottomMode.STACK),
        }
        return fallback[region]

    def _region_entries(self, region: Region) -> List[DockEntry]:
        return [self.entries[dock_id] for dock_id in self.region_states[region].order]

    # ── Build toolbars ────────────────────────────────────────────

    def _build_toolbars(self):
        self._clear_toolbar(self.left_toolbar)
        self._clear_toolbar(self.right_toolbar)
        for region_group, toolbar in (
                ([Region.LEFT_TOP, Region.LEFT_BOTTOM,
                  Region.BOTTOM_LEFT], self.left_toolbar),
                ([Region.RIGHT_TOP, Region.RIGHT_BOTTOM,
                  Region.BOTTOM_RIGHT], self.right_toolbar),
        ):
            for region in region_group:
                # dock buttons keep their (possibly drag-set) region order; standalone action
                # buttons are woven in by their `order` relative to the dock entries' orders.
                merged = [(entry.order, self.buttons[entry.id]) for entry in self._region_entries(region)]
                for action in self.action_buttons.values():
                    if action["region"] != region:
                        continue
                    idx = next((i for i, (order, _) in enumerate(merged) if order > action["order"]), len(merged))
                    merged.insert(idx, (action["order"], action["button"]))
                for _order, button in merged:
                    toolbar.add_button(region, button)

    def _clear_toolbar(self, toolbar: VerticalToolbar):
        for region in (Region.LEFT_TOP, Region.LEFT_BOTTOM, Region.BOTTOM_LEFT,
                       Region.RIGHT_TOP, Region.RIGHT_BOTTOM, Region.BOTTOM_RIGHT):
            if self._toolbar_for_region(region) is not toolbar:
                continue
            layout = toolbar.layout_for_region(region)
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
        toolbar._update_separator_visibility()

    def _add_toolbar_widget(self, widget: VerticalToolbar, area):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setContextMenuPolicy(Qt.PreventContextMenu)
        tb.setStyleSheet(
            "QToolBar { border: none; background: palette(window); padding: 0; spacing: 0; }"
        )
        tb.setOrientation(Qt.Orientation.Vertical)
        tb.addWidget(widget)
        self.mw.addToolBar(area, tb)

    # ══════════════════════════════════════════════════════════════
    # Bottom anchors + rebuild  (FIX P1 + P2)
    # ══════════════════════════════════════════════════════════════

    def _init_bottom_anchors(self):
        left = self.region_states[Region.BOTTOM_LEFT].order
        right = self.region_states[Region.BOTTOM_RIGHT].order
        self._bottom_left_anchor = left[0] if left else None
        self._bottom_right_anchor = right[0] if right else None

    def _schedule_bottom_rebuild(self):
        if self._bottom_rebuild_pending:
            return
        self._bottom_rebuild_pending = True
        QTimer.singleShot(0, self._rebuild_bottom_layouts)

    def _rebuild_bottom_layouts(self):
        """
        Rebuild the bottom area.
        Adjusted to avoid the segfault spotted under GDB.
        """
        self._bottom_rebuild_pending = False

        if self._bottom_in_lateral:
            return

        if not self._bottom_docks_in_order():
            return

        self._updating = True

        # --- CRITICAL FIX ---
        # Save the current options and DISABLE animations.
        # This stops any QPropertyAnimation internal to the docks BEFORE we try
        # to remove the widgets.
        original_options = self.mw.dockOptions()
        self.mw.setDockOptions(
            (original_options | QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks)
            & ~QMainWindow.AnimatedDocks
        )

        try:
            # 1. Limpieza segura
            self._reset_bottom_layouts()

            # 2. Re-posicionamiento
            left_root = self._bottom_root(Region.BOTTOM_LEFT)
            right_root = self._bottom_root(Region.BOTTOM_RIGHT)

            if left_root and right_root and left_root is not right_root:
                self.mw.splitDockWidget(left_root, right_root, Qt.Horizontal)

            self._retabify_bottom_region(Region.BOTTOM_LEFT)
            self._retabify_bottom_region(Region.BOTTOM_RIGHT)

        finally:
            # Restore the options (including animations if they were on)
            self.mw.setDockOptions(original_options)
            self._updating = False

        self.sync_buttons()

    def _visible_bottom_docks(self, region: Region) -> List[QDockWidget]:
        return [self.docks[dock_id] for dock_id in self.region_states[region].visible]

    def _bottom_docks_in_order(self) -> List[QDockWidget]:
        docks: List[QDockWidget] = []
        for region in (Region.BOTTOM_LEFT, Region.BOTTOM_RIGHT):
            docks.extend(
                self.docks[dock_id]
                for dock_id in self.region_states[region].order
                if dock_id not in self._windowed
            )
        return docks

    def _bottom_root(self, region: Region) -> Optional[QDockWidget]:
        visible = self._visible_bottom_docks(region)
        if visible:
            return visible[0]

        anchor_id = (
            self._bottom_left_anchor
            if region == Region.BOTTOM_LEFT
            else self._bottom_right_anchor
        )
        if anchor_id is not None and anchor_id not in self._windowed:
            return self.docks.get(anchor_id)
        return next(
            (
                self.docks[dock_id]
                for dock_id in self.region_states[region].order
                if dock_id not in self._windowed
            ),
            None,
        )

    def _reset_bottom_layouts(self):
        for dock in self._bottom_docks_in_order():
            dock.hide()
            self.mw.removeDockWidget(dock)
            self.mw.addDockWidget(Qt.BottomDockWidgetArea, dock)

        self._apply_region_visibility(Region.BOTTOM_LEFT)
        self._apply_region_visibility(Region.BOTTOM_RIGHT)

    def _retabify_bottom_region(self, region: Region):
        visible = self._visible_bottom_docks(region)
        if len(visible) < 2:
            return
        base = visible[0]
        for dock in visible[1:]:
            if dock is not base:
                self.mw.tabifyDockWidget(base, dock)

    # ══════════════════════════════════════════════════════════════
    # visibilityChanged handler  (FIX P2)
    # ══════════════════════════════════════════════════════════════

    def _on_dock_visibility_changed(self, dock_id: str, visible: bool):
        """
        FIX P2: this event is ignored entirely while _updating is True.
        That breaks the feedback loop that made the buttons flicker.
        """
        if self._updating:
            return
        if dock_id in self._windowed:
            self.sync_buttons()
            return
        entry = self.entries[dock_id]
        if visible:
            self._activate_dock_in_state(dock_id)
        else:
            self._deactivate_dock_in_state(dock_id)
        if self._uses_bottom_area(entry.region):
            self._schedule_bottom_rebuild()
        elif entry.region.is_bottom():
            self._schedule_lateral_rebuild()
        self.sync_buttons()

    # ══════════════════════════════════════════════════════════════
    # Toggle  (FIX P2)
    # ══════════════════════════════════════════════════════════════

    def toggle(self, dock_id: str, checked: bool):
        """
        FIX P2: we use _updating instead of _in_toggle so a single flag blocks
        every reactive handler.
        """
        if self._updating:
            return
        dock = self.docks[dock_id]
        if dock_id in self._windowed or dock.isFloating():
            if checked:
                dock.show()
                dock.raise_()
                dock.activateWindow()
            else:
                dock.hide()
            self.sync_buttons()
            return
        self._updating = True
        try:
            entry = self.entries[dock_id]

            if not checked:
                self._deactivate_dock_in_state(dock_id)
                self._apply_region_visibility(entry.region)
                if self._uses_bottom_area(entry.region):
                    self._schedule_bottom_rebuild()
                else:
                    self._schedule_lateral_rebuild()
                self.sync_buttons()
                return

            if self._uses_bottom_area(entry.region):
                self._toggle_bottom(dock_id)
            else:
                self._toggle_lateral(dock_id)

            self.sync_buttons()
        finally:
            self._updating = False

    # ── Toggle lateral ────────────────────────────────────────────

    def _toggle_lateral(self, dock_id: str):
        entry = self.entries[dock_id]
        target = self.docks[dock_id]
        self._activate_dock_in_state(dock_id)
        self._apply_region_visibility(entry.region)
        self._schedule_lateral_rebuild()
        target.raise_()

    def _retabify_region(self, region: Region):
        visible = [self.docks[dock_id] for dock_id in self.region_states[region].visible]
        self._retabify_in_order(visible)

    def _schedule_lateral_rebuild(self):
        if self._lateral_rebuild_pending:
            return
        self._lateral_rebuild_pending = True
        QTimer.singleShot(0, self._rebuild_lateral_layouts)

    def _rebuild_lateral_layouts(self):
        self._lateral_rebuild_pending = False

        if self._updating:
            self._schedule_lateral_rebuild()
            return

        self._updating = True
        original_options = self.mw.dockOptions()
        self.mw.setDockOptions(
            (original_options | QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks)
            & ~QMainWindow.AnimatedDocks
        )

        try:
            for column in (
                    [Region.LEFT_TOP, Region.LEFT_BOTTOM],
                    [Region.RIGHT_TOP, Region.RIGHT_BOTTOM],
            ):
                if self._bottom_in_lateral:
                    column = column + [self._bottom_region_for_side(column[0])]

                # Split each visible section-root under the previous one, top → bottom.
                prev_root: Optional[QDockWidget] = None
                for region in column:
                    visible = self._safe_lateral_docks(region)
                    if not visible:
                        continue
                    if prev_root is not None and not self._is_lateral_split_already_ok(
                            prev_root, visible[0]
                    ):
                        self.mw.splitDockWidget(prev_root, visible[0], Qt.Vertical)
                    prev_root = visible[0]

                for region in column:
                    self._retabify_in_order(self._safe_tab_docks(region))
        finally:
            self.mw.setDockOptions(original_options)
            self._updating = False

        self.sync_buttons()

    def _safe_lateral_docks(self, region: Region) -> List[QDockWidget]:
        area = self._area_for_region(region)
        docks: List[QDockWidget] = []
        for dock_id in self.region_states[region].visible:
            dock = self.docks[dock_id]
            if dock.isFloating() or not dock.isVisible():
                continue
            if self.mw.dockWidgetArea(dock) != area:
                continue
            docks.append(dock)
        return docks

    def _safe_tab_docks(self, region: Region) -> List[QDockWidget]:
        return [
            dock
            for dock_id in self.region_states[region].visible
            if self.entries[dock_id].behavior == Behavior.MIXED_TAB
            for dock in [self.docks[dock_id]]
            if dock.isVisible()
            and not dock.isFloating()
            and self.mw.dockWidgetArea(dock) == self._area_for_region(region)
        ]

    def _is_lateral_split_already_ok(self, top_dock: QDockWidget,
                                     bottom_dock: QDockWidget) -> bool:
        if top_dock is bottom_dock:
            return True
        if top_dock.isFloating() or bottom_dock.isFloating():
            return True
        if self.mw.dockWidgetArea(top_dock) != self.mw.dockWidgetArea(bottom_dock):
            return False

        top_geo = top_dock.geometry()
        bottom_geo = bottom_dock.geometry()
        if not top_geo.isValid() or not bottom_geo.isValid():
            return False

        return top_geo.center().y() < bottom_geo.center().y()

    # ── Toggle bottom ─────────────────────────────────────────────

    def _toggle_bottom(self, dock_id: str):
        entry = self.entries[dock_id]
        target = self.docks[dock_id]
        self._activate_dock_in_state(dock_id)
        self._apply_region_visibility(entry.region)
        self._schedule_bottom_rebuild()
        target.raise_()

    # ── Util ──────────────────────────────────────────────────────

    def _retabify_in_order(self, visible_docks: List[QDockWidget]):
        candidates = [
            dock for dock in visible_docks
            if dock.isVisible() and not dock.isFloating()
        ]
        if len(candidates) < 2:
            return
        base = candidates[0]
        base_area = self.mw.dockWidgetArea(base)
        for d in candidates[1:]:
            if d is not base and self.mw.dockWidgetArea(d) == base_area:
                self.mw.tabifyDockWidget(base, d)

    def sync_buttons(self, *args):
        visible_ids = {
            dock_id
            for state in self.region_states.values()
            for dock_id in state.visible
        }
        for dock_id, button in self.buttons.items():
            button.blockSignals(True)
            button.setChecked(
                dock_id in visible_ids
                or (dock_id in self._windowed and self.docks[dock_id].isVisible())
            )
            button.blockSignals(False)
