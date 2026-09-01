from __future__ import annotations
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QWidget, QHBoxLayout, QLabel, QPushButton, QScrollArea


if TYPE_CHECKING:
    from ms_components.ms_table import SortSpec, TableConfig

class SortChip(QFrame):
    """Visual pill for an active SortSpec."""

    toggled = Signal(str)    # field → toggle ASC/DESC
    removed = Signal(str)    # field → remove the sort

    def __init__(self, spec: SortSpec, col_label: str, parent=None):
        super().__init__(parent)
        self._field = spec.field
        self.setObjectName("SortChip")
        self.setProperty('chip_objet', True)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        self._arrow_lbl = QLabel("↓" if spec.descending else "↑")
        self._arrow_lbl.setObjectName("SortArrow")
        layout.addWidget(self._arrow_lbl)

        lbl = QLabel(col_label)
        lbl.setObjectName("SortLabel")
        layout.addWidget(lbl)

        btn_toggle = QPushButton("⇅")
        btn_toggle.setObjectName("SortToggle")
        btn_toggle.setFixedSize(18, 18)
        btn_toggle.setToolTip("Change direction")
        btn_toggle.clicked.connect(lambda: self.toggled.emit(self._field))
        layout.addWidget(btn_toggle)

        btn_remove = QPushButton("×")
        btn_remove.setObjectName("SortRemove")
        btn_remove.setFixedSize(18, 18)
        btn_remove.clicked.connect(lambda: self.removed.emit(self._field))
        layout.addWidget(btn_remove)

    def update_arrow(self, descending: bool):
        self._arrow_lbl.setText("↓" if descending else "↑")


class SortPanel(QWidget):
    """
    Compact bar showing the active sorts as pills, with a combo to add new
    ones.

    Signals:
        sort_changed(list[SortSpec])
    """

    sort_changed = Signal(list)

    def __init__(self, config: TableConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._sorts: list[SortSpec] = list(config.default_sort)
        self._chips: dict[str, SortChip] = {}
        self._setup_ui()
        self._rebuild_chips()

    def _setup_ui(self):
        from PySide6.QtWidgets import QComboBox
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        sort_lbl = QLabel("Order:")
        sort_lbl.setObjectName("SortBarLabel")
        layout.addWidget(sort_lbl)

        # Scroll area for the pills
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
        layout.addWidget(self._chips_scroll, stretch=1)

        # Combo to add a sort
        self._add_combo = QComboBox()
        self._add_combo.setFixedWidth(140)
        self._add_combo.addItem("+ Sort by…", None)
        for c in self._config.columns:
            if c.sortable and c.visible:
                self._add_combo.addItem(c.label, c.field)
        self._add_combo.currentIndexChanged.connect(self._on_add_sort)
        layout.addWidget(self._add_combo)

    def _rebuild_chips(self):
        # Clear the existing chips
        for pill in list(self._chips.values()):
            self._chips_layout.removeWidget(pill)
            pill.deleteLater()
        self._chips.clear()

        for spec in self._sorts:
            col_def = self._config.column_by_field(spec.field)
            label   = col_def.label if col_def else spec.field
            pill    = SortChip(spec, label)
            pill.toggled.connect(self._on_toggle_sort)
            pill.removed.connect(self._on_remove_sort)
            self._chips[spec.field] = pill
            count = self._chips_layout.count()
            self._chips_layout.insertWidget(count - 1, pill)

    def _on_add_sort(self, index: int):
        from ms_components.ms_table import SortSpec  # runtime import (TYPE_CHECKING-only above)

        field = self._add_combo.itemData(index)
        if field is None:
            return
        self._add_combo.setCurrentIndex(0)

        # No duplicar
        if any(s.field == field for s in self._sorts):
            return

        self._sorts.append(SortSpec(field=field, descending=False))
        self._rebuild_chips()
        self.sort_changed.emit(list(self._sorts))

    def _on_toggle_sort(self, field: str):
        for spec in self._sorts:
            if spec.field == field:
                spec.descending = not spec.descending
                if field in self._chips:
                    self._chips[field].update_arrow(spec.descending)
                break
        self.sort_changed.emit(list(self._sorts))

    def _on_remove_sort(self, field: str):
        self._sorts = [s for s in self._sorts if s.field != field]
        self._rebuild_chips()
        self.sort_changed.emit(list(self._sorts))

    def set_sorts(self, sorts: list[SortSpec]):
        self._sorts = list(sorts)
        self._rebuild_chips()

    def get_sorts(self) -> list[SortSpec]:
        return list(self._sorts)

    def summary_text(self) -> str:
        if not self._sorts:
            return "No active sort"
        parts = []
        for spec in self._sorts:
            col_def = self._config.column_by_field(spec.field)
            label = col_def.label if col_def else spec.field
            direction = "DESC" if spec.descending else "ASC"
            parts.append(f"{label} {direction}")
        return " • ".join(parts)