"""
table_model.py
──────────────
QAbstractTableModel exposing the dicts returned by QueryBuilder to Qt.

Responsibilities:
  - Feed data to QTableView (data / headerData / flags).
  - Support inline editing when the column is editable.
  - Emit signals when data is refreshed.
  - It never runs queries directly → it delegates to QueryBuilder.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, Qt, Signal
)
from PySide6.QtGui import QColor, QFont

from .table_config import AlignHint, ColumnDef, TableConfig, TableLoadMode


# Custom roles
RAW_OBJECT_ROLE  = Qt.UserRole + 1     # Original SQLModel object
COLUMN_DEF_ROLE  = Qt.UserRole + 2     # ColumnDef of the column


_ALIGN_MAP = {
    AlignHint.LEFT:   Qt.AlignVCenter | Qt.AlignLeft,
    AlignHint.CENTER: Qt.AlignVCenter | Qt.AlignHCenter,
    AlignHint.RIGHT:  Qt.AlignVCenter | Qt.AlignRight,
}


class SmartTableModel(QAbstractTableModel):
    """Qt model for SmartTableView.

    Signals:
        data_loaded(int, int):  (total_items, current_page) after a refresh.
        edit_requested(object, str, object):
            (raw_obj, field_name, new_value) when the user edits a cell.
    """

    data_loaded     = Signal(int, int)
    edit_requested  = Signal(object, str, object)

    def __init__(self, config: TableConfig, parent=None):
        super().__init__(parent)
        self._config:  TableConfig   = config
        self._rows:    list[dict]    = []
        self._total:   int           = 0
        self._total_is_exact: bool   = True
        self._window_start: int      = 0
        self._page:    int           = 1
        self._visible_cols: list[ColumnDef] = config.visible_columns()

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def load_data(
        self,
        rows: list[dict],
        total: int,
        page: int,
        *,
        window_start: int = 0,
        total_is_exact: bool = True,
    ) -> None:
        """Load one page of data. Called by SmartTableView."""
        self.beginResetModel()
        self._rows  = rows
        self._total = total
        self._total_is_exact = bool(total_is_exact)
        self._window_start = max(0, int(window_start))
        self._page  = page
        self._visible_cols = self._config.visible_columns()
        self.endResetModel()
        self.data_loaded.emit(total, page)

    def set_total(self, total: int) -> None:
        """Update only the total (counters/pagination), leaving loaded rows alone."""
        new_total = max(0, int(total))
        old_total = self.rowCount()
        if self._config.load_mode == TableLoadMode.INFINITE and new_total > old_total:
            self.beginInsertRows(QModelIndex(), old_total, new_total - 1)
            self._total = new_total
            self.endInsertRows()
        elif self._config.load_mode == TableLoadMode.INFINITE and new_total < old_total:
            self.beginRemoveRows(QModelIndex(), new_total, old_total - 1)
            self._total = new_total
            self.endRemoveRows()
        else:
            self._total = new_total
        self._total_is_exact = True
        self.data_loaded.emit(self._total, self._page)

    def clear_data(self) -> None:
        self.load_data([], 0, 1)

    def set_column_visible(self, field: str, visible: bool) -> None:
        col_def = self._config.column_by_field(field)
        if col_def and col_def.visible != visible:
            self.beginResetModel()
            col_def.visible = visible
            self._visible_cols = self._config.visible_columns()
            self.endResetModel()

    def get_raw_object(self, row: int) -> Optional[Any]:
        data = self.get_row_data(row)
        return data.get("__raw__") if data is not None else None

    def get_row_data(self, row: int) -> Optional[dict]:
        local = int(row) - self._window_start
        return self._rows[local] if 0 <= local < len(self._rows) else None

    def is_row_loaded(self, row: int) -> bool:
        return self._window_start <= int(row) < self._window_start + len(self._rows)

    @property
    def loaded_count(self) -> int:
        return len(self._rows)

    @property
    def window_start(self) -> int:
        return self._window_start

    @property
    def window_end(self) -> int:
        return self._window_start + len(self._rows)

    @property
    def loaded_rows(self) -> range:
        return range(self._window_start, self.window_end)

    @property
    def total_is_exact(self) -> bool:
        return self._total_is_exact

    @property
    def total_items(self) -> int:
        return self._total

    # ──────────────────────────────────────────
    # QAbstractTableModel overrides
    # ──────────────────────────────────────────

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return self._total if self._config.load_mode == TableLoadMode.INFINITE else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        extra = 1 if self._config.show_row_numbers else 0
        return len(self._visible_cols) + extra

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole
    ) -> Any:
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                if self._config.show_row_numbers:
                    if section == 0:
                        return "#"
                    section -= 1
                if 0 <= section < len(self._visible_cols):
                    return self._visible_cols[section].label
            if role == Qt.TextAlignmentRole:
                return Qt.AlignCenter
            if role == Qt.FontRole:
                f = QFont()
                f.setBold(True)
                return f

        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            # Global row number
            offset = 0 if self._config.load_mode == TableLoadMode.INFINITE else (self._page - 1) * self._config.page_size
            return str(offset + section + 1)

        return None

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.DisplayRole
    ) -> Any:
        if not index.isValid():
            return None

        row_idx = index.row()
        col_idx = index.column()

        # Row-number column
        if self._config.show_row_numbers:
            if col_idx == 0:
                if role == Qt.DisplayRole:
                    offset = 0 if self._config.load_mode == TableLoadMode.INFINITE else (self._page - 1) * self._config.page_size
                    return str(offset + row_idx + 1)
                return None
            col_idx -= 1

        if not (0 <= row_idx < self.rowCount()):
            return None
        if not (0 <= col_idx < len(self._visible_cols)):
            return None

        row_data = self.get_row_data(row_idx)
        if row_data is None:
            return None
        col_def  = self._visible_cols[col_idx]
        value    = row_data.get(col_def.display_key)

        match role:
            case Qt.DisplayRole | Qt.EditRole:
                if value is None:
                    return "—"
                return str(value)

            case Qt.TextAlignmentRole:
                return int(_ALIGN_MAP.get(col_def.align, Qt.AlignVCenter | Qt.AlignLeft))

            case Qt.ToolTipRole:
                if col_def.tooltip is None:
                    return None
                if callable(col_def.tooltip):
                    try:
                        return str(col_def.tooltip(row_data))
                    except Exception:
                        return None
                return str(col_def.tooltip)

            case Qt.BackgroundRole:
                if self._config.alternating_rows and row_idx % 2 == 1:
                    # Subtle colour for alternating rows; the view may override it via QSS
                    return QColor(0, 0, 0, 12)   # semi-transparent
                return None

            case _ if role == RAW_OBJECT_ROLE:
                return row_data.get("__raw__")

            case _ if role == COLUMN_DEF_ROLE:
                return col_def

            case _:
                return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid() or self.get_row_data(index.row()) is None:
            return Qt.NoItemFlags

        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable

        col_idx = index.column()
        if self._config.show_row_numbers:
            if col_idx == 0:
                return base
            col_idx -= 1

        if 0 <= col_idx < len(self._visible_cols):
            if self._visible_cols[col_idx].editable:
                base |= Qt.ItemIsEditable

        return base

    def setData(
        self,
        index: QModelIndex,
        value: Any,
        role: int = Qt.EditRole
    ) -> bool:
        if role != Qt.EditRole or not index.isValid():
            return False

        col_idx = index.column()
        if self._config.show_row_numbers:
            col_idx -= 1

        if not (0 <= col_idx < len(self._visible_cols)):
            return False

        col_def  = self._visible_cols[col_idx]
        raw_obj  = self.get_raw_object(index.row())

        if raw_obj is None or not col_def.editable:
            return False

        # Update the local cache
        local = index.row() - self._window_start
        self._rows[local][col_def.display_key] = value
        self.dataChanged.emit(index, index, [Qt.DisplayRole])

        # Notify the layer above so it can persist to the DB
        self.edit_requested.emit(raw_obj, col_def.field, value)
        return True
