"""
action_header.py
────────────────
QHeaderView with per-column sort / search / filter buttons.
SVG icons recoloured with the active palette (currentColor → palette).
Requires PySide6.QtSvg.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QDoubleValidator, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QStyle, QStyleOptionHeader,
    QVBoxLayout, QWidget,
)

from .table_config import ColumnDef, ColumnKind, FilterOperator, FilterSpec, SortSpec, TableConfig

_ICONS = Path(__file__).parent / "icons"

_ICON_FILES: dict[str, str] = {
    "sort":      "sort.svg",
    "sort-asc":  "sort-asc.svg",
    "sort-desc": "sort-desc.svg",
    "search":    "search.svg",
    "filter":    "filter.svg",
}


@lru_cache(maxsize=128)
def _svg_pixmap(name: str, color_hex: str, size: int, dpr: float) -> QPixmap:
    """SVG → QPixmap, recoloreado (currentColor → color_hex), cacheado."""
    svg = (_ICONS / _ICON_FILES[name]).read_bytes().replace(b"currentColor", color_hex.encode())
    renderer = QSvgRenderer(QByteArray(svg))
    actual = max(1, int(size * dpr))
    pixmap = QPixmap(actual, actual)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    renderer.render(p)
    p.end()
    return pixmap


# ── ActionHeader ──────────────────────────────────────────────────────────────

class ActionHeader(QHeaderView):
    """Horizontal header with per-column action buttons.

    Signal:
        actionClicked(logical_index, action, modifiers)
            action: "sort" | "search" | "filter"
            modifiers: Qt.KeyboardModifiers (Shift → additive sort)
    """

    actionClicked = Signal(int, str, Qt.KeyboardModifiers)
    _ACTIONS = ("sort", "search", "filter")

    def __init__(self, config: TableConfig, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._config = config
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.setMouseTracking(True)
        self.setMinimumHeight(38)

        self._hovered: tuple[int, str] | None = None
        self._active_searches: set[int] = set()
        self._active_filters:  set[int] = set()
        self._sort_directions: dict[int, Qt.SortOrder] = {}

    def set_query_state(
        self,
        sorts: list[SortSpec],
        active_searches: set[str],
        active_filters: set[str],
    ) -> None:
        visible = self._config.visible_columns()
        offset  = 1 if self._config.show_row_numbers else 0
        to_idx  = {col.field: i + offset for i, col in enumerate(visible)}

        self._active_searches = {to_idx[f] for f in active_searches if f in to_idx}
        self._active_filters  = {to_idx[f] for f in active_filters  if f in to_idx}
        self._sort_directions = {
            to_idx[s.field]: (
                Qt.SortOrder.DescendingOrder if s.descending else Qt.SortOrder.AscendingOrder
            )
            for s in sorts if s.field in to_idx
        }
        self.viewport().update()

    def popup_position(self, logical_index: int) -> QPoint:
        x = self.sectionViewportPosition(logical_index)
        return self.viewport().mapToGlobal(QPoint(x, self.height()))

    # ── Paint ─────────────────────────────────────────────────────────────

    def paintSection(self, painter: QPainter, rect: QRect, logical_index: int) -> None:
        if not rect.isValid():
            return
        painter.save()

        opt = QStyleOptionHeader()
        self.initStyleOption(opt)
        opt.rect = rect
        opt.section = logical_index
        opt.text = ""
        self.style().drawControl(QStyle.ControlElement.CE_Header, opt, painter, self)

        btn_rects = self._action_rects(rect, logical_index)
        _btn_slot = 17  # must match size+gap in _action_rects
        reserved  = len(btn_rects) * _btn_slot + (3 if btn_rects else 0)
        text_rect = rect.adjusted(8, 0, -reserved, 0)

        title = str(
            self.model().headerData(
                logical_index, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole,
            ) or ""
        )
        title = painter.fontMetrics().elidedText(
            title, Qt.TextElideMode.ElideRight, max(0, text_rect.width()),
        )
        painter.setPen(self.palette().text().color())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)

        dpr  = round(self.devicePixelRatioF(), 2)
        size = 12

        for action, btn_rect in btn_rects.items():
            active  = self._is_active(action, logical_index)
            hovered = self._hovered == (logical_index, action)

            if active or hovered:
                bg = self.palette().highlight().color() if active else self.palette().midlight().color()
                bg.setAlpha(80 if active else 55)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(bg)
                painter.drawRoundedRect(btn_rect, 4, 4)

            icon_color = (
                self.palette().highlightedText().color() if active
                else self.palette().buttonText().color()
            )

            if action == "sort":
                sort_dir = self._sort_directions.get(logical_index)
                icon_name = (
                    "sort-asc"  if sort_dir == Qt.SortOrder.AscendingOrder  else
                    "sort-desc" if sort_dir == Qt.SortOrder.DescendingOrder else
                    "sort"
                )
                if sort_dir is None:
                    painter.setOpacity(0.35)
            else:
                icon_name = action

            cx = btn_rect.center().x() - size // 2
            cy = btn_rect.center().y() - size // 2
            painter.drawPixmap(cx, cy, _svg_pixmap(icon_name, icon_color.name(), size, dpr))
            painter.setOpacity(1.0)

        painter.restore()

    # ── Mouse ─────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        li  = self.logicalIndexAt(pos)
        hovered: tuple[int, str] | None = None

        if li >= 0:
            for action, r in self._action_rects(self._section_rect(li), li).items():
                if r.contains(pos):
                    hovered = (li, action)
                    break

        if hovered != self._hovered:
            self._hovered = hovered
            self.viewport().update()

        if hovered:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.position().toPoint()
        li  = self.logicalIndexAt(pos)

        if li >= 0:
            for action, r in self._action_rects(self._section_rect(li), li).items():
                if r.contains(pos):
                    self.actionClicked.emit(li, action, event.modifiers())
                    event.accept()
                    return

        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = None
        self.viewport().unsetCursor()
        self.viewport().update()
        super().leaveEvent(event)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _col_def(self, logical_index: int) -> ColumnDef | None:
        visible = self._config.visible_columns()
        offset  = 1 if self._config.show_row_numbers else 0
        idx     = logical_index - offset
        return visible[idx] if 0 <= idx < len(visible) else None

    def _action_rects(self, rect: QRect, logical_index: int) -> dict[str, QRect]:
        col = self._col_def(logical_index)
        if col is None:
            return {}
        allowed = {
            a for a, flag in [
                ("sort",   col.sortable),
                ("search", col.searchable),
                ("filter", col.filterable),
            ] if flag
        }
        actions = [a for a in self._ACTIONS if a in allowed]

        size, gap = 16, 1  # slot = 17px, must match _btn_slot in paintSection
        right = rect.right() - 4
        top   = rect.center().y() - size // 2
        result: dict[str, QRect] = {}
        for action in reversed(actions):
            result[action] = QRect(right - size + 1, top, size, size)
            right -= size + gap
        return result

    def _section_rect(self, logical_index: int) -> QRect:
        return QRect(
            self.sectionViewportPosition(logical_index), 0,
            self.sectionSize(logical_index), self.height(),
        )

    def _is_active(self, action: str, logical_index: int) -> bool:
        return (
            (action == "search" and logical_index in self._active_searches) or
            (action == "filter" and logical_index in self._active_filters)  or
            (action == "sort"   and logical_index in self._sort_directions)
        )


# ── Popups ────────────────────────────────────────────────────────────────────

class SearchPopup(QFrame):
    applied = Signal(str)
    cleared = Signal()

    def __init__(self, title: str, current_text: str = "", parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.editor = QLineEdit(current_text)
        self.editor.setPlaceholderText(f"Search in {title}…")
        self.editor.selectAll()

        btns = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btn_apply = QPushButton("Apply")
        btn_apply.setDefault(True)
        btns.addStretch(1)
        btns.addWidget(btn_clear)
        btns.addWidget(btn_apply)

        layout.addWidget(self.editor)
        layout.addLayout(btns)

        btn_apply.clicked.connect(self._apply)
        btn_clear.clicked.connect(self._clear)
        self.editor.returnPressed.connect(self._apply)

    def _apply(self) -> None:
        self.applied.emit(self.editor.text())
        self.close()

    def _clear(self) -> None:
        self.cleared.emit()
        self.close()


# Operator label → (FilterOperator, value_transform)
_TEXT_OPS: list[tuple[str, FilterOperator, Any]] = [
    ("contains", FilterOperator.ILIKE, lambda v: f"%{v}%"),
    ("=",        FilterOperator.EQ,    lambda v: v),
    ("≠",        FilterOperator.NEQ,   lambda v: v),
    ("starts",   FilterOperator.ILIKE, lambda v: f"{v}%"),
    ("ends",     FilterOperator.ILIKE, lambda v: f"%{v}"),
]
_NUM_OPS: list[tuple[str, FilterOperator, Any]] = [
    ("=",  FilterOperator.EQ,  None),
    ("≠",  FilterOperator.NEQ, None),
    (">",  FilterOperator.GT,  None),
    ("≥",  FilterOperator.GTE, None),
    ("<",  FilterOperator.LT,  None),
    ("≤",  FilterOperator.LTE, None),
]


def _decode_text_filter(spec: FilterSpec) -> tuple[str, str]:
    """FilterSpec → (display_label, raw_text) to pre-fill the popup."""
    v = str(spec.value) if spec.value is not None else ""
    if spec.op == FilterOperator.ILIKE:
        if v.startswith("%") and v.endswith("%"):
            return "contains", v[1:-1]
        if v.endswith("%"):
            return "starts", v[:-1]
        if v.startswith("%"):
            return "ends", v[1:]
        return "contains", v
    for label, op, _ in _TEXT_OPS:
        if op == spec.op:
            return label, v
    return "contains", v


class FilterPopup(QFrame):
    applied = Signal(FilterOperator, object)  # (op, processed_value)
    cleared = Signal()

    def __init__(self, col_def: ColumnDef, current: FilterSpec | None, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self._col = col_def
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(QLabel(f"Filtrar {col_def.label}"))

        self._checkboxes: list[QCheckBox] = []
        self._op_combo:   QComboBox | None = None
        self._value_edit: QLineEdit | None = None
        self._op_map:     list[tuple[str, FilterOperator, Any]] = []
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setDefault(True)

        if col_def.kind == ColumnKind.CHOICE:
            self._build_choice(layout, current)
        elif col_def.kind in (ColumnKind.NUMBER, ColumnKind.INTEGER):
            self._build_numeric(layout, current)
        else:
            self._build_text(layout, current)

        btns = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btns.addStretch()
        btns.addWidget(btn_clear)
        btns.addWidget(self._apply_btn)
        layout.addLayout(btns)

        btn_clear.clicked.connect(self._clear)
        self._apply_btn.clicked.connect(self._apply)

    # ── builders ──────────────────────────────────────────────────────────

    def _build_choice(self, layout: QVBoxLayout, current: FilterSpec | None) -> None:
        selected = set(current.value) if current and current.op == FilterOperator.IN else set(self._col.choices)
        for ch in self._col.choices:
            cb = QCheckBox(ch)
            cb.setChecked(ch in selected)
            cb.stateChanged.connect(self._refresh_apply)
            self._checkboxes.append(cb)
            layout.addWidget(cb)

        row = QHBoxLayout()
        btn_all  = QPushButton("All")
        btn_none = QPushButton("None")
        btn_all.clicked.connect(lambda: [cb.setChecked(True)  for cb in self._checkboxes])
        btn_none.clicked.connect(lambda: [cb.setChecked(False) for cb in self._checkboxes])
        row.addWidget(btn_all)
        row.addWidget(btn_none)
        row.addStretch()
        layout.addLayout(row)

    def _build_numeric(self, layout: QVBoxLayout, current: FilterSpec | None) -> None:
        self._op_map = _NUM_OPS
        self._op_combo = QComboBox()
        for label, _, _ in _NUM_OPS:
            self._op_combo.addItem(label)
        self._value_edit = QLineEdit()
        self._value_edit.setValidator(QDoubleValidator(-1e12, 1e12, 8, self))
        self._value_edit.setPlaceholderText("Numeric value")
        self._value_edit.returnPressed.connect(self._apply)

        row = QHBoxLayout()
        row.addWidget(self._op_combo)
        row.addWidget(self._value_edit, 1)
        layout.addLayout(row)

        if current and current.op in {op for _, op, _ in _NUM_OPS}:
            idx = next((i for i, (_, op, _) in enumerate(_NUM_OPS) if op == current.op), 0)
            self._op_combo.setCurrentIndex(idx)
            self._value_edit.setText(str(current.value))

    def _build_text(self, layout: QVBoxLayout, current: FilterSpec | None) -> None:
        self._op_map = _TEXT_OPS
        self._op_combo = QComboBox()
        for label, _, _ in _TEXT_OPS:
            self._op_combo.addItem(label)
        self._value_edit = QLineEdit()
        self._value_edit.setPlaceholderText("Value")
        self._value_edit.returnPressed.connect(self._apply)

        row = QHBoxLayout()
        row.addWidget(self._op_combo)
        row.addWidget(self._value_edit, 1)
        layout.addLayout(row)

        if current:
            display_op, raw_text = _decode_text_filter(current)
            idx = next((i for i, (lbl, _, _) in enumerate(_TEXT_OPS) if lbl == display_op), 0)
            self._op_combo.setCurrentIndex(idx)
            self._value_edit.setText(raw_text)

    # ── slots ─────────────────────────────────────────────────────────────

    def _refresh_apply(self) -> None:
        if self._checkboxes:
            self._apply_btn.setEnabled(any(cb.isChecked() for cb in self._checkboxes))

    def focus_editor(self) -> None:
        if self._value_edit:
            self._value_edit.setFocus()
        elif self._checkboxes:
            self._checkboxes[0].setFocus()

    def _apply(self) -> None:
        if self._checkboxes:
            selected = tuple(cb.text() for cb in self._checkboxes if cb.isChecked())
            if not selected:
                return
            if set(selected) == set(self._col.choices):
                self.cleared.emit()
            else:
                self.applied.emit(FilterOperator.IN, selected)
            self.close()
            return

        assert self._op_combo is not None and self._value_edit is not None
        idx            = self._op_combo.currentIndex()
        label, op, tfm = self._op_map[idx]
        text           = self._value_edit.text().strip()
        if not text:
            return
        try:
            if self._col.kind == ColumnKind.INTEGER:
                raw: Any = int(float(text))
            elif self._col.kind == ColumnKind.NUMBER:
                raw = float(text)
            else:
                raw = text
        except ValueError:
            return
        self.applied.emit(op, tfm(raw) if tfm is not None else raw)
        self.close()

    def _clear(self) -> None:
        self.cleared.emit()
        self.close()
