"""
column_panel.py
───────────────
Side panel / dialog to configure columns:
  - Toggle visibility
  - Drag & drop to reorder
  - Active-sort indicator (↑↓)

It also exposes SortPanel: a compact row of active-sort "pills" with the option
to add/remove sort columns.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget, QFrame, QScrollArea
)

from .table_config import ColumnDef, SortSpec, TableConfig


# ──────────────────────────────────────────────────────────────
# Column configuration dialog
# ──────────────────────────────────────────────────────────────

class ColumnConfigDialog(QDialog):
    """
    Lets the user:
      1. Enable / disable columns (checkbox)
      2. Reorder them with drag & drop

    On accept it emits the reordered ColumnDef list with updated visibility.
    """

    columns_changed = Signal(list)  # reordered list[ColumnDef]

    def __init__(self, config: TableConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure columns")
        self.setMinimumSize(320, 400)
        self._config = config
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        hint = QLabel("Drag to reorder • Tick to show/hide")
        hint.setObjectName("ColumnConfigHint")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setSpacing(2)

        for col_def in self._config.columns:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, col_def)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
            self._list.addItem(item)

            row_widget = _ColumnRow(col_def)
            item.setSizeHint(row_widget.sizeHint())
            self._list.setItemWidget(item, row_widget)

        layout.addWidget(self._list)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        ordered: list[ColumnDef] = []
        for i in range(self._list.count()):
            item      = self._list.item(i)
            col_def   = item.data(Qt.UserRole)
            row_widget: _ColumnRow = self._list.itemWidget(item)
            col_def.visible = row_widget.is_checked()
            ordered.append(col_def)
        self.columns_changed.emit(ordered)
        self.accept()


class _ColumnRow(QWidget):
    """Row widget inside ColumnConfigDialog."""

    def __init__(self, col_def: ColumnDef, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        drag_icon = QLabel("⣿")
        drag_icon.setObjectName("DragHandle")
        drag_icon.setCursor(Qt.SizeVerCursor)
        layout.addWidget(drag_icon)

        self._check = QCheckBox(col_def.label)
        self._check.setChecked(col_def.visible)
        layout.addWidget(self._check, stretch=1)

        if col_def.is_joined:
            badge = QLabel("JOIN")
            badge.setObjectName("JoinBadge")
            layout.addWidget(badge)

    def is_checked(self) -> bool:
        return self._check.isChecked()


# ──────────────────────────────────────────────────────────────
# Sort Bar: row of active-sort pills
# ──────────────────────────────────────────────────────────────


