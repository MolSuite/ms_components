"""
filter_panel.py
───────────────
Advanced filter panel with:
  - Visual chips for active filters (with a × button)
  - Quick search bar (ILIKE over filterable columns)
  - A "Filters" button that opens FilterDialog for advanced filters
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget
)

from .table_config import ColumnDef, FilterOperator, FilterSpec, TableConfig


# ──────────────────────────────────────────────────────────────
# Active filter chip
# ──────────────────────────────────────────────────────────────

class FilterChip(QFrame):
    """Visual chip representing an active filter."""

    removed = Signal(str)   # field

    def __init__(self, spec: FilterSpec, parent=None):
        super().__init__(parent)
        self._field = spec.field
        self.setObjectName("FilterChip")
        self.setProperty('chip_objet', True)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        lbl = QLabel(spec.label)
        lbl.setObjectName("ChipLabel")
        layout.addWidget(lbl)

        btn_remove = QPushButton("×")
        btn_remove.setObjectName("ChipRemove")
        btn_remove.setFixedSize(18, 18)
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.clicked.connect(lambda: self.removed.emit(self._field))
        layout.addWidget(btn_remove)


# ──────────────────────────────────────────────────────────────
# Advanced filter dialog
# ──────────────────────────────────────────────────────────────

_OPERATOR_LABELS: dict[FilterOperator, str] = {
    FilterOperator.ILIKE:    "contain",
    FilterOperator.EQ:       "equal to",
    FilterOperator.NEQ:      "not equal to",
    FilterOperator.LT:       "less than",
    FilterOperator.LTE:      "less than or equal",
    FilterOperator.GT:       "greater than",
    FilterOperator.GTE:      "greater than or equal",
    FilterOperator.LIKE:     "LIKE (exact)",
    FilterOperator.IN:       "is in (csv)",
    FilterOperator.IS_NULL:  "is empty",
    FilterOperator.NOT_NULL: "is not empty",
}


class FilterDialog(QDialog):
    """Dialog to create / edit a FilterSpec."""

    def __init__(self, filterable_cols: list[ColumnDef],
                 existing: Optional[FilterSpec] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add filter")
        self.setMinimumWidth(380)
        self._result_spec: Optional[FilterSpec] = None

        layout = QVBoxLayout(self)
        form   = QFormLayout()
        layout.addLayout(form)

        # Field
        self._col_combo = QComboBox()
        for c in filterable_cols:
            self._col_combo.addItem(c.label, c.field)
        if existing:
            idx = self._col_combo.findData(existing.field)
            if idx >= 0:
                self._col_combo.setCurrentIndex(idx)
        form.addRow("Field:", self._col_combo)

        # Operator
        self._op_combo = QComboBox()
        for op, label in _OPERATOR_LABELS.items():
            self._op_combo.addItem(label, op)
        if existing:
            idx = self._op_combo.findData(existing.op)
            if idx >= 0:
                self._op_combo.setCurrentIndex(idx)
        self._op_combo.currentIndexChanged.connect(self._on_op_changed)
        form.addRow("Operator:", self._op_combo)

        # Value
        self._value_input = QLineEdit()
        if existing and existing.value is not None:
            self._value_input.setText(str(existing.value))
        form.addRow("Value:", self._value_input)

        self._on_op_changed()   # Set the initial state

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _current_op(self) -> FilterOperator:
        """Return the current operator as a FilterOperator, even when Qt
        deserialised it as a str."""
        raw = self._op_combo.currentData()
        if isinstance(raw, FilterOperator):
            return raw
        return FilterOperator(raw)   # str → Enum by the Enum's value

    def _on_op_changed(self):
        op = self._current_op()
        no_value_ops = {FilterOperator.IS_NULL, FilterOperator.NOT_NULL}
        self._value_input.setEnabled(op not in no_value_ops)

    def _on_accept(self):
        field = self._col_combo.currentData()
        op    = self._current_op()
        value = self._value_input.text().strip() or None

        if op not in {FilterOperator.IS_NULL, FilterOperator.NOT_NULL} and not value:
            self._value_input.setFocus()
            return

        # Adjust the value for ILIKE
        if op == FilterOperator.ILIKE and value and "%" not in value:
            value = f"%{value}%"

        col_label = self._col_combo.currentText()
        op_label  = _OPERATOR_LABELS.get(op, op.value)
        display_v = "" if value is None else f' "{value.strip("%")}"'
        label     = f'{col_label} {op_label}{display_v}'

        self._result_spec = FilterSpec(field=field, op=op, value=value, label=label)
        self.accept()

    @property
    def result_spec(self) -> Optional[FilterSpec]:
        return self._result_spec


# ──────────────────────────────────────────────────────────────
# Main filter panel
# ──────────────────────────────────────────────────────────────

class FilterPanel(QWidget):
    """
    Filter bar with:
      - Quick search
      - Chips for the active filters
      - A "+ Filter" button that opens FilterDialog

    Signals:
        search_changed(str):        Global search text.
        filter_added(FilterSpec):   New advanced filter.
        filter_removed(str):        Filter removed (field).
        filters_cleared():          All filters cleared.
    """

    search_changed  = Signal(str)
    filter_added    = Signal(object)
    filter_removed  = Signal(str)
    filters_cleared = Signal()

    def __init__(self, config: TableConfig, parent=None, *, show_search: bool = True):
        super().__init__(parent)
        self._config  = config
        self._chips:  dict[str, FilterChip] = {}
        self._show_search = show_search
        self._search_box: QLineEdit | None = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # ── Top row: search + filter button ──
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        if self._show_search:
            self._search_box = QLineEdit()
            filterable_labels = [
                c.label for c in self._config.columns if c.filterable and c.visible
            ]
            if filterable_labels:
                cols_str = ", ".join(filterable_labels[:4])
                suffix   = "…" if len(filterable_labels) > 4 else ""
                placeholder = f"Search in: {cols_str}{suffix}"
            else:
                placeholder = "Quick search…"
            self._search_box.setPlaceholderText(placeholder)
            self._search_box.setClearButtonEnabled(True)
            self._search_box.textChanged.connect(self.search_changed)
            top_row.addWidget(self._search_box, stretch=1)

        self._chips_scroll = QScrollArea()
        self._chips_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._chips_scroll.setFixedHeight(30)
        self._chips_scroll.setWidgetResizable(True)

        self._chips_container = QWidget()
        self._chips_layout    = QHBoxLayout(self._chips_container)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(4)
        self._chips_layout.addStretch()
        self._chips_scroll.setWidget(self._chips_container)

        if self._show_search:
            main_layout.addLayout(top_row)
        else:
            top_row.addWidget(self._chips_scroll, stretch=1)

        self._add_filter_btn = QPushButton("+ Filter")
        self._add_filter_btn.setObjectName("AddFilterBtn")
        self._add_filter_btn.clicked.connect(self._open_filter_dialog)
        top_row.addWidget(self._add_filter_btn)


        if self._show_search:
            main_layout.addWidget(self._chips_scroll)
        else:
            main_layout.addLayout(top_row)

    # ──────────────────────────────────────────
    # Internal slots
    # ──────────────────────────────────────────

    def _open_filter_dialog(self):
        filterable = [c for c in self._config.columns if c.filterable and c.visible]
        if not filterable:
            return
        dlg = FilterDialog(filterable, parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.result_spec:
            self._add_chip(dlg.result_spec)
            self.filter_added.emit(dlg.result_spec)

    def _add_chip(self, spec: FilterSpec):
        # If a chip already exists for that field, replace it
        if spec.field in self._chips:
            old = self._chips.pop(spec.field)
            self._chips_layout.removeWidget(old)
            old.deleteLater()

        chip = FilterChip(spec)
        chip.removed.connect(self._on_chip_removed)
        self._chips[spec.field] = chip

        # Insert before the stretch
        count = self._chips_layout.count()
        self._chips_layout.insertWidget(count - 1, chip)


    def _on_chip_removed(self, field: str):
        chip = self._chips.pop(field, None)
        if chip:
            self._chips_layout.removeWidget(chip)
            chip.deleteLater()

        self.filter_removed.emit(field)

    def _clear_all(self, *, emit_signal: bool = True):
        for chip in list(self._chips.values()):
            self._chips_layout.removeWidget(chip)
            chip.deleteLater()
        self._chips.clear()
        if self._search_box is not None:
            self._search_box.blockSignals(True)
            self._search_box.clear()
            self._search_box.blockSignals(False)

        if emit_signal:
            self.filters_cleared.emit()

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def set_filters(self, specs: list[FilterSpec]) -> None:
        """Show chips for a list of filters (e.g. when restoring state)."""
        self._clear_all(emit_signal=False)
        for spec in specs:
            self._add_chip(spec)

    def get_search_text(self) -> str:
        return self._search_box.text() if self._search_box is not None else ""

    def set_search_text(self, text: str) -> None:
        if self._search_box is None:
            return
        self._search_box.blockSignals(True)
        self._search_box.setText(text)
        self._search_box.blockSignals(False)

    def active_filter_count(self) -> int:
        return len(self._chips)

    def active_filter_labels(self) -> list[str]:
        return [chip.findChild(QLabel, "ChipLabel").text() for chip in self._chips.values()]
