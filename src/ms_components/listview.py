
import hashlib
from dataclasses import dataclass
from dataclasses import field
from typing import List, Optional, Callable, Set, Hashable, Type

from PySide6.QtCore import (Qt, QAbstractListModel, QModelIndex, QEvent, QRect, QSize, Signal)
from PySide6.QtGui import QColor, QPalette
from PySide6.QtGui import (QCursor, QPainter, QFont, QPen, QBrush, QPainterPath, QMouseEvent)
from PySide6.QtWidgets import QApplication, QStyledItemDelegate
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListView,
                               QLineEdit, QLabel,
                               QAbstractItemView, QToolButton, QMenu)

from .pagination import PaginationControl


@dataclass(frozen=True)
class ThemeColors:
    # -- Backgrounds ---------------------------------------------
    bg_base: QColor  # Normal background of each item
    bg_hover: QColor  # Hover
    bg_selected: QColor  # Multi-selection (opaque, no alpha)
    bg_selected_border: QColor  # Left border when selected

    # -- Checkbox ------------------------------------------------
    checkbox_empty_bg: QColor
    checkbox_empty_border: QColor
    checkbox_hover_bg: QColor
    checkbox_hover_border: QColor
    checkbox_checked_bg: QColor  # = primary
    checkbox_check_mark: QColor  # Check-mark colour

    # -- Neutral tags / badges -----------------------------------
    tag_bg: QColor
    tag_text: QColor
    tag_border: QColor

    # -- Text ---------------------------------------------------
    text_primary: QColor
    text_secondary: QColor
    text_muted: QColor
    text_on_primary: QColor

    # -- Accents -------------------------------------------------
    primary: QColor
    primary_light: QColor
    danger: QColor

    # -- Borders -------------------------------------------------
    border_item: QColor  # Row separator
    border_input: QColor  # Input border

    # -- Side indicator ------------------------------------------
    indicator_selected: QColor
    indicator_hover: QColor

    # -- Info publica --------------------------------------------
    is_dark: bool

    # ------------------------------------------------------------
    @classmethod
    def get(cls, widget: Optional[QWidget] = None) -> "ThemeColors":
        # Some widgets can be left holding stale local palettes, so the app's
        # global palette is the source of truth for the active theme.
        app = QApplication.instance()
        theme_mode = ""
        if app is not None:
            palette = app.palette()
            theme_mode = str(app.property("theme_mode") or "").lower()
        elif widget is not None:
            palette = widget.palette()
        else:
            palette = QPalette()

        primary = cls._primary_from_palette(palette)
        if theme_mode in {"dark", "light"}:
            is_dark = theme_mode == "dark"
        else:
            is_dark = cls._detect_dark(palette)

        return (cls._build_dark(palette, primary)
                if is_dark
                else cls._build_light(palette, primary))

    # ── Deteccion ────────────────────────────────────────────────

    @staticmethod
    def _detect_dark(palette: QPalette) -> bool:
        window = palette.color(QPalette.Window)
        window_text = palette.color(QPalette.WindowText)
        if abs(window.lightness() - window_text.lightness()) >= 80:
            return window_text.lightness() > window.lightness()
        return window.lightness() < 128

    @staticmethod
    def _primary_from_palette(palette: QPalette) -> QColor:
        h = palette.color(QPalette.Highlight)
        return h if h.saturation() >= 30 else QColor("#2979ff")

    # ── Construccion tema oscuro ─────────────────────────────────

    @classmethod
    def _build_dark(cls, palette: QPalette, primary: QColor) -> "ThemeColors":
        bg = cls._surface_bg_from_palette(palette)
        text = cls._text_from_palette(palette)

        bg_sel = _blend(bg, primary, 0.15)
        tag_bg = _blend(bg, QColor(255, 255, 255), 0.13)
        cb_border = _blend(bg, QColor(255, 255, 255), 0.30)
        cb_hov_bg = _blend(bg, QColor(255, 255, 255), 0.10)
        cb_hov_bdr = _blend(bg, QColor(255, 255, 255), 0.50)

        return cls(
            bg_base=bg,
            bg_hover=_blend(bg, QColor(255, 255, 255), 0.06),
            bg_selected=bg_sel,
            bg_selected_border=primary,

            checkbox_empty_bg=bg,  # theme background, NOT white
            checkbox_empty_border=cb_border,
            checkbox_hover_bg=cb_hov_bg,
            checkbox_hover_border=cb_hov_bdr,
            checkbox_checked_bg=primary,
            checkbox_check_mark=QColor("#ffffff"),

            tag_bg=tag_bg,
            tag_text=_with_alpha(text, 210),
            tag_border=_blend(bg, QColor(255, 255, 255), 0.20),

            text_primary=text,
            text_secondary=_with_alpha(text, 180),
            text_muted=_with_alpha(text, 110),
            text_on_primary=QColor("#ffffff"),

            primary=primary,
            primary_light=primary.lighter(140),
            danger=QColor("#cf6679"),

            border_item=_blend(bg, QColor(255, 255, 255), 0.09),
            border_input=_blend(bg, QColor(255, 255, 255), 0.25),

            indicator_selected=primary,
            indicator_hover=_with_alpha(primary, 130),

            is_dark=True,
        )

    @classmethod
    def _build_light(cls, palette: QPalette, primary: QColor) -> "ThemeColors":
        bg = cls._surface_bg_from_palette(palette)
        text = cls._text_from_palette(palette)
        if bg.lightness() < 140:
            bg = QColor("#f3f5f7")
        if text.lightness() > 170:
            text = QColor("#1f2328")
        bg_sel = _blend(bg, primary, 0.10)

        return cls(
            bg_base=bg,
            bg_hover=_blend(bg, QColor(0, 0, 0), 0.04),
            bg_selected=_blend(bg, primary, 0.10),
            bg_selected_border=primary,

            checkbox_empty_bg=bg,
            checkbox_empty_border=QColor("#adb5bd"),
            checkbox_hover_bg=_blend(bg, QColor(0, 0, 0), 0.06),
            checkbox_hover_border=QColor("#6c757d"),
            checkbox_checked_bg=primary,
            checkbox_check_mark=QColor("#ffffff"),

            tag_bg=_blend(bg, QColor(0, 0, 0), 0.08),
            tag_text=_with_alpha(text, 220),
            tag_border=_blend(bg, QColor(0, 0, 0), 0.15),

            text_primary=text,
            text_secondary=_with_alpha(text, 180),
            text_muted=_with_alpha(text, 120),
            text_on_primary=QColor("#ffffff"),

            primary=primary,
            primary_light=primary.lighter(170),
            danger=QColor("#dc3545"),

            border_item=_blend(bg, QColor(0, 0, 0), 0.10),
            border_input=_blend(bg, QColor(0, 0, 0), 0.15),

            indicator_selected=primary,
            indicator_hover=_with_alpha(primary, 120),

            is_dark=False,
        )

    @staticmethod
    def _surface_bg_from_palette(palette: QPalette) -> QColor:
        base = palette.color(QPalette.Base)
        window = palette.color(QPalette.Window)
        if abs(base.lightness() - window.lightness()) > 90:
            return window
        return base

    @staticmethod
    def _text_from_palette(palette: QPalette) -> QColor:
        base = palette.color(QPalette.Base)
        window = palette.color(QPalette.Window)
        if abs(base.lightness() - window.lightness()) > 90:
            return palette.color(QPalette.WindowText)
        return palette.color(QPalette.Text)


# -- Utilidades --------------------------------------------------

def _blend(a: QColor, b: QColor, t: float) -> QColor:
    """Linear blend. t=0->a, t=1->b. Result is always opaque."""

    def ch(ca, cb):
        return max(0, min(255, int(ca + (cb - ca) * t)))

    return QColor(
        ch(a.red(), b.red()),
        ch(a.green(), b.green()),
        ch(a.blue(), b.blue()),
    )


def _with_alpha(color: QColor, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(max(0, min(255, alpha)))
    return c


@dataclass
class ProjectItem:
    """Data model for a project."""
    id: Hashable
    name: str
    description: str
    path: str
    last_modified: str
    favorite: bool = False
    tags: List[str] = field(default_factory=list)
    language: Optional[str] = None
    color: Optional[str] = None


class ProjectListModel(QAbstractListModel):
    """Model for the project list, with multi-selection support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._projects: List[ProjectItem] = []
        self._selected_ids: Set[Hashable] = set()
        self._active_id: Optional[Hashable] = None

    def rowCount(self, parent=QModelIndex()):
        return len(self._projects)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._projects):
            return None
        project = self._projects[index.row()]
        if role == Qt.DisplayRole:
            return project
        if role == Qt.UserRole + 1:
            return project.id in self._selected_ids
        if role == Qt.UserRole + 2:
            return project.id == self._active_id
        return None

    def set_projects(self, projects: List[ProjectItem]):
        """Set the project list."""
        self.beginResetModel()
        self._projects = projects
        current_ids = {p.id for p in projects}
        self._selected_ids &= current_ids
        if self._active_id not in current_ids:
            self._active_id = None
        self.endResetModel()

    def get_project(self, row: int) -> Optional[ProjectItem]:
        """Return the project at the given index."""
        if 0 <= row < len(self._projects):
            return self._projects[row]
        return None

    def toggle_selection(self, project_id: Hashable):
        """Toggle a project's selection."""
        if project_id in self._selected_ids:
            self._selected_ids.remove(project_id)
        else:
            self._selected_ids.add(project_id)
        self.dataChanged.emit(
            self.index(0), self.index(self.rowCount() - 1)
        )

    def get_selected_count(self) -> int:
        """Return how many projects are selected."""
        return len(self._selected_ids)

    def get_selected_projects(self) -> List[ProjectItem]:
        """Return the list of selected projects."""
        return [p for p in self._projects if p.id in self._selected_ids]

    def set_active_project(self, project_id: Optional[Hashable]):
        self._active_id = project_id
        if self.rowCount() > 0:
            self.dataChanged.emit(
                self.index(0), self.index(self.rowCount() - 1)
            )

    def get_active_project(self) -> Optional[ProjectItem]:
        if self._active_id is None:
            return None
        for project in self._projects:
            if project.id == self._active_id:
                return project
        return None

    def clear_selection(self):
        """Clear the whole selection."""
        self._selected_ids.clear()
        if self.rowCount() > 0:
            self.dataChanged.emit(
                self.index(0), self.index(self.rowCount() - 1)
            )

    def select_all(self):
        self._selected_ids = {p.id for p in self._projects}
        if self.rowCount() > 0:
            self.dataChanged.emit(
                self.index(0), self.index(self.rowCount() - 1)
            )

    def are_all_selected(self) -> bool:
        return bool(self._projects) and len(self._selected_ids) == len(self._projects)



# Language brand colours - these ARE fixed (technology identity, not theme)
LANG_COLORS: dict[str, tuple[str, str]] = {
    "Python": ("#3776ab", "#ffffff"),
    "JavaScript": ("#f7df1e", "#111111"),
    "TypeScript": ("#3178c6", "#ffffff"),
    "Java": ("#007396", "#ffffff"),
    "C++": ("#00599c", "#ffffff"),
    "Go": ("#00add8", "#ffffff"),
    "Rust": ("#ce422b", "#ffffff"),
    "Kotlin": ("#7f52ff", "#ffffff"),
    "Swift": ("#f05138", "#ffffff"),
    "Ruby": ("#cc342d", "#ffffff"),
}

AVATAR_COLORS: tuple[str, ...] = (
    "#4e95ff",  # blue
    "#a259ff",  # violet
    "#ff6b6b",  # red
    "#43d9ad",  # teal
    "#ffb347",  # amber
    "#f7768e",  # pink
    "#9ece6a",  # green
    "#7dcfff",  # sky
)


def _avatar_color_for(project: "ProjectItem") -> QColor:
    """
    Return the avatar color for a project.
    Priority: project.color (set by caller per-tool) > hash-based fallback.
    """
    if project.color:
        return QColor(project.color)
    seed = f"{project.id}|{project.name}".encode("utf-8", errors="ignore")
    digest = hashlib.md5(seed).digest()
    return QColor(AVATAR_COLORS[digest[0] % len(AVATAR_COLORS)])


class ProjectItemDelegate(QStyledItemDelegate):
    """
    Theme-adaptive delegate for the project list.

    Features:
    - Every base colour comes from ThemeColors.get() - nothing hardcoded.
    - The avatar uses project.color when set (per-tool colour), otherwise a
      colour derived from the hash of the id/name as a fallback.
    - Inline "Open" and "★" buttons, visible only on hover (hover-reveal).
    - Clicking an inline button emits open_clicked / favorite_clicked.
    - Agnostic: can be subclassed or replaced by an external delegate.
    """

    checkbox_clicked  = Signal(int, object)   # (row, project_id)
    open_clicked      = Signal(object)         # ProjectItem
    favorite_clicked  = Signal(object)         # ProjectItem

    # Inline button geometry (relative to the item rect)
    _BTN_W   = 60    # "Open" button width
    _BTN_H   = 26
    _STAR_W  = 28    # "★" button width
    _BTN_GAP = 6     # gap between buttons
    _BTN_R   = 6     # border-radius
    _PAD_RIGHT = 14  # right margin

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hover_row       = -1
        self.hover_checkbox  = -1
        self.show_checkboxes = False
        self._hover_open     = False   # cursor over the Open button
        self._hover_star     = False   # cursor over the ★ button

    # ── State setters ────────────────────────────────────────────

    def set_hover_row(self, row: int):
        self.hover_row = row

    def set_hover_checkbox(self, row: int):
        self.hover_checkbox = row

    def set_show_checkboxes(self, enabled: bool):
        self.show_checkboxes = enabled

    # ── Geometry ─────────────────────────────────────────────────

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 78)

    def get_checkbox_rect(self, rect: QRect) -> QRect:
        if not self.show_checkboxes:
            return QRect()
        return QRect(rect.left() + 15, rect.top() + (rect.height() - 22) // 2, 22, 22)

    def _get_open_btn_rect(self, rect: QRect) -> QRect:
        """Rect of the 'Open' button within the item rect."""
        x = rect.right() - self._PAD_RIGHT - self._STAR_W - self._BTN_GAP - self._BTN_W
        y = rect.center().y() - self._BTN_H // 2
        return QRect(x, y, self._BTN_W, self._BTN_H)

    def _get_star_btn_rect(self, rect: QRect) -> QRect:
        """Rect of the '★' button within the item rect."""
        x = rect.right() - self._PAD_RIGHT - self._STAR_W
        y = rect.center().y() - self._BTN_H // 2
        return QRect(x, y, self._STAR_W, self._BTN_H)

    # ── Paint ────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        project   = index.data(Qt.DisplayRole)
        is_selected = bool(index.data(Qt.UserRole + 1))
        is_active   = bool(index.data(Qt.UserRole + 2))
        if not project:
            painter.restore()
            return

        rect   = option.rect
        colors = ThemeColors.get()
        is_hovered = self.hover_row == index.row()

        # ── Fondo ────────────────────────────────────────────────
        if is_selected or is_active:
            painter.fillRect(rect, colors.bg_selected)
        elif is_hovered:
            painter.fillRect(rect, colors.bg_hover)
        else:
            painter.fillRect(rect, colors.bg_base)

        # ── Separador inferior ───────────────────────────────────
        painter.setPen(QPen(colors.border_item, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        # ── Checkbox (modo multi-select) ─────────────────────────
        cb_rect = self.get_checkbox_rect(rect)
        if self.show_checkboxes:
            self._paint_checkbox(painter, cb_rect, colors, is_selected, index.row())

        # ── Avatar with per-tool colour ──────────────────────────
        icon_x = cb_rect.right() + 15 if self.show_checkboxes else rect.left() + 18
        icon_rect = QRect(icon_x, rect.top() + (rect.height() - 40) // 2, 40, 40)
        self._paint_avatar(painter, icon_rect, project)

        # ── Text - reserve room for the inline buttons ──────────
        text_x = icon_rect.right() + 12
        # On hover, reserve width for the buttons; otherwise use the full width
        if is_hovered:
            btn_reserve = self._BTN_W + self._STAR_W + self._BTN_GAP + self._PAD_RIGHT + 12
        else:
            btn_reserve = self._STAR_W + self._PAD_RIGHT + 6  # always reserve ★
        text_width = rect.width() - (text_x - rect.left()) - btn_reserve
        self._paint_text(painter, rect, text_x, text_width, project, colors)

        # ── ★ favourite button - always present, dimmed if not fav ─
        star_rect = self._get_star_btn_rect(rect)
        self._paint_star_btn(painter, star_rect, project, colors, is_hovered)

        # ── "Open" button - hover only ─────────────────────────
        if is_hovered:
            open_rect = self._get_open_btn_rect(rect)
            self._paint_open_btn(painter, open_rect, colors)

        # ── Indicador lateral ────────────────────────────────────
        if is_selected or is_active:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(colors.indicator_selected))
            painter.drawRect(QRect(rect.left(), rect.top(), 4, rect.height()))
        elif is_hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(colors.indicator_hover))
            painter.drawRect(QRect(rect.left(), rect.top(), 3, rect.height()))

        painter.restore()

    def _paint_checkbox(self, painter, cb_rect, colors: ThemeColors, is_checked, row):
        if is_checked:
            painter.setBrush(QBrush(colors.checkbox_checked_bg))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(cb_rect, 4, 4)
            painter.setPen(QPen(colors.checkbox_check_mark, 2))
            path = QPainterPath()
            path.moveTo(cb_rect.left() + 5, cb_rect.center().y())
            path.lineTo(cb_rect.center().x() - 1, cb_rect.bottom() - 6)
            path.lineTo(cb_rect.right() - 4, cb_rect.top() + 6)
            painter.drawPath(path)
        elif row == self.hover_checkbox:
            painter.setBrush(QBrush(colors.checkbox_hover_bg))
            painter.setPen(QPen(colors.checkbox_hover_border, 1.5))
            painter.drawRoundedRect(cb_rect, 4, 4)
        else:
            painter.setBrush(QBrush(colors.checkbox_empty_bg))
            painter.setPen(QPen(colors.checkbox_empty_border, 1.5))
            painter.drawRoundedRect(cb_rect, 4, 4)

    def _paint_avatar(self, painter: QPainter, icon_rect: QRect, project: "ProjectItem"):
        """Circular avatar with a per-tool colour (project.color) or hash fallback."""
        avatar_rect = icon_rect.adjusted(2, 2, -2, -2)
        color = _avatar_color_for(project)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(avatar_rect)

        text_color = QColor("#202124") if color.lightness() > 150 else QColor("#ffffff")
        painter.setPen(text_color)
        painter.setFont(QFont("", 12, QFont.Bold))
        initial = (project.name or "?").strip()[:1].upper()
        painter.drawText(avatar_rect, Qt.AlignCenter, initial)

    def _paint_text(self, painter, rect, text_x, text_width, project, colors: ThemeColors):
        top = rect.top() + 10

        # Name
        painter.setFont(QFont("", 11, QFont.Bold))
        painter.setPen(colors.text_primary)
        name_rect = QRect(text_x, top, text_width, 20)
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, project.name or "")

        # ID + description
        painter.setFont(QFont("", 9))
        painter.setPen(colors.text_secondary)
        desc = f"ID: {project.id}"
        if project.description:
            desc = f"{desc} | {project.description}"
        painter.drawText(QRect(text_x, top + 22, text_width, 16),
                         Qt.AlignLeft | Qt.AlignVCenter, desc)

        # Date and path
        painter.setPen(colors.text_muted)
        painter.setFont(QFont("", 8))
        date_str = f"\U0001f4c5 {project.last_modified}"
        painter.drawText(QRect(text_x, top + 40, text_width // 2, 14),
                         Qt.AlignLeft | Qt.AlignVCenter, date_str)

        path_str = project.path if len(str(project.path)) <= 55 else "..." + str(project.path)[-52:]
        painter.drawText(QRect(text_x + text_width // 2, top + 40, text_width // 2, 14),
                         Qt.AlignLeft | Qt.AlignVCenter, f"\U0001f4c2 {path_str}")

        # Inline tags (small pills below the date/path, only if they fit)
        if project.tags:
            tag_y = top + 56
            tag_x = text_x
            painter.setFont(QFont("", 7))
            for tag in project.tags[:4]:
                tw = min(len(tag) * 6 + 10, 90)
                tag_rect = QRect(tag_x, tag_y, tw, 14)
                painter.setBrush(QBrush(colors.tag_bg))
                painter.setPen(QPen(colors.tag_border, 0.8))
                painter.drawRoundedRect(tag_rect, 3, 3)
                painter.setPen(colors.tag_text)
                painter.drawText(tag_rect, Qt.AlignCenter, tag)
                tag_x += tw + 4
                if tag_x > text_x + text_width:
                    break

    def _paint_open_btn(self, painter: QPainter, btn_rect: QRect, colors: ThemeColors):
        """'Open' button - visible on hover only."""
        # Semi-transparent background tinted with the primary colour
        bg = _with_alpha(colors.primary, 35)
        border = _with_alpha(colors.primary, 90)
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1))
        path = QPainterPath()
        path.addRoundedRect(btn_rect.x(), btn_rect.y(),
                            btn_rect.width(), btn_rect.height(),
                            self._BTN_R, self._BTN_R)
        painter.drawPath(path)

        painter.setPen(QPen(colors.primary_light, 1))
        painter.setFont(QFont("", 9, QFont.Bold))
        painter.drawText(btn_rect, Qt.AlignCenter, "Open")

    def _paint_star_btn(self, painter: QPainter, btn_rect: QRect,
                        project: "ProjectItem", colors: ThemeColors, is_hovered: bool):
        """★ button - always visible, dimmed when not a favourite."""
        if project.favorite:
            # Activo: fondo gold tenue
            painter.setBrush(QBrush(QColor(255, 195, 30, 30)))
            painter.setPen(QPen(QColor(255, 195, 30, 100), 1))
            path = QPainterPath()
            path.addRoundedRect(btn_rect.x(), btn_rect.y(),
                                btn_rect.width(), btn_rect.height(),
                                self._BTN_R, self._BTN_R)
            painter.drawPath(path)
            painter.setPen(QPen(QColor(255, 195, 30, 230)))
        elif is_hovered:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(_with_alpha(colors.text_muted, 120)))
        else:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(_with_alpha(colors.text_muted, 50)))

        painter.setFont(QFont("", 11))
        painter.drawText(btn_rect, Qt.AlignCenter, "★")

    # ── Editor events (clicks on the inline buttons) ────────────

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonPress:
            project = index.data(Qt.DisplayRole)
            if not project:
                return super().editorEvent(event, model, option, index)

            pos = event.pos()

            # Click on the "Open" button
            if self.hover_row == index.row():
                open_rect = self._get_open_btn_rect(option.rect)
                if open_rect.contains(pos):
                    self.open_clicked.emit(project)
                    return True

                # Click on the "★" button
                star_rect = self._get_star_btn_rect(option.rect)
                if star_rect.contains(pos):
                    self.favorite_clicked.emit(project)
                    return True

            # Click on the checkbox
            if self.show_checkboxes:
                cb_rect = self.get_checkbox_rect(option.rect)
                if cb_rect.contains(pos):
                    self.checkbox_clicked.emit(index.row(), project.id)
                    return True

        return super().editorEvent(event, model, option, index)

    def mouseMoveEvent_hook(self, pos, rect: QRect):
        """
        Call from the containing widget's mouseMoveEvent to refresh which
        inline button sits under the cursor.
        Returns True when the cursor moved to a different button (needs repaint).
        """
        prev_open = self._hover_open
        prev_star = self._hover_star
        self._hover_open = self._get_open_btn_rect(rect).contains(pos)
        self._hover_star = self._get_star_btn_rect(rect).contains(pos)
        return (self._hover_open != prev_open) or (self._hover_star != prev_star)


class ActionBar(QWidget):
    """
    Action bar for the listview.

    Layout:
      [☑ multi] [filter▾] [sort▾]  ──stretch──  [search field▾] [🔍 input......] | [contextual actions] [🗑]

    The contextual actions (edit, favourite, export, stats) only appear when an
    item is active or selected. The delete button is always present but disabled
    when there is no target.
    """

    import_clicked           = Signal()
    export_clicked           = Signal()
    edit_clicked             = Signal()
    favorite_clicked         = Signal()
    stats_clicked            = Signal()
    delete_clicked           = Signal()
    select_all_clicked       = Signal()
    toggle_multi_clicked     = Signal(bool)
    filter_changed           = Signal(str)
    sort_changed             = Signal(str)
    search_field_changed     = Signal(str)
    search_visibility_toggled = Signal()
    search_text_changed      = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_filter       = "all"
        self._current_sort         = "recent"
        self._current_search_field = "name"
        self._setup_ui()

    def _make_tool_btn(self, text: str, tooltip: str, size: int = 30) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(size, size)
        return btn

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        # ── Left group: mode and filters ────────────────────────
        self.multi_mode_btn = self._make_tool_btn("☑", "Multi-selection")
        self.multi_mode_btn.setCheckable(True)
        self.multi_mode_btn.toggled.connect(self.toggle_multi_clicked.emit)
        layout.addWidget(self.multi_mode_btn)

        self.select_all_btn = self._make_tool_btn("⊞", "Select / deselect all")
        self.select_all_btn.setVisible(False)  # multi-select only
        self.select_all_btn.clicked.connect(self.select_all_clicked.emit)
        layout.addWidget(self.select_all_btn)

        # Filter
        self.filter_btn = self._make_tool_btn("⊟", "Filter")
        self.filter_btn.setPopupMode(QToolButton.InstantPopup)
        self.filter_menu = QMenu(self.filter_btn)
        self._filter_actions: dict[str, object] = {}
        for key, label in [
            ("all",             "All"),
            ("favorites",       "Favorites"),
            ("has_description", "With description"),
            ("has_language",    "With tool"),
            ("has_tags",        "With tags"),
        ]:
            action = self.filter_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(lambda _c=False, k=key: self._set_filter(k))
            self._filter_actions[key] = action
        self.filter_btn.setMenu(self.filter_menu)
        layout.addWidget(self.filter_btn)

        # Sort
        self.sort_btn = self._make_tool_btn("↕", "Sort")
        self.sort_btn.setPopupMode(QToolButton.InstantPopup)
        self.sort_menu = QMenu(self.sort_btn)
        self._sort_actions: dict[str, object] = {}
        for key, label in [
            ("recent",    "Most recent"),
            ("name_asc",  "Name A → Z"),
            ("name_desc", "Name Z → A"),
            ("path_asc",  "Path A → Z"),
        ]:
            action = self.sort_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(lambda _c=False, k=key: self._set_sort(k))
            self._sort_actions[key] = action
        self.sort_btn.setMenu(self.sort_menu)
        layout.addWidget(self.sort_btn)

        layout.addStretch(1)

        # ── Centre: selection label (only shown when something is selected) ──
        self.selection_label = QLabel("")
        self.selection_label.setVisible(False)
        layout.addWidget(self.selection_label)

        layout.addStretch(1)

        # ── Right group: search + contextual actions ────────────
        # Search field
        self.search_mode_btn = self._make_tool_btn("🔍", "Search field")
        self.search_mode_btn.setPopupMode(QToolButton.InstantPopup)
        self.search_mode_menu = QMenu(self.search_mode_btn)
        self._search_field_actions: dict[str, object] = {}
        for key, label in [
            ("name",        "Name"),
            ("tags",        "Tags"),
            ("description", "Description"),
            ("path",        "Path"),
            ("id",          "ID"),
            ("all",         "Everything"),
        ]:
            action = self.search_mode_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(lambda _c=False, k=key: self._set_search_field(k))
            self._search_field_actions[key] = action
        self.search_mode_btn.setMenu(self.search_mode_menu)
        layout.addWidget(self.search_mode_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.setMinimumHeight(30)
        self.search_input.setMinimumWidth(160)
        self.search_input.textChanged.connect(self.search_text_changed.emit)
        layout.addWidget(self.search_input)

        # Visual separator
        sep = QLabel("|")
        sep.setFixedWidth(10)
        sep.setAlignment(Qt.AlignCenter)
        layout.addWidget(sep)
        self._separator = sep

        # Contextual actions (only visible when there is a target)
        self.edit_btn = self._make_tool_btn("✏", "Edit")
        self.edit_btn.clicked.connect(self.edit_clicked.emit)
        layout.addWidget(self.edit_btn)

        self.favorite_btn = self._make_tool_btn("★", "Mark / unmark favourite")
        self.favorite_btn.clicked.connect(self.favorite_clicked.emit)
        layout.addWidget(self.favorite_btn)

        self.export_btn = self._make_tool_btn("↑", "Export")
        self.export_btn.clicked.connect(self.export_clicked.emit)
        layout.addWidget(self.export_btn)

        self.import_btn = self._make_tool_btn("↓", "Import")
        self.import_btn.clicked.connect(self.import_clicked.emit)
        layout.addWidget(self.import_btn)

        self.stats_btn = self._make_tool_btn("◫", "Statistics")
        self.stats_btn.clicked.connect(self.stats_clicked.emit)
        layout.addWidget(self.stats_btn)

        self.delete_btn = self._make_tool_btn("⌫", "Delete selected")
        self.delete_btn.clicked.connect(self.delete_clicked.emit)
        layout.addWidget(self.delete_btn)

        self._context_buttons = [
            self.edit_btn, self.favorite_btn, self.export_btn,
            self.import_btn, self.stats_btn,
        ]

        self._update_filter_checks()
        self._update_sort_checks()
        self._update_search_field_checks()
        # Start with context buttons hidden
        self.set_actions_enabled(False)

    # ── State refresh ────────────────────────────────────────────

    def _update_filter_checks(self):
        for key, action in self._filter_actions.items():
            action.setChecked(key == self._current_filter)

    def _update_sort_checks(self):
        for key, action in self._sort_actions.items():
            action.setChecked(key == self._current_sort)

    def _update_search_field_checks(self):
        icon_map = {"name": "🔍", "tags": "🏷", "description": "≡",
                    "path": "⌂", "id": "#", "all": "✦"}
        self.search_mode_btn.setText(icon_map.get(self._current_search_field, "🔍"))
        for key, action in self._search_field_actions.items():
            action.setChecked(key == self._current_search_field)

    def _set_filter(self, key: str):
        self._current_filter = key
        self._update_filter_checks()
        self.filter_changed.emit(key)

    def _set_sort(self, key: str):
        self._current_sort = key
        self._update_sort_checks()
        self.sort_changed.emit(key)

    def _set_search_field(self, key: str):
        self._current_search_field = key
        self._update_search_field_checks()
        self.search_field_changed.emit(key)

    # ── Public API ──────────────────────────────────────────────

    def set_search_visible(self, visible: bool):
        self.search_input.setVisible(visible)
        self.search_mode_btn.setVisible(visible)
        if visible:
            self.search_input.setFocus()
        else:
            self.search_input.clear()

    def set_selection_count(self, count: int):
        if count > 0:
            self.selection_label.setText(f"{count} seleccionado{'s' if count != 1 else ''}")
            self.selection_label.setVisible(True)
        else:
            self.selection_label.setVisible(False)

    def set_actions_enabled(self, has_target: bool):
        """Show/hide the contextual buttons and separator depending on the target."""
        for btn in self._context_buttons:
            btn.setVisible(has_target)
        self._separator.setVisible(has_target)
        self.delete_btn.setEnabled(has_target)

    def set_multi_mode(self, enabled: bool):
        was_blocked = self.multi_mode_btn.blockSignals(True)
        self.multi_mode_btn.setChecked(enabled)
        self.multi_mode_btn.blockSignals(was_blocked)
        self.select_all_btn.setVisible(enabled)

    def set_select_all_state(self, all_selected: bool):
        self.select_all_btn.setText("☐" if all_selected else "⊞")

    def get_search_text(self) -> str:
        return self.search_input.text().strip()

    def get_search_field(self) -> str:
        return self._current_search_field


class ProjectListWidget(QWidget):
    """
    Gmail-style project list with multi-selection.

    Agnostic: takes an optional external delegate_class. When none is passed it
    uses ProjectItemDelegate. The delegate must subclass ProjectItemDelegate or
    implement the same interface (checkbox_clicked, open_clicked and
    favorite_clicked signals; set_hover_row, set_hover_checkbox,
    set_show_checkboxes, get_checkbox_rect methods).

    Public signals:
        project_selected        - active item changed (single click)
        project_double_clicked  - item double-clicked
        open_requested          - inline "Open" button clicked
        favorite_toggled        - inline "★" button clicked
        selection_changed       - the selected/active item list changed
        import_requested        - import action from the action bar
        export_requested        - export action
        favorite_requested      - favourite action from the action bar (bulk)
        delete_requested        - delete action
        edit_requested          - edit action
        stats_requested         - statistics action
        page_changed            - page changed
    """

    project_selected        = Signal(object)   # ProjectItem
    project_double_clicked  = Signal(object)   # ProjectItem
    open_requested          = Signal(object)   # ProjectItem  ← inline Open button
    favorite_toggled        = Signal(object)   # ProjectItem  ← inline ★ button
    selection_changed       = Signal(list)
    import_requested        = Signal(list)
    export_requested        = Signal(list)
    favorite_requested      = Signal(list)
    delete_requested        = Signal(list)
    edit_requested          = Signal(list)
    stats_requested         = Signal(list)
    page_changed            = Signal(int)

    def __init__(self,
                 data_loader: Callable[[int, int], List[ProjectItem]],
                 total_count_loader: Callable[[], int],
                 items_per_page: int = 10,
                 show_pagination: bool = True,
                 sort_changed_callback: Optional[Callable[[str], None]] = None,
                 filter_changed_callback: Optional[Callable[[str], None]] = None,
                 search_changed_callback: Optional[Callable[[str, str], None]] = None,
                 delegate_class: Optional[Type[ProjectItemDelegate]] = None,
                 parent=None):
        super().__init__(parent)
        self.data_loader             = data_loader
        self.total_count_loader      = total_count_loader
        self.items_per_page          = items_per_page
        self.show_pagination         = show_pagination
        self.sort_changed_callback   = sort_changed_callback
        self.filter_changed_callback = filter_changed_callback
        self.search_changed_callback = search_changed_callback
        self._delegate_class         = delegate_class or ProjectItemDelegate
        self._current_filter         = "all"
        self._current_sort           = "recent"
        self._current_search_field   = "name"
        self._loaded_projects: List[ProjectItem] = []
        self._multi_select_enabled   = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.action_bar = ActionBar()
        self.action_bar.import_clicked.connect(
            lambda: self.import_requested.emit(self._get_action_projects()))
        self.action_bar.export_clicked.connect(
            lambda: self.export_requested.emit(self._get_action_projects()))
        self.action_bar.edit_clicked.connect(
            lambda: self.edit_requested.emit(self._get_action_projects()))
        self.action_bar.favorite_clicked.connect(
            lambda: self.favorite_requested.emit(self._get_action_projects()))
        self.action_bar.stats_clicked.connect(
            lambda: self.stats_requested.emit(self._get_action_projects()))
        self.action_bar.delete_clicked.connect(
            lambda: self.delete_requested.emit(self._get_action_projects()))
        self.action_bar.select_all_clicked.connect(self.select_all)
        self.action_bar.toggle_multi_clicked.connect(self._set_multi_select_mode)
        self.action_bar.filter_changed.connect(self._set_filter)
        self.action_bar.sort_changed.connect(self._set_sort)
        self.action_bar.search_field_changed.connect(self._set_search_field)
        self.action_bar.search_text_changed.connect(self._on_search_text_changed)
        self.action_bar.search_visibility_toggled.connect(self._toggle_search)
        layout.addWidget(self.action_bar)

        # ── QListView ────────────────────────────────────────────
        self.list_view = QListView()
        self.list_view.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_view.setMouseTracking(True)

        self.model    = ProjectListModel()
        self.delegate = self._delegate_class()
        self.delegate.set_show_checkboxes(self._multi_select_enabled)

        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)

        self.list_view.clicked.connect(self._on_clicked)
        self.list_view.doubleClicked.connect(self._on_double_clicked)
        self.list_view.entered.connect(self._on_entered)
        self.delegate.checkbox_clicked.connect(self._on_checkbox)

        # ── Inline button signals ────────────────────────────────
        if hasattr(self.delegate, "open_clicked"):
            self.delegate.open_clicked.connect(self._on_inline_open)
        if hasattr(self.delegate, "favorite_clicked"):
            self.delegate.favorite_clicked.connect(self._on_inline_favorite)

        layout.addWidget(self.list_view)
        self._apply_list_surface_style()

        # ── Pagination ───────────────────────────────────────────
        if self.show_pagination:
            self.pagination = PaginationControl(
                total_items=0,
                items_per_page=self.items_per_page,
                items_per_page_options=[5, 10, 15, 20, 25],
            )
            self.pagination.page_changed.connect(self._on_page_changed)
            self.pagination.items_per_page_changed.connect(lambda _: self.load_data())
            layout.addWidget(self.pagination)

        self._update_action_bar()

    # ── Data loading ───────────────────────────────────────────

    def load_data(self):
        page = self.pagination.get_current_page() if self.show_pagination else 1
        size = self.pagination.get_items_per_page() if self.show_pagination \
            else self.items_per_page

        projects = self.data_loader(page, size)
        total = self.total_count_loader()
        self._loaded_projects = projects

        if self.show_pagination:
            self.pagination.set_total_items(total)

        self._apply_view_controls()

    def refresh(self):
        self.load_data()

    # ── Forced repaint after a theme change ─────────────────────

    def force_repaint(self):
        """
        Call this after switching theme.
        unpolish/polish forces Qt to re-read QPalette on ALL widgets,
        including the QListView and its viewport.
        """
        # In QAbstractItemView, the visible repaint happens in the viewport.
        # Calling update() on a QListView can resolve to an incompatible overload.
        for widget in [self, self.list_view.viewport()]:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        self._apply_list_surface_style()

        # Force a repaint of the delegate
        self.list_view.viewport().update()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange):
            self._apply_list_surface_style()
            self.list_view.viewport().update()

    def _apply_list_surface_style(self):
        colors = ThemeColors.get()
        self.list_view.setStyleSheet(
            f"QListView {{ background-color: {colors.bg_base.name()}; }}"
        )

    # ── Slots internos ───────────────────────────────────────────

    def _on_checkbox(self, row: int, project_id):
        if not self._multi_select_enabled:
            return
        self.model.toggle_selection(project_id)
        self._update_action_bar()
        self._emit_selection_changed()

    def _on_clicked(self, index):
        project = self.model.get_project(index.row())
        if project:
            self.model.set_active_project(project.id)
            self.project_selected.emit(project)
            self._update_action_bar()
            self._emit_selection_changed()

    def _on_double_clicked(self, index):
        project = self.model.get_project(index.row())
        if project:
            self.project_double_clicked.emit(project)

    def _on_entered(self, index):
        """Hover - refresh hover_row and hover_checkbox on the delegate."""
        self.delegate.set_hover_row(index.row())

        pos = self.list_view.viewport().mapFromGlobal(QCursor.pos())
        item_rect = self.list_view.visualRect(index)
        cb_rect = self.delegate.get_checkbox_rect(item_rect)

        self.delegate.set_hover_checkbox(
            index.row() if (not cb_rect.isNull() and cb_rect.contains(pos)) else -1
        )
        self.list_view.viewport().update()

    def _on_inline_open(self, project: ProjectItem):
        """Inline 'Open' button clicked - emits open_requested and project_double_clicked."""
        self.open_requested.emit(project)
        self.project_double_clicked.emit(project)

    def _on_inline_favorite(self, project: ProjectItem):
        """Inline '★' button clicked - emits favorite_toggled and favorite_requested."""
        self.favorite_toggled.emit(project)
        self.favorite_requested.emit([project])

    def _on_page_changed(self, _page: int):
        self.load_data()
        self.page_changed.emit(_page)

    def _update_action_bar(self):
        selected_count = self.model.get_selected_count()
        targets = self._get_action_projects()
        self.action_bar.set_selection_count(selected_count if self._multi_select_enabled else len(targets))
        self.action_bar.set_actions_enabled(bool(targets))
        self.action_bar.set_multi_mode(self._multi_select_enabled)
        self.action_bar.set_select_all_state(self.model.are_all_selected())

    def _get_action_projects(self) -> List[ProjectItem]:
        if self._multi_select_enabled:
            selected = self.model.get_selected_projects()
            if selected:
                return selected
        active = self.model.get_active_project()
        return [active] if active else []

    def _emit_selection_changed(self):
        self.selection_changed.emit(self._get_action_projects())

    def _set_multi_select_mode(self, enabled: bool):
        self._multi_select_enabled = enabled
        self.delegate.set_show_checkboxes(enabled)
        if not enabled:
            self.model.clear_selection()
        self.list_view.viewport().update()
        self._update_action_bar()
        self._emit_selection_changed()

    def _set_filter(self, key: str):
        self._current_filter = key
        if self.filter_changed_callback is not None:
            self.filter_changed_callback(key)
            self.load_data()
        else:
            self._apply_view_controls()

    def _set_sort(self, key: str):
        self._current_sort = key
        if self.sort_changed_callback is not None:
            self.sort_changed_callback(key)
            self.load_data()
        else:
            self._apply_view_controls()

    def _set_search_field(self, key: str):
        self._current_search_field = key
        if self.search_changed_callback is not None:
            self.search_changed_callback(self._current_search_field, self.action_bar.get_search_text())
            self.load_data()
        else:
            self._apply_view_controls()

    def _on_search_text_changed(self, text: str):
        if self.search_changed_callback is not None:
            self.search_changed_callback(self._current_search_field, text)
            self.load_data()
        else:
            self._apply_view_controls()

    def _toggle_search(self):
        visible = self.action_bar.search_input.isHidden()
        self.action_bar.set_search_visible(visible)
        if self.search_changed_callback is not None:
            self.search_changed_callback(self._current_search_field, self.action_bar.get_search_text())
            self.load_data()
        else:
            self._apply_view_controls()

    def _matches_filter(self, project: ProjectItem) -> bool:
        if self._current_filter == "all":
            return True
        if self._current_filter == "has_description":
            return bool((project.description or "").strip())
        if self._current_filter == "has_language":
            return bool(project.language)
        if self._current_filter == "has_tags":
            return bool(project.tags)
        if self._current_filter == "favorites":
            return bool(project.favorite)
        return True

    def _apply_view_controls(self):
        projects = self._loaded_projects

        if self.filter_changed_callback is None:
            projects = [p for p in projects if self._matches_filter(p)]

        if self.search_changed_callback is None:
            query = self.action_bar.get_search_text().lower()
            if query:
                field = self._current_search_field

                def matches(project: ProjectItem) -> bool:
                    haystack = {
                        "name": (project.name or "").lower(),
                        "description": (project.description or "").lower(),
                        "path": (project.path or "").lower(),
                        "tags": " ".join(project.tags).lower(),
                        "id": str(project.id).lower(),
                        "all": " ".join([
                            (project.name or "").lower(),
                            (project.description or "").lower(),
                            (project.path or "").lower(),
                            " ".join(project.tags).lower(),
                            str(project.id).lower(),
                        ]),
                    }
                    return query in haystack.get(field, haystack["all"])

                projects = [p for p in projects if matches(p)]

        self.model.set_projects(projects)
        self._update_action_bar()
        self._emit_selection_changed()

    # ── Public API ──────────────────────────────────────────────

    def select_all(self):
        if not self._multi_select_enabled:
            self._set_multi_select_mode(True)
        if self.model.are_all_selected():
            self.model.clear_selection()
        else:
            self.model.select_all()
        self._update_action_bar()
        self._emit_selection_changed()

    def clear_selection(self):
        self.model.clear_selection()
        self.model.set_active_project(None)
        self._update_action_bar()
        self._emit_selection_changed()
