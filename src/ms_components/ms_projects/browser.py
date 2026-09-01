from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import (
    Qt, Signal, QRect, QSize, QAbstractTableModel, QModelIndex, QEvent,
)
from PySide6.QtGui import (
    QAction, QFont, QPainter, QColor, QPen, QBrush, QPainterPath, QMouseEvent,
    QKeySequence, QPalette, QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QProgressDialog, QPushButton, QSpinBox, QSplitter, QStyledItemDelegate,
    QStyle, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QToolButton,
    QTreeView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ms_flow.core.project.catalog import ProjectCatalogBackend
from ms_flow.core.settings.manager import SettingsManager
from ms_flow.core.settings.models import Settings
from ms_components.theme import color as theme_color


# ── Palette ───────────────────────────────────────────────────────────────────
_TOOL_COLORS: list[str] = [
    "#4e95ff", "#a259ff", "#ff6b6b", "#43d9ad",
    "#ffb347", "#f7768e", "#9ece6a", "#7dcfff",
]


def _tool_color(idx: int) -> str:
    return _TOOL_COLORS[idx % len(_TOOL_COLORS)]


def _tool_update_demo(app_id: str) -> dict[str, Any]:
    del app_id
    return {
        "latest_version": "",
        "headline": "No release information",
        "status": "Up to date",
        "summary": "This tool does not expose update metadata in the current workspace.",
        "notes": ["No release notes available."],
    }


# ── Stylesheet ────────────────────────────────────────────────────────────────

def _toolbox_shell_stylesheet() -> str:
    return """
QWidget#ProjectBrowserRoot { 
    background: #1a1525;
}
QFrame[surface="hero"] {
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 22px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #2a1d3e, stop:0.6 #1f1633, stop:1 #1a1228);
}
QFrame[surface="tab"], QFrame[surface="panel"], QFrame[surface="browser"] {
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 18px;
    background: #211830;
}
QFrame[surface="sidebar"] {
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 18px;
    background: #1d1629;
}
QFrame[role="separator"] { 
    background: rgba(255,255,255,0.07);
    max-height:1px;
    border:none;
}
QTabWidget::pane { 
    border: none;
    background: transparent;
}
QTabBar::tab {
    min-width:170px;
    padding:12px 18px;
    margin-right:6px;
    border-radius:12px;
    color:rgba(200,180,240,0.65);
    background:rgba(255,255,255,0.04);
    border:1px solid transparent;
}
QTabBar::tab:selected {
    color:rgba(235,228,245,0.95);
    background:rgba(103,58,183,0.22);
    border:1px solid rgba(103,58,183,0.30);
    font-weight:600;
}
QTabBar::tab:hover:!selected { 
    background:rgba(255,255,255,0.07);
    color:rgba(235,228,245,0.80);
}
QTreeWidget[nav="tools"] { 
    border:none;
    background:transparent;
    outline:none;
    font-size:13px;
}
QTreeWidget[nav="tools"]::item {
    padding:9px 12px;
    margin:2px 4px;
    border-radius:10px;
    color:rgba(200,180,240,0.70);
}
QTreeWidget[nav="tools"]::item:selected {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(103,58,183,0.45),stop:1 rgba(78,149,255,0.20));
    color:rgba(235,228,245,0.97);
    border:1px solid rgba(103,58,183,0.30);
}
QTreeWidget[nav="tools"]::item:hover:!selected {
    background:rgba(255,255,255,0.05);
    color:rgba(235,228,245,0.85);
}
QTreeWidget[nav="tools"]::item:disabled {
    color:rgba(200,180,240,0.30);
    font-size:10px;
    letter-spacing:0.08em;
    font-weight:700;
    padding-top:14px;
}
QLabel[role="eyebrow"] { 
    color:rgba(200,180,240,0.45);
    letter-spacing:0.10em;
    text-transform:uppercase;
    font-size:10px;
    font-weight:700;
}
QLabel[role="sidebarTitle"] {
    color:rgba(235,228,245,0.95);
    font-size:16px;
    font-weight:700;
}
QLabel[role="headline"] { 
    color:rgba(235,228,245,0.97);
    font-size:24px;
    font-weight:700;
}
QLabel[role="muted"] { 
    color:rgba(200,180,240,0.52);
    font-size:12px;
}
QLabel[role="statValue"] { 
    color:rgba(235,228,245,0.97);
    font-size:22px;
    font-weight:700;
}
QLabel[role="statLabel"] { 
    color:rgba(200,180,240,0.55);
}
QLabel[role="badge"] {
    padding:4px 12px;
    border-radius:999px;
    color:rgba(200,180,240,0.85);
    background:rgba(103,58,183,0.22);
    border:1px solid rgba(103,58,183,0.32);
    font-size:12px;
    font-weight:500;
}
QLabel[status="running"] { 
    padding:3px 10px;
    border-radius:999px;
    color:rgba(67,217,173,0.92);  
    background:rgba(67,217,173,0.12);  
    border:1px solid rgba(67,217,173,0.25);  
    font-size:11px;
    font-weight:600;
}
QLabel[status="closing"] { 
    padding:3px 10px;
    border-radius:999px;
    color:rgba(255,179,71,0.92);  
    background:rgba(255,179,71,0.12);  
    border:1px solid rgba(255,179,71,0.25);  
    font-size:11px;
    font-weight:600;
}
QLabel[status="launching"] { 
    padding:3px 10px;
    border-radius:999px;
    color:rgba(78,149,255,0.92);  
    background:rgba(78,149,255,0.12);  
    border:1px solid rgba(78,149,255,0.25);  
    font-size:11px;
    font-weight:600;
}
QLabel[status="done"] {
    padding:3px 10px;
    border-radius:999px;
    color:rgba(67,217,173,0.92);  
    background:rgba(67,217,173,0.12);  
    border:1px solid rgba(67,217,173,0.25);  
    font-size:11px;
    font-weight:600;
}
QPushButton {
    padding:8px 14px;
    border-radius:10px;
    background:rgba(255,255,255,0.06);
    border:1px solid rgba(255,255,255,0.09);
    color:rgba(200,180,240,0.82);
}
QPushButton:hover  { 
    background:rgba(255,255,255,0.10);
    border:1px solid rgba(255,255,255,0.13);
    color:rgba(235,228,245,0.95);
}
QPushButton:pressed { 
    background:rgba(255,255,255,0.07);
}
QPushButton:disabled { 
    color:rgba(200,180,240,0.28);
    border:1px solid rgba(255,255,255,0.05);
    background:rgba(255,255,255,0.03);
}
QPushButton[primary="true"] {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(103,58,183,0.92),stop:1 rgba(78,149,255,0.88));
    color:rgba(235,228,245,0.97);
    border:none;
    font-weight:600;
}
QPushButton[primary="true"]:hover {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(118,72,200,1.0),stop:1 rgba(95,162,255,1.0));
}
QPushButton[danger="true"] {
    background:rgba(162,45,45,0.25);
    color:rgba(240,149,149,0.90);
    border:1px solid rgba(162,45,45,0.35);
}
QPushButton[danger="true"]:hover { 
    background:rgba(162,45,45,0.40);
    color:rgba(240,149,149,1.0);
}
QToolButton {
    padding:5px;
    border-radius:8px;
    background:rgba(255,255,255,0.05);
    border:1px solid rgba(255,255,255,0.07);
    color:rgba(200,180,240,0.75);
}
QToolButton:hover   { 
    background:rgba(255,255,255,0.10);
    color:rgba(235,228,245,0.95);
}
QToolButton:checked { 
    background:rgba(103,58,183,0.25);
    border:1px solid rgba(103,58,183,0.35);
    color:rgba(235,228,245,0.95);
}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    border-radius:10px;
    padding:6px 8px;
    background:rgba(255,255,255,0.05);
    border:1px solid rgba(255,255,255,0.09);
    color:rgba(235,228,245,0.90);
    selection-background-color:rgba(103,58,183,0.45);
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border:1px solid rgba(103,58,183,0.55);
    background:rgba(103,58,183,0.08);
}
QComboBox::drop-down { 
    border:none;
}
QTableWidget {
    border-radius:10px;
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.07);
    color:rgba(235,228,245,0.85);
    gridline-color:rgba(255,255,255,0.05);
}
QHeaderView::section {
    background:rgba(103,58,183,0.14);
    border:none;
    border-bottom:1px solid rgba(103,58,183,0.22);
    padding:8px;
    color:rgba(200,180,240,0.70);
    font-weight:600;
    font-size:11px;
}
QTableWidget::item:selected { 
    background:rgba(103,58,183,0.28);
    color:rgba(235,228,245,0.97);
}
QSplitter::handle { 
    background:rgba(255,255,255,0.06);
    width:1px;
}
QScrollBar:vertical { 
    background:transparent;
    width:6px;
    margin:0;
}
QScrollBar::handle:vertical { 
    background:rgba(103,58,183,0.35);
    border-radius:3px;
    min-height:30px;
}
QScrollBar::handle:vertical:hover { 
    background:rgba(103,58,183,0.55);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
    height:0;
}
QScrollBar:horizontal { 
    background:transparent;
    height:6px;
    margin:0;
}
QScrollBar::handle:horizontal { 
    background:rgba(103,58,183,0.35);
    border-radius:3px;
    min-width:30px;
}
QScrollBar::handle:horizontal:hover { 
    background:rgba(103,58,183,0.55);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { 
    width:0;
}
"""


# ── ProjectItem (self-contained) ──────────────────────────────────────────────

@dataclass
class ProjectItem:
    id: Any
    name: str
    description: str
    path: str
    last_modified: str
    app_id: str = ""
    favorite: bool = False
    tags: List[str] = field(default_factory=list)
    language: Optional[str] = None
    color: Optional[str] = None


# ── ProjectTableModel ─────────────────────────────────────────────────────────

_COL_NAME  = 0   # avatar + name + id
_COL_META  = 1   # description
_COL_PATH  = 2   # path  (stretch)
_COL_DATE  = 3   # last_modified
_COL_STAR  = 4   # ★ button
_COL_MENU  = 5   # ⋯ button
_COL_COUNT = 6


class ProjectTableModel(QAbstractTableModel):
    """All projects in memory. Scope/filter/search/sort are pure Python."""

    HEADERS = ["", "Description", "Modified", "Path", "", ""]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all:     List[ProjectItem] = []
        self._visible: List[ProjectItem] = []
        self._scope:   Optional[str]     = None
        self._filter:  str               = "all"
        self._search:  str               = ""
        self._sort_col: int              = _COL_DATE
        self._sort_asc: bool             = False

    # ── Feed ─────────────────────────────────────────────────────

    def load(self, projects: List[ProjectItem]) -> None:
        self.beginResetModel()
        self._all = list(projects)
        self._rebuild()
        self.endResetModel()

    # ── Controls ──────────────────────────────────────────────────

    def set_scope(self, app_id: Optional[str]) -> None:
        self._scope = app_id
        self._reset()

    def set_filter(self, key: str) -> None:
        self._filter = key
        self._reset()

    def set_search(self, text: str) -> None:
        self._search = text.lower().strip()
        self._reset()

    def set_sort(self, col: int, ascending: bool) -> None:
        self._sort_col = col
        self._sort_asc = ascending
        self._reset()

    def _reset(self) -> None:
        self.beginResetModel()
        self._rebuild()
        self.endResetModel()

    def _rebuild(self) -> None:
        pl = self._all
        if self._scope:
            pl = [p for p in pl if p.app_id == self._scope]
        if self._filter == "favorites":
            pl = [p for p in pl if p.favorite]
        elif self._filter == "has_description":
            pl = [p for p in pl if p.description.strip()]
        elif self._filter == "has_tags":
            pl = [p for p in pl if p.tags]
        if self._search:
            q = self._search
            pl = [p for p in pl
                  if q in p.name.lower() or q in p.description.lower()
                  or q in str(p.path).lower()
                  or any(q in t.lower() for t in p.tags)]
        key_fn = {
            _COL_NAME: lambda p: p.name.lower(),
            _COL_PATH: lambda p: str(p.path).lower(),
            _COL_DATE: lambda p: p.last_modified,
        }.get(self._sort_col, lambda p: p.last_modified)
        self._visible = sorted(pl, key=key_fn, reverse=not self._sort_asc)

    # ── Qt interface ──────────────────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._visible)

    def columnCount(self, parent=QModelIndex()) -> int:
        return _COL_COUNT

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section] if section < len(self.HEADERS) else ""
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        p   = self._visible[index.row()]
        col = index.column()
        if role == Qt.UserRole:
            return p
        if role == Qt.DisplayRole:
            if col == _COL_NAME: return p.name
            if col == _COL_META: return p.description
            if col == _COL_PATH: return str(p.path)
            if col == _COL_DATE: return p.last_modified
            return ""
        if role == Qt.ToolTipRole:
            if col == _COL_NAME:
                tags = ", ".join(p.tags) if p.tags else ""
                parts = [p.name, f"ID: {p.id}"]
                if tags:
                    parts.append(f"Tags: {tags}")
                return "\n".join(parts)
            if col == _COL_META:
                return p.description or "No description"
            if col == _COL_PATH:
                return str(p.path)
            if col == _COL_DATE:
                return p.last_modified
        return None

    def flags(self, index: QModelIndex):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # ── Helpers ───────────────────────────────────────────────────

    def project_at(self, row: int) -> Optional[ProjectItem]:
        return self._visible[row] if 0 <= row < len(self._visible) else None

    def all_visible(self) -> List[ProjectItem]:
        return list(self._visible)

    def counts_by_app(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self._all:
            counts[p.app_id] = counts.get(p.app_id, 0) + 1
        return counts

    def total_all(self) -> int:
        return len(self._all)


# ── ProjectRowDelegate ────────────────────────────────────────────────────────

class ProjectRowDelegate(QStyledItemDelegate):
    """
    Col 0 — avatar circle + project name + project id
    Col 1-3 — plain muted text (Qt default overridden for color)
    Col 4 — ★ favorite (always visible)
    Col 5 — ⋯ menu (always visible)
    """

    favorite_clicked = Signal(object)          # ProjectItem
    menu_requested   = Signal(object, object)  # ProjectItem, QPoint (global)

    _AVATAR   = 34
    _BTN_SIZE = 26
    _BTN_R    = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_row = -1

    def set_hover_row(self, row: int) -> None:
        self._hover_row = row

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 62)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        project: Optional[ProjectItem] = index.data(Qt.UserRole)
        if not project:
            super().paint(painter, option, index)
            painter.restore()
            return

        col      = index.column()
        rect     = option.rect
        is_sel   = bool(option.state & QStyle.State_Selected)
        is_hover = self._hover_row == index.row()
        palette  = option.palette

        bg = QColor(palette.color(
            QPalette.ColorRole.Highlight if is_sel
            else QPalette.ColorRole.AlternateBase
        ))
        bg.setAlpha(45 if is_sel else 150 if is_hover else 0)
        if bg.alpha() > 0:
            painter.fillRect(rect.adjusted(0, 1, 0, 0), bg)
        if col == _COL_NAME:
            if is_sel:
                painter.setBrush(QBrush(palette.color(QPalette.ColorRole.Highlight)))
                painter.setPen(Qt.NoPen)
                painter.drawRect(QRect(rect.left(), rect.top()+1, 3, rect.height()-1))
            self._paint_name_col(painter, rect, project, palette)

        elif col in (_COL_META, _COL_PATH, _COL_DATE):
            role = (
                QPalette.ColorRole.Text
                if col == _COL_META
                else QPalette.ColorRole.PlaceholderText
            )
            painter.setPen(QPen(palette.color(role)))
            painter.setFont(QFont("", 9 if col == _COL_META else 8))
            text = index.data(Qt.DisplayRole) or ""
            flags = Qt.AlignLeft | Qt.AlignVCenter
            if col == _COL_META:
                flags = Qt.AlignLeft | Qt.TextWordWrap
            painter.drawText(rect.adjusted(6, 8 if col == _COL_META else 0, -6, -8 if col == _COL_META else 0),
                             flags, text)

        elif col == _COL_STAR:
            self._paint_star(painter, rect, project, is_hover, palette)

        elif col == _COL_MENU:
            self._paint_menu_btn(painter, rect, is_hover, palette)

        painter.restore()

    def _paint_name_col(
        self,
        painter: QPainter,
        rect: QRect,
        project: ProjectItem,
        palette: QPalette,
    ):
        # Avatar
        av_x  = rect.left() + 10
        av_y  = rect.center().y() - self._AVATAR // 2
        av_r  = QRect(av_x, av_y, self._AVATAR, self._AVATAR)
        color = QColor(project.color) if project.color else QColor("#4e95ff")
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(av_r)
        tc = QColor("#202124") if color.lightness() > 150 else QColor("#ffffff")
        painter.setPen(tc)
        painter.setFont(QFont("", 12, QFont.Bold))
        painter.drawText(av_r, Qt.AlignCenter, (project.name or "?")[:1].upper())

        # Name
        tx = av_x + self._AVATAR + 10
        painter.setFont(QFont("", 11, QFont.Bold))
        painter.setPen(palette.color(QPalette.ColorRole.Text))
        painter.drawText(QRect(tx, rect.top()+8, rect.width()-tx-8, 20),
                         Qt.AlignLeft | Qt.AlignVCenter, project.name or "")

        # Project id
        painter.setFont(QFont("", 8))
        painter.setPen(palette.color(QPalette.ColorRole.PlaceholderText))
        painter.drawText(
            QRect(tx, rect.top() + 30, rect.width() - tx - 8, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"ID: {project.id}",
        )

    def _paint_star(self, painter, rect, project, is_hover, palette: QPalette):
        if project.favorite:
            favorite = theme_color("yellow")
            favorite_bg = QColor(favorite)
            favorite_bg.setAlpha(25)
            favorite_border = QColor(favorite)
            favorite_border.setAlpha(80)
            painter.setBrush(QBrush(favorite_bg))
            painter.setPen(QPen(favorite_border, 1))
            bh = self._BTN_SIZE
            r  = rect.adjusted(3, (rect.height()-bh)//2, -3, -(rect.height()-bh)//2)
            painter.drawRoundedRect(r, self._BTN_R, self._BTN_R)
            painter.setPen(QPen(favorite))
        elif is_hover:
            painter.setPen(QPen(palette.color(QPalette.ColorRole.Text)))
        else:
            painter.setPen(QPen(palette.color(QPalette.ColorRole.PlaceholderText)))
        painter.setFont(QFont("", 12))
        painter.drawText(rect, Qt.AlignCenter, "★")

    def _paint_menu_btn(self, painter, rect, is_hover, palette: QPalette):
        if is_hover:
            bh = self._BTN_SIZE
            r  = rect.adjusted(3, (rect.height()-bh)//2, -3, -(rect.height()-bh)//2)
            painter.setBrush(QBrush(palette.color(QPalette.ColorRole.AlternateBase)))
            painter.setPen(QPen(palette.color(QPalette.ColorRole.Mid), 1))
            painter.drawRoundedRect(r, self._BTN_R, self._BTN_R)
        painter.setPen(QPen(palette.color(
            QPalette.ColorRole.Text
            if is_hover
            else QPalette.ColorRole.PlaceholderText
        )))
        painter.setFont(QFont("", 13, QFont.Bold))
        painter.drawText(rect, Qt.AlignCenter, "⋯")

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            project: Optional[ProjectItem] = index.data(Qt.UserRole)
            if not project:
                return False
            col = index.column()
            if col == _COL_STAR:
                self.favorite_clicked.emit(project)
                return True
            if col == _COL_MENU:
                vp = option.widget.viewport() if option.widget else None
                gp = vp.mapToGlobal(event.position().toPoint()) if vp else event.globalPos()
                self.menu_requested.emit(project, gp)
                return True
        return super().editorEvent(event, model, option, index)


# ── ProjectTreeWidget ─────────────────────────────────────────────────────────

class ProjectTreeWidget(QWidget):
    """
    QTreeView-based project list.
    - All data in ProjectTableModel (in-memory, no DB callbacks)
    - Fixed columns: Name | Meta | Date | Path(stretch) | ★ | ⋯
    - ★ always visible
    ⋯ opens context menu with all actions
    - Hover tracked via event filter on viewport
    """

    project_selected  = Signal(object)   # ProjectItem
    project_opened    = Signal(object)   # ProjectItem
    favorite_toggled  = Signal(object)   # ProjectItem
    edit_requested    = Signal(object)   # ProjectItem
    delete_requested  = Signal(list)     # [ProjectItem]
    export_requested  = Signal(list)
    stats_requested   = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── Toolbar ───────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        self._filter_labels = {
            "all": "All",
            "favorites": "Favorites",
            "has_description": "Has description",
            "has_tags": "Has tags",
        }
        self._filter_btn = QToolButton()
        self._filter_btn.setText("▾ All")
        self._filter_btn.setToolTip("Filter")
        self._filter_btn.setPopupMode(QToolButton.InstantPopup)
        filter_menu = QMenu(self._filter_btn)
        self._filter_actions: dict[str, QAction] = {}
        for key, label in self._filter_labels.items():
            act = filter_menu.addAction(label)
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, k=key: self._set_filter(k))
            self._filter_actions[key] = act
        self._filter_actions["all"].setChecked(True)
        self._filter_btn.setMenu(filter_menu)
        toolbar.addWidget(self._filter_btn)

        toolbar.addStretch(1)

        self._count_label = QLabel("")
        self._count_label.setProperty("role", "muted")
        self._count_label.setStyleSheet("color: palette(placeholder-text);")
        toolbar.addWidget(self._count_label)

        toolbar.addStretch(1)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search...")
        self._search.setMinimumHeight(28)
        self._search.setMinimumWidth(200)
        self._search.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search)

        layout.addLayout(toolbar)

        # ── QTreeView ─────────────────────────────────────────────
        self.model = ProjectTableModel()
        self.view  = QTreeView()
        self.view.setModel(self.model)
        self.view.setRootIsDecorated(False)
        self.view.setItemsExpandable(False)
        self.view.setUniformRowHeights(True)
        self.view.setMouseTracking(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Extended by default: plain click selects one row, Ctrl/Shift-click adds
        # more. No mode toggle to discover before multi-selecting.
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setStyleSheet("""
            QTreeView {
                background: palette(window);
                border: none;
                outline: none;
                color: palette(text);
            }
            QTreeView::item {
                border: none;
                padding: 0;
            }
            QTreeView::item:selected {
                background: transparent;
            }
        """)

        # Header
        hdr = self.view.header()
        hdr.setStyleSheet("""
            QHeaderView::section {
                background: palette(window);
                border: none;
                border-bottom: 1px solid palette(mid);
                padding: 6px 8px;
                color: palette(placeholder-text);
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.05em;
            }
        """)
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.Fixed)
        hdr.setSectionResizeMode(_COL_META, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_PATH, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_DATE, QHeaderView.Fixed)
        hdr.setSectionResizeMode(_COL_STAR, QHeaderView.Fixed)
        hdr.setSectionResizeMode(_COL_MENU, QHeaderView.Fixed)
        hdr.setStretchLastSection(False)
        hdr.resizeSection(_COL_NAME, 300)
        hdr.resizeSection(_COL_DATE, 100)
        hdr.resizeSection(_COL_STAR, 30)
        hdr.resizeSection(_COL_MENU, 30)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(_COL_DATE, Qt.DescendingOrder)
        hdr.sectionClicked.connect(self._on_header_clicked)

        self.delegate = ProjectRowDelegate(self.view)
        for col in range(_COL_COUNT):
            self.view.setItemDelegateForColumn(col, self.delegate)

        self.delegate.favorite_clicked.connect(self._on_favorite)
        self.delegate.menu_requested.connect(self._on_menu_requested)
        self.view.doubleClicked.connect(self._on_double_clicked)
        self.view.clicked.connect(self._on_clicked)
        self.view.viewport().installEventFilter(self)

        # Delete removes the current selection (one or more rows).
        del_sc = QShortcut(QKeySequence.Delete, self.view)
        del_sc.setContext(Qt.WidgetWithChildrenShortcut)
        del_sc.activated.connect(self._on_delete_shortcut)

        layout.addWidget(self.view, 1)
        # self._rebalance_columns()
        self._update_count()

    # ── Event filter — hover tracking ─────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.view.viewport():
            t = event.type()
            if t in (QEvent.MouseMove, QEvent.HoverMove):
                point = event.position().toPoint()
                idx = self.view.indexAt(point)
                row = idx.row() if idx.isValid() else -1
                if row != self.delegate._hover_row:
                    self.delegate.set_hover_row(row)
                    self.view.viewport().update()
            elif t == QEvent.Leave:
                self.delegate.set_hover_row(-1)
                self.view.viewport().update()
        return super().eventFilter(obj, event)

    # def resizeEvent(self, event):
    #     super().resizeEvent(event)
    #     self._rebalance_columns()

    # ── Slots ─────────────────────────────────────────────────────

    def _on_clicked(self, index: QModelIndex):
        p = self.model.project_at(index.row())
        if p:
            self.project_selected.emit(p)

    def _on_double_clicked(self, index: QModelIndex):
        p = self.model.project_at(index.row())
        if p and index.column() not in (_COL_STAR, _COL_MENU):
            self.project_opened.emit(p)

    def _on_favorite(self, project: ProjectItem):
        self.favorite_toggled.emit(project)

    def _delete_targets(self, project: ProjectItem) -> List[ProjectItem]:
        """If the clicked row is part of a multi-selection, delete the whole
        selection; otherwise just the clicked project."""
        selected = self.selected_projects()
        if len(selected) > 1 and any(p.id == project.id for p in selected):
            return selected
        return [project]

    def _on_delete_shortcut(self):
        targets = self.selected_projects()
        if targets:
            self.delete_requested.emit(targets)

    def _on_menu_requested(self, project: ProjectItem, global_pos):
        targets = self._delete_targets(project)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: palette(window);
                border: 1px solid palette(mid);
                border-radius: 10px;
                padding: 4px;
                color: palette(text);
            }
            QMenu::item {
                padding: 8px 16px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
            QMenu::separator {
                height: 1px;
                background: palette(mid);
                margin: 4px 8px;
            }
        """)
        menu.addAction("Open").triggered.connect(
            lambda: self.project_opened.emit(project))
        menu.addAction("Edit").triggered.connect(
            lambda: self.edit_requested.emit(project))
        menu.addSeparator()
        fav_label = "Remove from favorites" if project.favorite else "Add to favorites"
        menu.addAction(fav_label).triggered.connect(
            lambda: self.favorite_toggled.emit(project))
        menu.addAction("Export").triggered.connect(
            lambda: self.export_requested.emit([project]))
        menu.addSeparator()
        del_label = f"Delete {len(targets)} projects…" if len(targets) > 1 else "Delete…"
        menu.addAction(del_label).triggered.connect(
            lambda: self.delete_requested.emit(targets))
        menu.exec(global_pos)

    def _set_filter(self, key: str):
        for k, act in self._filter_actions.items():
            act.setChecked(k == key)
        self._filter_btn.setText(f"▾ {self._filter_labels.get(key, 'All')}")
        self.model.set_filter(key)
        self._update_count()

    def _on_search(self, text: str):
        self.model.set_search(text)
        self._update_count()

    def _on_header_clicked(self, logical: int):
        if logical in (_COL_STAR, _COL_MENU):
            return
        asc = (not self.model._sort_asc
               if logical == self.model._sort_col else True)
        self.model.set_sort(logical, asc)
        self.view.header().setSortIndicator(
            logical, Qt.AscendingOrder if asc else Qt.DescendingOrder)
        self._update_count()

    def _update_count(self):
        total   = self.model.total_all()
        visible = self.model.rowCount()
        if visible < total:
            self._count_label.setText(f"{visible} of {total} projects")
        else:
            self._count_label.setText(f"{total} project{'s' if total != 1 else ''}")

    # ── Public API ────────────────────────────────────────────────

    def load(self, projects: List[ProjectItem]) -> None:
        self.model.load(projects)
        self._update_count()

    def set_scope(self, app_id: Optional[str]) -> None:
        self.model.set_scope(app_id)
        self._update_count()

    def selected_projects(self) -> List[ProjectItem]:
        rows = {idx.row() for idx in self.view.selectedIndexes()}
        return [p for p in (self.model.project_at(r) for r in sorted(rows)) if p]

    def counts_by_app(self) -> dict[str, int]:
        return self.model.counts_by_app()


# ── Dialogs ───────────────────────────────────────────────────────────────────

class StatsDialog(QDialog):
    def __init__(self, projects: list, parent=None):
        super().__init__(parent)
        self.projects = projects
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Statistics")
        self.setMinimumSize(480, 360)
        layout = QVBoxLayout(self)
        total     = len(self.projects)
        favorites = sum(1 for p in self.projects if p.favorite)
        app_counts: dict[str, int] = {}
        tags: dict[str, int] = {}
        for p in self.projects:
            n = p.language or "Unknown"
            app_counts[n] = app_counts.get(n, 0) + 1
            for t in p.tags:
                tags[t] = tags.get(t, 0) + 1
        html = [f"<h2>{total} project(s)</h2><h3>Apps</h3><ul>"]
        for n, c in sorted(app_counts.items(), key=lambda x: x[1], reverse=True):
            html.append(f"<li><b>{n}</b>: {c}</li>")
        html += ["</ul>", f"<p><b>Favorites:</b> {favorites}</p>"]
        if tags:
            html.append("<h3>Tags</h3><ul>")
            for t, c in sorted(tags.items(), key=lambda x: x[1], reverse=True)[:8]:
                html.append(f"<li><b>{t}</b>: {c}</li>")
            html.append("</ul>")
        view = QTextEdit()
        view.setReadOnly(True)
        view.setHtml("".join(html))
        layout.addWidget(view)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


class ProjectFormDialog(QDialog):
    def __init__(self, *, apps: list, mode: str,
                 initial_data: dict | None = None,
                 allow_app_selection: bool = True, parent=None):
        super().__init__(parent)
        self.apps = apps
        self.mode = mode
        self.initial_data = initial_data or {}
        self.allow_app_selection = allow_app_selection
        self._setup_ui()

    def _setup_ui(self):
        is_edit = self.mode == "edit"
        self.setWindowTitle("Edit project" if is_edit else "New project")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input        = QLineEdit(self.initial_data.get("name", ""))
        self.path_input        = QLineEdit(str(self.initial_data.get("path", "")))
        self.path_input.setReadOnly(True)
        self.description_input = QTextEdit(self.initial_data.get("description", ""))
        self.description_input.setMinimumHeight(120)
        self.tags_input = QLineEdit(
            ", ".join(self.initial_data["tags"])
            if isinstance(self.initial_data.get("tags"), list)
            else self.initial_data.get("tags", "")
        )
        self.app_combo = QComboBox()
        for app in self.apps:
            self.app_combo.addItem(app.name, app.app_id)
        cid = self.initial_data.get("app_id", "")
        if cid:
            idx = self.app_combo.findData(cid)
            if idx >= 0: self.app_combo.setCurrentIndex(idx)
        self.app_combo.setEnabled(self.allow_app_selection and not is_edit)
        path_row = QWidget()
        pl = QHBoxLayout(path_row)
        pl.setContentsMargins(0,0,0,0)
        pl.addWidget(self.path_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        browse_btn.setEnabled(not is_edit)
        pl.addWidget(browse_btn)
        form.addRow("Name:", self.name_input)
        form.addRow("App:", self.app_combo)
        form.addRow("Path:", path_row)
        form.addRow("Tags:", self.tags_input)
        form.addRow("Description:", self.description_input)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder",
            self.path_input.text().strip() or str(Path.home()))
        if folder: self.path_input.setText(folder)

    def accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Invalid data", "The name cannot be empty.")
            return
        if not self.path_input.text().strip():
            QMessageBox.warning(self, "Invalid data", "The path cannot be empty.")
            return
        if self.app_combo.currentData() is None:
            QMessageBox.warning(self, "Invalid data", "You must select an app.")
            return
        super().accept()

    def get_data(self) -> dict:
        return {
            "name":        self.name_input.text().strip(),
            "path":        Path(self.path_input.text().strip()),
            "description": self.description_input.toPlainText().strip(),
            "tags":        [t.strip() for t in self.tags_input.text().split(",") if t.strip()],
            "app_id":      str(self.app_combo.currentData()),
        }


class StatTile(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setProperty("surface", "panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        self.value_label   = QLabel("0", self)
        self.value_label.setProperty("role", "statValue")
        self.caption_label = QLabel(label, self)
        self.caption_label.setProperty("role", "statLabel")
        lay.addWidget(self.value_label)
        lay.addWidget(self.caption_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


# ── ProjectBrowserPanel ───────────────────────────────────────────────────────

class ProjectBrowserPanel(QWidget):
    project_requested = Signal(str)
    project_created   = Signal(str)
    projects_changed  = Signal()

    def __init__(self, *, app_id: str | None = None, header_title: str,
                 hint_text: str, allow_app_selection: bool | None = None,
                 default_app_id: str | None = None, launch_on_open: bool = True,
                 open_after_create: bool = False,
                 _backend: ProjectCatalogBackend | None = None, parent=None):
        super().__init__(parent)
        self.app_id              = (app_id or "").strip() or None
        self.backend             = _backend or ProjectCatalogBackend(app_id_filter=None)
        self.header_title        = header_title
        self.hint_text           = hint_text
        self.allow_app_selection = (
            bool(allow_app_selection) if allow_app_selection is not None else self.app_id is None)
        self.default_app_id      = (default_app_id or self.app_id or "").strip() or None
        self.launch_on_open      = launch_on_open
        self.open_after_create   = open_after_create
        self._active_tool_app_id: Optional[str] = self.app_id
        self._tool_locked        = self.app_id is not None
        self._app_color_map: dict[str, str] = {}
        self._setup_ui()
        self.refresh()

    def _build_color_map(self) -> None:
        self._app_color_map = {
            m.app_id: _tool_color(i)
            for i, m in enumerate(self.backend.list_apps())
        }

    def _color_for_app(self, app_id: str) -> str:
        return self._app_color_map.get(app_id, "#4e95ff")

    def _manifest_name(self, app_id: str) -> str:
        m = self.backend.get_app_manifest(app_id)
        return m.name if m else (app_id or "Unknown")

    def _load_all_from_db(self) -> List[ProjectItem]:
        total = max(1, int(self.backend.get_total_projects()))
        return [
            ProjectItem(
                id           = str(p.id),
                name         = p.name,
                description  = p.description or "",
                path         = str(p.path),
                last_modified= p.updated_at.strftime("%d/%m/%Y %H:%M"),
                app_id       = (getattr(p, "app_id", "") or "").strip(),
                favorite     = bool(p.favorite),
                language     = self._manifest_name(p.app_id),
                color        = self._color_for_app((getattr(p, "app_id", "") or "").strip()),
                tags         = self.backend.parse_tags(p.tags),
            )
            for p in self.backend.list_projects(1, total)
        ]

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Hero
        hero = QFrame(self)
        hero.setProperty("surface", "hero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(20, 18, 20, 18)
        ey = QLabel("Tools and Projects", hero)
        ey.setProperty("role", "eyebrow")
        hl.addWidget(ey)
        tr = QHBoxLayout()
        ti = QLabel(self.header_title, hero)
        ti.setProperty("role", "headline")
        tr.addWidget(ti)
        tr.addStretch(1)
        self.scope_badge = QLabel("All tools", hero)
        self.scope_badge.setProperty("role", "badge")
        tr.addWidget(self.scope_badge)
        hl.addLayout(tr)
        self.hint_label = QLabel(self.hint_text, hero)
        self.hint_label.setProperty("role", "muted")
        self.hint_label.setWordWrap(True)
        hl.addWidget(self.hint_label)
        layout.addWidget(hero)

        # Action row
        ar = QHBoxLayout()
        ar.setSpacing(8)
        self.new_btn = QPushButton("＋  New project", self)
        self.new_btn.setProperty("primary", "true")
        self.new_btn.clicked.connect(self.on_create_project)
        ar.addWidget(self.new_btn)
        self.refresh_btn = QPushButton("↻  Refresh", self)
        self.refresh_btn.clicked.connect(self.refresh)
        ar.addWidget(self.refresh_btn)
        ar.addStretch(1)
        self._stats_btn = QPushButton("◫  Stats", self)
        self._stats_btn.clicked.connect(
            lambda: StatsDialog(self.project_tree.model.all_visible(), self).exec())
        ar.addWidget(self._stats_btn)
        layout.addLayout(ar)

        # Browser card
        browser_card = QFrame(self)
        browser_card.setProperty("surface", "browser")
        bl = QVBoxLayout(browser_card)
        bl.setContentsMargins(14, 14, 14, 14)
        self.project_tree = ProjectTreeWidget(self)
        self.project_tree.project_selected.connect(self._on_project_selected)
        self.project_tree.project_opened.connect(self._on_project_opened)
        self.project_tree.favorite_toggled.connect(self._on_favorite_toggled)
        self.project_tree.edit_requested.connect(self._on_edit)
        self.project_tree.delete_requested.connect(self._on_delete)
        self.project_tree.export_requested.connect(
            lambda pl: QMessageBox.information(
                self,
                "Export",
                f"Export is not implemented yet. Selected: {len(pl)}",
            )
        )
        self.project_tree.stats_requested.connect(
            lambda pl: StatsDialog(pl, self).exec())
        bl.addWidget(self.project_tree)
        layout.addWidget(browser_card, 1)

    # ── Refresh / scope ───────────────────────────────────────────

    def refresh(self) -> None:
        self._build_color_map()
        self.project_tree.load(self._load_all_from_db())
        self.project_tree.set_scope(self._active_tool_app_id)
        self.projects_changed.emit()

    def force_repaint(self) -> None:
        self.project_tree.viewport().update()

    def get_total_projects(self) -> int:
        return len(self.project_tree.model.all_visible())

    def get_projects_paginated(self, page: int, items_per_page: int) -> list[ProjectItem]:
        visible = self.project_tree.model.all_visible()
        start = max(0, (page - 1) * items_per_page)
        stop = start + max(1, items_per_page)
        return visible[start:stop]

    def set_tool_scope(self, app_id: Optional[str], *, locked: bool | None = None) -> None:
        normalized = (app_id or "").strip() or None
        self._active_tool_app_id = normalized
        if locked is not None:
            self._tool_locked = bool(locked)
        effective = self.header_title if normalized is None else self._manifest_name(normalized)
        self.scope_badge.setText("All tools" if normalized is None else effective)
        self.hint_label.setText(
            self.hint_text if normalized is None
            else (
                f"Browse and open projects for '{effective}'. "
                "Project creation will be scoped to this tool."
            )
        )
        self.project_tree.set_scope(normalized)

    def project_counts_by_app(self) -> dict[str, int]:
        return self.project_tree.counts_by_app()

    # ── Slots ─────────────────────────────────────────────────────

    def _on_project_selected(self, project: ProjectItem) -> None:
        w = self.window()
        if hasattr(w, "statusBar"):
            w.statusBar().showMessage(f"Selected: {project.name}", 3000)

    def _on_project_opened(self, project: ProjectItem) -> None:
        if self.launch_on_open:
            try:
                process = self.backend.launch_project(project.id)
            except Exception as exc:
                QMessageBox.critical(self, "Open project", f"Could not launch the app:\n{exc}")
                return
            if process.poll() is not None:
                QMessageBox.critical(
                    self,
                    "Open project",
                    "The app exited before initialization.",
                )
                return
        self.project_requested.emit(str(project.id))

    def _on_favorite_toggled(self, project: ProjectItem) -> None:
        self.backend.toggle_favorite([project.id])
        self.refresh()

    def _on_edit(self, project: ProjectItem) -> None:
        raw  = self.backend.get_project(project.id)
        apps = self._available_apps_for_dialog()
        dlg  = ProjectFormDialog(
            apps=apps, mode="edit",
            initial_data={"name": raw.name, "path": raw.path,
                          "description": raw.description, "tags": raw.tags,
                          "app_id": raw.app_id},
            allow_app_selection=self._dialog_allows_app_selection(), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.get_data()
        m    = self.backend.get_app_manifest(data["app_id"])
        try:
            self.backend.update_project(
                project_id=raw.id, name=data["name"], folder=data["path"],
                description=data["description"], tags=data["tags"], app_id=data["app_id"],
                scope=m.scope_id if m else raw.scope)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Edit project", f"Could not update the project:\n{exc}")

    def _on_delete(self, projects: list) -> None:
        if not projects:
            return
        reply = QMessageBox.question(
            self, "Delete projects",
            f"{len(projects)} project(s) and their folders will be deleted. This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # Per-project deletion runs in the GUI thread with QProgressDialog;
        # this is sufficient for normal project counts. Move it to QThread if
        # deleting hundreds of large folders causes noticeable UI blocking.
        progress = QProgressDialog(
            "Deleting projects…", None, 0, len(projects), self)
        progress.setWindowTitle("Delete projects")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setValue(0)
        # Force it visible now: minimumDuration alone can skip the dialog when the
        # deletes are fast, so it never appeared for the user.
        progress.show()
        QApplication.processEvents()

        errors: list[tuple[str, Exception]] = []
        for i, p in enumerate(projects):
            progress.setLabelText(f"Deleting '{p.name}'…")
            QApplication.processEvents()
            try:
                self.backend.delete_projects([p.id], delete_files=True)
            except Exception as exc:
                errors.append((p.name, exc))
            progress.setValue(i + 1)
            QApplication.processEvents()
        progress.close()

        self.refresh()
        if errors:
            detail = "\n".join(f"• {name}: {exc}" for name, exc in errors)
            QMessageBox.critical(
                self, "Delete projects",
                f"Could not delete {len(errors)} of {len(projects)} project(s):\n{detail}")

    def on_create_project(self) -> None:
        apps = self._available_apps_for_dialog()
        if not apps:
            QMessageBox.critical(self, "New project", "No registered apps are available.")
            return
        dlg = ProjectFormDialog(
            apps=apps, mode="create",
            initial_data={"path": str(Path.home()/"molsuite_projects"),
                          "app_id": self._active_tool_app_id or apps[0].app_id},
            allow_app_selection=self._dialog_allows_app_selection(), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        fd = dlg.get_data()
        try:
            folder = fd["path"].expanduser().resolve()
            name   = fd["name"].strip()
            if folder.name != name:
                folder = folder / name
            ctx = self.backend.create_project(
                name=name, folder=folder, description=fd["description"],
                tags=fd["tags"], app_id=fd["app_id"])
            self.project_created.emit(str(ctx.id))
            self.refresh()
            if self.open_after_create:
                self.project_requested.emit(str(ctx.id))
        except Exception as exc:
            QMessageBox.critical(self, "Create project", f"Could not create the project:\n{exc}")

    def _available_apps_for_dialog(self) -> list:
        apps = self.backend.list_apps()
        if self._tool_locked and self._active_tool_app_id:
            return [a for a in apps if a.app_id == self._active_tool_app_id]
        return apps

    def _dialog_allows_app_selection(self) -> bool:
        return self.allow_app_selection and not self._tool_locked


# ── ToolTreeDelegate (sidebar) ────────────────────────────────────────────────

class ToolTreeDelegate(QStyledItemDelegate):
    _ICON_W = 36
    _ICON_H = 36
    _ITEM_H = 54
    _PAD_L  = 10
    _GAP    = 12
    _PAD_R  = 10

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        color_hex: str | None = index.data(Qt.UserRole + 1)
        count: int | None     = index.data(Qt.UserRole + 2)
        has_update = bool(index.data(Qt.UserRole + 3))
        text: str             = (index.data(Qt.DisplayRole) or "").strip()
        is_sep     = not color_hex and count is None
        is_sel     = bool(option.state & QStyle.State_Selected)
        is_hover   = bool(option.state & QStyle.State_MouseOver)
        is_disabled = not bool(index.flags() & Qt.ItemIsEnabled)
        r = option.rect

        if is_sep or is_disabled:
            painter.setPen(QPen(QColor(200, 180, 240, 70)))
            f = painter.font()
            f.setPointSize(9)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(r.adjusted(self._PAD_L, 0, -self._PAD_R, 0),
                             Qt.AlignVCenter | Qt.AlignLeft, text.upper())
            painter.restore()
            return

        card = r.adjusted(4, 3, -4, -3)
        path = QPainterPath()
        path.addRoundedRect(card.x(), card.y(), card.width(), card.height(), 10, 10)
        if is_sel:
            painter.setBrush(QBrush(QColor(103,58,183,55)))
            painter.setPen(QPen(QColor(103,58,183,80),1))
        elif is_hover:
            painter.setBrush(QBrush(QColor(255,255,255,12)))
            painter.setPen(Qt.NoPen)
        else:
            painter.setBrush(QBrush(QColor(255,255,255,5)))
            painter.setPen(QPen(QColor(255,255,255,10),1))
        painter.drawPath(path)

        cy = r.center().y()
        ix = r.x() + self._PAD_L
        iy = cy - self._ICON_H//2
        icon_rect = QRect(ix, iy, self._ICON_W, self._ICON_H)

        if color_hex:
            base = QColor(color_hex)
            painter.setBrush(QBrush(base.lighter(115)))
            painter.setPen(QPen(base.darker(120),1))
            painter.drawRoundedRect(icon_rect, 9, 9)
            dr = 5
            painter.setBrush(QBrush(QColor(255,255,255,200)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(icon_rect.right()-dr-1, icon_rect.bottom()-dr-1, dr, dr)
            if has_update:
                painter.setBrush(QBrush(QColor("#ffb347")))
                painter.setPen(QPen(QColor("#ffd59b"), 1))
                painter.drawEllipse(icon_rect.right() - 11, icon_rect.y() + 2, 9, 9)
            painter.setPen(QPen(QColor(255,255,255,240)))
            f = painter.font()
            f.setPointSize(13)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(icon_rect.adjusted(0,-3,0,-3), Qt.AlignCenter, text[:1].upper())
        else:
            sq=7
            gap=3
            colors=["#4e95ff","#a259ff","#43d9ad","#ffb347"]
            pos=[(0,0),(1,0),(0,1),(1,1)]
            ox=icon_rect.x()+(self._ICON_W-(sq*2+gap))//2
            oy=icon_rect.y()+(self._ICON_H-(sq*2+gap))//2
            painter.setPen(Qt.NoPen)
            for (c,row), col in zip(pos, colors):
                painter.setBrush(QBrush(QColor(col)))
                painter.drawRoundedRect(ox+c*(sq+gap), oy+row*(sq+gap), sq, sq, 2, 2)

        tx = ix + self._ICON_W + self._GAP
        badge_w = max(28, len(str(count))*8+14) if count is not None else 28
        text_max_w = r.right() - self._PAD_R - badge_w - 8 - tx

        f = painter.font()
        f.setPointSize(12)
        f.setBold(is_sel)
        painter.setFont(f)
        painter.setPen(QPen(QColor(235,228,245,230 if is_sel else 185)))
        painter.drawText(QRect(tx, r.y()+8, text_max_w, 20), Qt.AlignLeft|Qt.AlignVCenter, text)

        sub = ("All tools" if not color_hex
               else f"{count} project{'s' if count!=1 else ''}" if count is not None else "")
        if sub:
            f2 = painter.font()
            f2.setPointSize(10)
            f2.setBold(False)
            painter.setFont(f2)
            painter.setPen(QPen(QColor(200,180,240,100 if is_sel else 70)))
            painter.drawText(QRect(tx, r.y()+30, text_max_w, 16), Qt.AlignLeft|Qt.AlignVCenter, sub)

        if count is not None:
            bx=r.right()-self._PAD_R-badge_w
            by=cy-11
            br=QRect(bx,by,badge_w,22)
            painter.setBrush(QBrush(QColor(103,58,183,55 if is_sel else 30)))
            painter.setPen(QPen(QColor(103,58,183,100 if is_sel else 55),1))
            painter.drawRoundedRect(br,999,999)
            f3=painter.font()
            f3.setPointSize(10)
            f3.setBold(False)
            painter.setFont(f3)
            painter.setPen(QPen(QColor(162,130,230,200 if is_sel else 150)))
            painter.drawText(br, Qt.AlignCenter, str(count))
        painter.restore()

    def sizeHint(self, option, index):
        if not index.data(Qt.UserRole+1) and index.data(Qt.UserRole+2) is None:
            return QSize(option.rect.width(), 28)
        return QSize(option.rect.width(), self._ITEM_H)


# ── ToolsAndProjectsTab ───────────────────────────────────────────────────────

class ToolsAndProjectsTab(QWidget):
    project_requested = Signal(str)
    project_created   = Signal(str)

    def __init__(self, *, panel: ProjectBrowserPanel,
                 backend: ProjectCatalogBackend,
                 locked_app_id: str | None = None, parent=None):
        super().__init__(parent)
        self.panel         = panel
        self.backend       = backend
        self.locked_app_id = (locked_app_id or "").strip() or None
        self._tool_items: dict[str | None, QTreeWidgetItem] = {}
        self._setup_ui()
        self._populate_tree()
        self.panel.projects_changed.connect(self._refresh_tree_badges)
        self.panel.project_requested.connect(self.project_requested)
        self.panel.project_created.connect(self.project_created)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)

        sidebar = QFrame(self)
        sidebar.setProperty("surface","sidebar")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(18,20,18,18)
        sl.setSpacing(6)
        ey = QLabel("Workspace", sidebar)
        ey.setProperty("role","eyebrow")
        sl.addWidget(ey)
        he = QLabel("Tools and projects", sidebar)
        he.setProperty("role","sidebarTitle")
        sl.addWidget(he)
        inf = QLabel("Select a tool to scope the project catalog.", sidebar)
        inf.setProperty("role","muted")
        inf.setWordWrap(True)
        sl.addWidget(inf)
        sep = QFrame(sidebar)
        sep.setProperty("role","separator")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sl.addSpacing(8)
        sl.addWidget(sep)
        sl.addSpacing(4)
        self.tools_tree = QTreeWidget(sidebar)
        self.tools_tree.setProperty("nav","tools")
        self.tools_tree.setHeaderHidden(True)
        self.tools_tree.setIndentation(0)
        self.tools_tree.setItemDelegate(ToolTreeDelegate(self.tools_tree))
        self.tools_tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        sl.addWidget(self.tools_tree, 1)
        splitter.addWidget(sidebar)

        right = QFrame(self)
        right.setProperty("surface","tab")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18,18,18,18)
        rl.addWidget(self.panel)
        splitter.addWidget(right)
        splitter.setSizes([320, 860])

    def _populate_tree(self):
        self.tools_tree.clear()
        self._tool_items.clear()
        total_projects = sum(self.panel.project_counts_by_app().values())
        all_item = QTreeWidgetItem(["  All tools"])
        all_item.setData(0, Qt.UserRole, "")
        all_item.setData(0, Qt.UserRole + 2, total_projects)
        all_item.setData(0, Qt.UserRole + 3, self._count_updates() > 0)
        self.tools_tree.addTopLevelItem(all_item)
        self._tool_items[None] = all_item
        sep_item = QTreeWidgetItem(["  Installed"])
        sep_item.setFlags(sep_item.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled)
        self.tools_tree.addTopLevelItem(sep_item)
        for idx, m in enumerate(self.backend.list_apps()):
            count = self.panel.project_counts_by_app().get(m.app_id, 0)
            item  = QTreeWidgetItem([f"  {m.name}"])
            item.setData(0, Qt.UserRole,     m.app_id)
            item.setData(0, Qt.UserRole + 1, _tool_color(idx))
            item.setData(0, Qt.UserRole + 2, count)
            item.setData(0, Qt.UserRole + 3, self._tool_has_update(m))
            item.setToolTip(0, m.description or m.app_id)
            if self.locked_app_id and m.app_id != self.locked_app_id:
                item.setDisabled(True)
            self.tools_tree.addTopLevelItem(item)
            self._tool_items[m.app_id] = item
        target = (self._tool_items.get(self.locked_app_id or self.panel._active_tool_app_id)
                  or self._tool_items.get(None))
        if target:
            self.tools_tree.setCurrentItem(target)

    def _refresh_tree_badges(self):
        counts = self.panel.project_counts_by_app()
        all_item = self._tool_items.get(None)
        if all_item:
            all_item.setData(0, Qt.UserRole + 2, sum(counts.values()))
            all_item.setData(0, Qt.UserRole + 3, self._count_updates() > 0)
        for m in self.backend.list_apps():
            item = self._tool_items.get(m.app_id)
            if item:
                item.setText(0, f"  {m.name}")
                item.setData(0, Qt.UserRole + 2, counts.get(m.app_id, 0))
                item.setData(0, Qt.UserRole + 3, self._tool_has_update(m))

    def _on_tree_selection_changed(self):
        item = self.tools_tree.currentItem()
        if not item: return
        raw = str(item.data(0, Qt.UserRole) or "").strip() or None
        self.panel.set_tool_scope(raw, locked=self.locked_app_id is not None)

    def _tool_has_update(self, manifest) -> bool:
        release = _tool_update_demo(manifest.app_id)
        latest_version = str(release.get("latest_version") or "").strip()
        return bool(latest_version and latest_version != manifest.version)

    def _count_updates(self) -> int:
        return sum(1 for manifest in self.backend.list_apps() if self._tool_has_update(manifest))


# ── MolSuiteSettingsPanel ─────────────────────────────────────────────────────

class MolSuiteSettingsPanel(QWidget):
    def __init__(self, *, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self._setup_ui()
        self.reload_from_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(12)
        hero = QFrame(self)
        hero.setProperty("surface","hero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(20,18,20,18)
        e = QLabel("MolSuite Settings", hero)
        e.setProperty("role","eyebrow")
        hl.addWidget(e)
        h = QLabel("Executors, resources and runtime defaults", hero)
        h.setProperty("role","headline")
        hl.addWidget(h)
        t = QLabel("Use this panel to edit global MolSuite settings.", hero)
        t.setProperty("role","muted")
        t.setWordWrap(True)
        hl.addWidget(t)
        layout.addWidget(hero)
        self.status_label = QLabel("", self)
        self.status_label.setProperty("role","muted")
        layout.addWidget(self.status_label)
        body = QSplitter(Qt.Horizontal, self)
        body.setChildrenCollapsible(False)
        layout.addWidget(body, 1)

        # Left column
        lc = QWidget(self)
        ll = QVBoxLayout(lc)
        ll.setContentsMargins(0,0,0,0)
        ll.setSpacing(12)
        self.paths_card = QFrame(self)
        self.paths_card.setProperty("surface","panel")
        pl = QVBoxLayout(self.paths_card)
        pl.setContentsMargins(16,16,16,16)
        pt = QLabel("Storage", self.paths_card)
        pt.setProperty("role","headline")
        pt.setStyleSheet("font-size:18px;")
        pl.addWidget(pt)
        pf = QFormLayout()
        self.projects_db_input = QLineEdit(self.paths_card)
        pdr = QWidget(self.paths_card)
        pdl = QHBoxLayout(pdr)
        pdl.setContentsMargins(0,0,0,0)
        pdl.addWidget(self.projects_db_input)
        bp = QPushButton("Browse", pdr)
        bp.clicked.connect(lambda: self._choose_path(self.projects_db_input))
        pdl.addWidget(bp)
        pf.addRow("Projects DB", pdr)
        self.executor_db_input = QLineEdit(self.paths_card)
        edr = QWidget(self.paths_card)
        edl = QHBoxLayout(edr)
        edl.setContentsMargins(0,0,0,0)
        edl.addWidget(self.executor_db_input)
        be = QPushButton("Browse", edr)
        be.clicked.connect(lambda: self._choose_path(self.executor_db_input))
        edl.addWidget(be)
        pf.addRow("Executor DB", edr)
        pl.addLayout(pf)
        ll.addWidget(self.paths_card)
        self.runtime_card = QFrame(self)
        self.runtime_card.setProperty("surface","panel")
        rl = QVBoxLayout(self.runtime_card)
        rl.setContentsMargins(16,16,16,16)
        rt = QLabel("Runtime defaults", self.runtime_card)
        rt.setProperty("role","headline")
        rt.setStyleSheet("font-size:18px;")
        rl.addWidget(rt)
        rf = QFormLayout()
        self.poll_interval_spin = QDoubleSpinBox(self.runtime_card)
        self.poll_interval_spin.setRange(0.01,30.0)
        self.poll_interval_spin.setDecimals(2)
        rf.addRow("Poll interval", self.poll_interval_spin)
        self.general_log_level_combo = QComboBox(self.runtime_card)
        self.general_log_level_combo.addItems(["DEBUG","INFO","WARNING","ERROR","CRITICAL"])
        rf.addRow("General log", self.general_log_level_combo)
        self.app_log_level_combo = QComboBox(self.runtime_card)
        self.app_log_level_combo.addItems(["DEBUG","INFO","WARNING","ERROR","CRITICAL"])
        rf.addRow("App log", self.app_log_level_combo)
        self.executor_log_level_combo = QComboBox(self.runtime_card)
        self.executor_log_level_combo.addItems(["DEBUG","INFO","WARNING","ERROR","CRITICAL"])
        rf.addRow("Executor log", self.executor_log_level_combo)
        rl.addLayout(rf)
        ll.addWidget(self.runtime_card)
        ll.addStretch(1)
        body.addWidget(lc)

        # Right column
        rc = QWidget(self)
        rr = QVBoxLayout(rc)
        rr.setContentsMargins(0,0,0,0)
        rr.setSpacing(12)
        self.resources_card = QFrame(self)
        self.resources_card.setProperty("surface","panel")
        resl = QVBoxLayout(self.resources_card)
        resl.setContentsMargins(16,16,16,16)
        rest = QLabel("Local resources", self.resources_card)
        rest.setProperty("role","headline")
        rest.setStyleSheet("font-size:18px;")
        resl.addWidget(rest)
        sg = QGridLayout()
        self.cpus_tile=StatTile("CPUs",self.resources_card)
        self.gpus_tile=StatTile("GPUs",self.resources_card)
        self.threads_tile=StatTile("Max threads",self.resources_card)
        self.processes_tile=StatTile("Max processes",self.resources_card)
        sg.addWidget(self.cpus_tile,0,0)
        sg.addWidget(self.gpus_tile,0,1)
        sg.addWidget(self.threads_tile,1,0)
        sg.addWidget(self.processes_tile,1,1)
        resl.addLayout(sg)
        resf = QFormLayout()
        self.cpus_spin=QSpinBox(self.resources_card)
        self.cpus_spin.setRange(1,512)
        resf.addRow("CPUs",self.cpus_spin)
        self.gpus_spin=QSpinBox(self.resources_card)
        self.gpus_spin.setRange(0,64)
        resf.addRow("GPUs",self.gpus_spin)
        self.max_threads_spin=QSpinBox(self.resources_card)
        self.max_threads_spin.setRange(1,2048)
        resf.addRow("Max threads",self.max_threads_spin)
        self.max_processes_spin=QSpinBox(self.resources_card)
        self.max_processes_spin.setRange(1,512)
        resf.addRow("Max processes",self.max_processes_spin)
        resl.addLayout(resf)
        rr.addWidget(self.resources_card)
        self.workers_card=QFrame(self)
        self.workers_card.setProperty("surface","panel")
        wl=QVBoxLayout(self.workers_card)
        wl.setContentsMargins(16,16,16,16)
        wt=QLabel("Registered workers",self.workers_card)
        wt.setProperty("role","headline")
        wt.setStyleSheet("font-size:18px;")
        wl.addWidget(wt)
        wh=QLabel("Workers available in the global configuration.",self.workers_card)
        wh.setProperty("role","muted")
        wh.setWordWrap(True)
        wl.addWidget(wh)
        self.workers_table=QTableWidget(0,5,self.workers_card)
        self.workers_table.setHorizontalHeaderLabels(["Name","Type","Enabled","CPU","GPU"])
        self.workers_table.verticalHeader().setVisible(False)
        self.workers_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.workers_table.horizontalHeader().setStretchLastSection(True)
        wl.addWidget(self.workers_table)
        rr.addWidget(self.workers_card,1)
        ar=QHBoxLayout()
        ar.addStretch(1)
        self.reload_button=QPushButton("Reload",self)
        self.reload_button.clicked.connect(self.reload_from_settings)
        ar.addWidget(self.reload_button)
        self.save_button=QPushButton("Save global settings",self)
        self.save_button.setProperty("primary","true")
        self.save_button.clicked.connect(self.save_settings)
        ar.addWidget(self.save_button)
        rr.addLayout(ar)
        body.addWidget(rc)
        body.setSizes([440,520])

    def _choose_path(self, le: QLineEdit):
        fn, _ = QFileDialog.getSaveFileName(self,"Select file",le.text().strip() or str(Path.home()),"Database (*.db);;All files (*)")
        if fn: le.setText(fn)

    def reload_from_settings(self):
        self._apply_settings_to_form(self.settings_manager.settings)
        self.status_label.setText("Loaded global MolSuite settings.")

    def _apply_settings_to_form(self, s: Settings):
        self.projects_db_input.setText(str(s.projects_db))
        self.executor_db_input.setText("" if s.executor_db is None else str(s.executor_db))
        self.poll_interval_spin.setValue(float(s.general.poll_interval))
        self.general_log_level_combo.setCurrentText(str(s.general.log_level))
        self.app_log_level_combo.setCurrentText(str(s.logging.app_level))
        self.executor_log_level_combo.setCurrentText(str(s.logging.executor_level))
        lo=s.resources.local
        self.cpus_spin.setValue(int(lo.cpus))
        self.gpus_spin.setValue(int(lo.gpus))
        self.max_threads_spin.setValue(int(lo.max_threads))
        self.max_processes_spin.setValue(int(lo.max_processes))
        self.cpus_tile.set_value(str(lo.cpus))
        self.gpus_tile.set_value(str(lo.gpus))
        self.threads_tile.set_value(str(lo.max_threads))
        self.processes_tile.set_value(str(lo.max_processes))
        workers=s.workers.model_dump(mode="python")
        self.workers_table.setRowCount(len(workers))
        for row,(n,p) in enumerate(sorted(workers.items())):
            self.workers_table.setItem(row,0,QTableWidgetItem(str(n)))
            self.workers_table.setItem(row,1,QTableWidgetItem(str(p.get("type",""))))
            self.workers_table.setItem(row,2,QTableWidgetItem("Yes" if p.get("enabled",True) else "No"))
            self.workers_table.setItem(row,3,QTableWidgetItem(str(p.get("cpus",""))))
            self.workers_table.setItem(row,4,QTableWidgetItem(str(p.get("gpus",""))))
        self.workers_table.resizeColumnsToContents()

    def save_settings(self):
        updates={
            "projects_db": Path(self.projects_db_input.text().strip()).expanduser().resolve(),
            "executor_db": Path(self.executor_db_input.text().strip()).expanduser().resolve() if self.executor_db_input.text().strip() else None,
            "general.poll_interval": float(self.poll_interval_spin.value()),
            "general.log_level": str(self.general_log_level_combo.currentText()),
            "logging.app_level": str(self.app_log_level_combo.currentText()),
            "logging.executor_level": str(self.executor_log_level_combo.currentText()),
            "resources.local.cpus": int(self.cpus_spin.value()),
            "resources.local.gpus": int(self.gpus_spin.value()),
            "resources.local.max_threads": int(self.max_threads_spin.value()),
            "resources.local.max_processes": int(self.max_processes_spin.value()),
        }
        try:
            for k,v in updates.items(): self.settings_manager.update_setting(k,v)
        except Exception as exc:
            QMessageBox.critical(self,"Save settings",f"Could not save settings:\n{exc}")
            self.status_label.setText("Failed to save settings.")
            return
        self.reload_from_settings()
        self.status_label.setText("Global MolSuite settings saved.")


# ── AvailableToolsTab ─────────────────────────────────────────────────────────

class AvailableToolsTab(QWidget):
    updates_changed = Signal(int)

    def __init__(self, *, backend: ProjectCatalogBackend,
                 current_app_id: str | None = None, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.current_app_id = (current_app_id or "").strip() or None
        self._setup_ui()
        self.reload()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(12)
        hero=QFrame(self)
        hero.setProperty("surface","hero")
        hl=QVBoxLayout(hero)
        hl.setContentsMargins(20,18,20,18)
        QLabel("Available Tools",hero).setProperty("role","eyebrow")
        hl.addWidget(QLabel("Available Tools",hero))
        t=QLabel("Registered and attachable tools",hero)
        t.setProperty("role","headline")
        hl.addWidget(t)
        h=QLabel("This view summarizes the tools available to MolSuite and can show updates for the selected tool.",hero)
        h.setProperty("role","muted")
        h.setWordWrap(True)
        hl.addWidget(h)
        layout.addWidget(hero)
        card=QFrame(self)
        card.setProperty("surface","panel")
        cl=QVBoxLayout(card)
        cl.setContentsMargins(16,16,16,16)
        ar=QHBoxLayout()
        ar.addStretch(1)
        rb=QPushButton("Refresh",self)
        rb.clicked.connect(self.reload)
        ar.addWidget(rb)
        cl.addLayout(ar)
        body = QSplitter(Qt.Horizontal, card)
        body.setChildrenCollapsible(False)
        cl.addWidget(body, 1)
        self.tools_table=QTableWidget(0,6,self)
        self.tools_table.setHorizontalHeaderLabels(["Tool","App ID","Version","Status","Projects","Source"])
        self.tools_table.verticalHeader().setVisible(False)
        self.tools_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tools_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tools_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tools_table.setAlternatingRowColors(False)
        self.tools_table.horizontalHeader().setStretchLastSection(True)
        self.tools_table.itemSelectionChanged.connect(self._sync_detail_from_selection)
        body.addWidget(self.tools_table)

        detail = QFrame(card)
        detail.setProperty("surface","browser")
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(18,18,18,18)
        dl.setSpacing(10)
        d_ey = QLabel("What's New", detail)
        d_ey.setProperty("role", "eyebrow")
        dl.addWidget(d_ey)
        self.detail_title = QLabel("Select a tool", detail)
        self.detail_title.setProperty("role", "headline")
        dl.addWidget(self.detail_title)
        top = QHBoxLayout()
        self.detail_status = QLabel("Up to date", detail)
        self.detail_status.setProperty("role", "badge")
        top.addWidget(self.detail_status)
        top.addStretch(1)
        self.detail_versions = QLabel("", detail)
        self.detail_versions.setProperty("role", "muted")
        top.addWidget(self.detail_versions)
        dl.addLayout(top)
        self.detail_summary = QLabel("", detail)
        self.detail_summary.setProperty("role", "muted")
        self.detail_summary.setWordWrap(True)
        dl.addWidget(self.detail_summary)
        self.detail_notes = QTextEdit(detail)
        self.detail_notes.setReadOnly(True)
        self.detail_notes.setMinimumHeight(180)
        dl.addWidget(self.detail_notes, 1)
        actions = QHBoxLayout()
        self.detail_action = QPushButton("Install update (demo)", detail)
        self.detail_action.setEnabled(False)
        actions.addWidget(self.detail_action)
        actions.addStretch(1)
        dl.addLayout(actions)
        body.addWidget(detail)
        body.setSizes([700, 420])
        self.note_label=QLabel("",self)
        self.note_label.setProperty("role","muted")
        self.note_label.setWordWrap(True)
        cl.addWidget(self.note_label)
        layout.addWidget(card,1)

    def reload(self):
        manifests=self.backend.list_apps()
        counts: dict[str,int]={}
        total=max(1,int(self.backend.get_total_projects()))
        for p in self.backend.list_projects(1,total):
            aid=(getattr(p,"app_id","") or "").strip()
            if aid: counts[aid]=counts.get(aid,0)+1
        self.tools_table.setRowCount(len(manifests))
        updates_count = 0
        for row,m in enumerate(manifests):
            release = _tool_update_demo(m.app_id)
            latest_version = str(release.get("latest_version") or "").strip()
            has_update = bool(latest_version and latest_version != m.version)
            if has_update:
                updates_count += 1
            if has_update:
                status = "Update available"
            else:
                status="Current tool" if m.app_id==self.current_app_id else ("Attached from source" if m.source_root else "Installed")
            self.tools_table.setItem(row,0,QTableWidgetItem(m.name))
            self.tools_table.setItem(row,1,QTableWidgetItem(m.app_id))
            self.tools_table.setItem(row,2,QTableWidgetItem(m.version))
            self.tools_table.setItem(row,3,QTableWidgetItem(status))
            self.tools_table.setItem(row,4,QTableWidgetItem(str(counts.get(m.app_id,0))))
            self.tools_table.setItem(row,5,QTableWidgetItem("-" if not m.source_root else str(m.source_root)))
        self.tools_table.resizeColumnsToContents()
        if manifests:
            self.tools_table.selectRow(0)
            self._sync_detail_from_selection()
        else:
            self._set_detail_empty()
        self.note_label.setText(
            "Demo UI: the right panel can show updates and release notes for the selected tool. "
            "If an app does not appear here, its manifest.py is not visible to the registry."
        )
        self.updates_changed.emit(updates_count)

    def _set_detail_empty(self) -> None:
        self.detail_title.setText("No tools available")
        self.detail_status.setText("No data")
        self.detail_versions.setText("")
        self.detail_summary.setText("No registered tools are visible for the current MolSuite workspace.")
        self.detail_notes.setPlainText("")

    def _count_updates(self) -> int:
        count = 0
        for manifest in self.backend.list_apps():
            release = _tool_update_demo(manifest.app_id)
            latest_version = str(release.get("latest_version") or "").strip()
            if latest_version and latest_version != manifest.version:
                count += 1
        return count

    def _sync_detail_from_selection(self) -> None:
        row = self.tools_table.currentRow()
        if row < 0:
            self._set_detail_empty()
            return
        app_id_item = self.tools_table.item(row, 1)
        name_item = self.tools_table.item(row, 0)
        version_item = self.tools_table.item(row, 2)
        if not app_id_item or not name_item or not version_item:
            self._set_detail_empty()
            return
        app_id = app_id_item.text().strip()
        current_version = version_item.text().strip()
        release = _tool_update_demo(app_id)
        latest_version = str(release.get("latest_version") or current_version).strip() or current_version
        has_update = bool(latest_version and latest_version != current_version)
        self.detail_title.setText(name_item.text().strip())
        self.detail_status.setText("Update available" if has_update else "Up to date")
        self.detail_versions.setText(f"{current_version} installed  ->  {latest_version} latest")
        self.detail_summary.setText(str(release.get("summary") or ""))
        headline = str(release.get("headline") or "What's new")
        notes = [str(item).strip() for item in release.get("notes") or [] if str(item).strip()]
        body = [headline, ""]
        if notes:
            body.extend(f"- {item}" for item in notes)
        else:
            body.append("- No release notes available.")
        self.detail_notes.setPlainText("\n".join(body))


# ── ProjectBrowserWindow ──────────────────────────────────────────────────────

class ProjectBrowserWindow(QMainWindow):
    def __init__(self, *, app_id: str | None = None,
                 window_title: str | None = None, header_title: str | None = None,
                 hint_text: str | None = None, allow_app_selection: bool | None = None,
                 close_on_launch: bool = True, _backend: ProjectCatalogBackend | None = None):
        super().__init__()
        self.app_id          = (app_id or "").strip() or None
        self.backend         = _backend or ProjectCatalogBackend(app_id_filter=None)
        self.window_title    = window_title or "MolSuite Control Center"
        self.close_on_launch = close_on_launch
        eff_header = header_title or (self.app_id or "MolSuite Projects")
        eff_hint   = hint_text or (
            "Browse registered apps and open each project with its domain runtime."
            if self.app_id is None else f"Browse and open projects for the '{self.app_id}' app.")
        eff_allow  = bool(allow_app_selection) if allow_app_selection is not None else self.app_id is None

        self.setObjectName("ProjectBrowserWindow")
        self.setStyleSheet(_toolbox_shell_stylesheet())

        root = QWidget(self)
        root.setObjectName("ProjectBrowserRoot")
        rl = QVBoxLayout(root)
        rl.setContentsMargins(18,18,18,18)
        rl.setSpacing(14)
        hero=QFrame(root)
        hero.setProperty("surface","hero")
        hl=QVBoxLayout(hero)
        hl.setContentsMargins(22,18,22,18)
        ey=QLabel("MolSuite",hero)
        ey.setProperty("role","eyebrow")
        hl.addWidget(ey)
        ti=QLabel("Tools, projects and runtime settings",hero)
        ti.setProperty("role","headline")
        hl.addWidget(ti)
        su=QLabel(
            "A single interface for browsing registered apps, opening projects in the correct "
            "context, and adjusting global runtime settings.",
            hero,
        )
        su.setProperty("role","muted")
        su.setWordWrap(True)
        hl.addWidget(su)
        rl.addWidget(hero)

        self.panel = ProjectBrowserPanel(
            app_id=self.app_id, header_title=eff_header, hint_text=eff_hint,
            allow_app_selection=eff_allow, default_app_id=self.app_id,
            launch_on_open=True, open_after_create=False, _backend=self.backend, parent=self)
        self.panel.project_requested.connect(self._on_project_requested)

        self.tools_tab = ToolsAndProjectsTab(
            panel=self.panel, backend=self.backend, locked_app_id=self.app_id, parent=self)
        self.tools_tab.project_requested.connect(self._on_project_requested)

        self.settings_panel = MolSuiteSettingsPanel(
            settings_manager=self.backend.catalog.settings_manager, parent=self)
        self.available_tools_panel = AvailableToolsTab(
            backend=self.backend, current_app_id=self.app_id, parent=self)
        self.available_tools_panel.updates_changed.connect(self._update_available_tools_tab_label)

        self.tabs = QTabWidget(root)
        self.tabs.addTab(self.tools_tab, "Tools and Projects")
        self.tabs.addTab(self.available_tools_panel, "Available Tools")
        self.tabs.addTab(self.settings_panel, "MolSuite Settings")
        rl.addWidget(self.tabs, 1)
        self._update_available_tools_tab_label(self.available_tools_panel._count_updates())
        self.setCentralWidget(root)
        self.setWindowTitle(self.window_title)
        self.resize(1320, 860)

    def _on_project_requested(self, _project_id: str):
        if self.close_on_launch:
            QApplication.instance().quit()

    def _update_available_tools_tab_label(self, updates_count: int) -> None:
        label = "Available Tools"
        if updates_count > 0:
            label = f"Available Tools ({updates_count})"
        self.tabs.setTabText(1, label)

    def closeEvent(self, event):
        try: self.backend.shutdown()
        except Exception: pass
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv[1:])
    w = ProjectBrowserWindow()
    w.show()
    sys.exit(app.exec())
