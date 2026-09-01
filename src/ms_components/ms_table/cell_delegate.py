"""
cell_delegate.py
────────────────
Generic delegate that renders any QWidget inside a SmartTableView cell.

Two usage modes, depending on what you set in ColumnDef:

──────────────────────────────────────────────────────────────────────────────
MODE 1 — PERSISTENT WIDGET (interactive, always visible)
──────────────────────────────────────────────────────────────────────────────
    The widget is created once per visible row and lives in the cell.
    Good for: buttons, combos, checkboxes, stateful badges.

    ColumnDef(
        field="status",
        label="Status",
        widget_factory=lambda row_data: StatusBadge(row_data["status"]),
    )

──────────────────────────────────────────────────────────────────────────────
MODE 2 — PAINT DELEGATE (static rendering via QPainter)
──────────────────────────────────────────────────────────────────────────────
    The widget is rendered as an image on every repaint. No direct interaction,
    but very efficient for read-only cells (SVGs, images).

    ColumnDef(
        field="smiles",
        label="Molecule",
        width=200,
        row_height=120,             # in TableConfig or ColumnDef
        paint_factory=lambda row_data: render_mol_svg(row_data["smiles"]),
        # paint_factory may return: QPixmap | QImage | QSvgRenderer | bytes(svg)
    )

──────────────────────────────────────────────────────────────────────────────
MODE 3 — ON-DEMAND EDITOR (created on click / double click)
──────────────────────────────────────────────────────────────────────────────
    The widget only exists while the cell is being edited.
    Good for: dropdowns, date pickers, colour pickers.

    ColumnDef(
        field="priority",
        label="Priority",
        editable=True,
        editor_factory=lambda row_data, parent: PriorityCombo(
            current=row_data["priority"], parent=parent
        ),
        editor_signal="value_changed",   # signal that commits the value
        editor_getter=lambda w: w.current_value(),
    )

──────────────────────────────────────────────────────────────────────────────
Every factory receives `row_data: dict` with the full row
(including "__raw__", the original SQLModel object).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QModelIndex, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap, QImage
from PySide6.QtWidgets import (
    QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QWidget,
)

# from .table_model import RAW_OBJECT_ROLE, COLUMN_DEF_ROLE


# ──────────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ──────────────────────────────────────────────────────────────────────────────

def _to_pixmap(source: Any, size: QSize) -> Optional[QPixmap]:
    """
    Convert several source types into a QPixmap ready to paint.

    Accepts:
      - QPixmap
      - QImage
      - bytes / str  →  treated as SVG
      - an object with a .render() method (QSvgRenderer)
      - callable()   →  called, and its result processed recursively
    """
    if source is None:
        return None

    if callable(source) and not isinstance(source, type):
        return _to_pixmap(source(), size)

    if isinstance(source, QPixmap):
        return source.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    if isinstance(source, QImage):
        return QPixmap.fromImage(source).scaled(
            size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

    if isinstance(source, (bytes, str)):
        # Treat it as SVG
        try:
            from PySide6.QtSvg import QSvgRenderer
            svg_bytes = source.encode() if isinstance(source, str) else source
            renderer = QSvgRenderer(svg_bytes)
            default_size = renderer.defaultSize()
            render_size = default_size.scaled(size, Qt.KeepAspectRatio) if default_size.isValid() else size
            pixmap = QPixmap(render_size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter, QRectF(0, 0, render_size.width(), render_size.height()))
            painter.end()
            return pixmap
        except Exception:
            return None

    # QSvgRenderer, or any object with .render(QPainter)
    if hasattr(source, "render"):
        try:
            default_size = source.defaultSize() if hasattr(source, "defaultSize") else size
            render_size = default_size.scaled(size, Qt.KeepAspectRatio) if default_size.isValid() else size
            pixmap  = QPixmap(render_size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            source.render(painter, QRectF(0, 0, render_size.width(), render_size.height()))
            painter.end()
            return pixmap
        except Exception:
            return None

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Delegate principal
# ──────────────────────────────────────────────────────────────────────────────

class CellWidgetDelegate(QStyledItemDelegate):
    """
    Delegate that hands cell rendering/editing to the factories declared in
    ColumnDef.

    Instantiated automatically by SmartTableView — you rarely need to use it
    directly outside very custom cases.
    """

    def __init__(self, col_index: int, col_def, parent: QWidget | None = None):
        """
        Args:
            col_index:  Logical index of the column in the view.
            col_def:    ColumnDef holding the configured factories.
        """
        super().__init__(parent)
        self._col_index = col_index
        self._col_def   = col_def

        # Persistent widget cache: row → QWidget
        # Invalidated when the page changes (load_data)
        self._persistent_widgets: dict[int, QWidget] = {}

    # ── Invalidate the cache on page change ───────────────────────────────

    def clear_widget_cache(self):
        for w in self._persistent_widgets.values():
            w.setParent(None)
            w.deleteLater()
        self._persistent_widgets.clear()

    # ── PAINT (static mode or persistent widget) ──────────────────────────

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        col_def = self._col_def

        # Standard selection background
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, option.widget)

        row_data = self._get_row_data(index)

        # ── paint_factory mode (SVG / image) ───────────────────────────────
        if col_def.paint_factory is not None:
            try:
                source  = col_def.paint_factory(row_data)
                padding = 6
                target  = QSize(
                    option.rect.width()  - padding * 2,
                    option.rect.height() - padding * 2,
                )
                pixmap = _to_pixmap(source, target)
                if pixmap:
                    # Centre it in the cell
                    x = option.rect.x() + (option.rect.width()  - pixmap.width())  // 2
                    y = option.rect.y() + (option.rect.height() - pixmap.height()) // 2
                    painter.drawPixmap(x, y, pixmap)
                    return
            except Exception as e:
                pass  # Fall back to text

        # ── widget_factory mode (persistent, managed by the view) ──────────
        # The widget lives in the view; paint only draws the background
        if col_def.widget_factory is not None:
            return   # sizeHint + view.setIndexWidget manage the widget

        # ── Fallback: plain text ───────────────────────────────────────────
        super().paint(painter, option, index)

    # ── SIZE HINT ──────────────────────────────────────────────────────────

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        col_def = self._col_def
        base    = super().sizeHint(option, index)

        if col_def.cell_height is not None:
            return QSize(base.width(), col_def.cell_height)
        return base

    # ── EDITOR (editor_factory mode) ──────────────────────────────────────

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> Optional[QWidget]:
        col_def = self._col_def
        if col_def.editor_factory is None:
            return super().createEditor(parent, option, index)

        row_data = self._get_row_data(index)
        try:
            editor = col_def.editor_factory(row_data, parent)
            # Connect the commit signal if one is defined
            if col_def.editor_signal and hasattr(editor, col_def.editor_signal):
                signal = getattr(editor, col_def.editor_signal)
                signal.connect(lambda *_: self.commitData.emit(editor))
            return editor
        except Exception:
            return super().createEditor(parent, option, index)

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        col_def = self._col_def
        if col_def.editor_factory is None:
            super().setEditorData(editor, index)
            return
        # The factory already set the initial state; nothing else to do.

    def setModelData(
        self,
        editor: QWidget,
        model,
        index: QModelIndex,
    ) -> None:
        col_def = self._col_def
        if col_def.editor_getter is None:
            super().setModelData(editor, model, index)
            return
        try:
            value = col_def.editor_getter(editor)
            model.setData(index, value, Qt.EditRole)
        except Exception:
            super().setModelData(editor, model, index)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _get_row_data(self, index: QModelIndex) -> dict:
        """Get the row data dict from the model."""
        model = index.model()
        # Try to get raw_data directly
        if hasattr(model, "get_row_data"):
            data = model.get_row_data(index.row())
            return data or {}
        return {}
