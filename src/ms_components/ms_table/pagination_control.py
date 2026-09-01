"""
pagination_control.py
─────────────────────
Compact pagination component (adapted for smart_table).
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSpacerItem, QSpinBox, QWidget
)
from PySide6.QtCore import Qt


class PaginationControl(QWidget):
    """
    Compact, modern pagination.

    Signals:
        page_changed(int)
        items_per_page_changed(int)
    """

    page_changed           = Signal(int)
    items_per_page_changed = Signal(int)

    def __init__(
        self,
        total_items: int = 0,
        items_per_page: int = 20,
        items_per_page_options: list[int] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.total_items     = total_items
        self.items_per_page  = items_per_page
        self.current_page    = 1
        self.total_pages     = 1

        if items_per_page_options is None:
            self.items_per_page_options = [10, 15, 20, 25, 50, 100, 200]
        else:
            self.items_per_page_options = items_per_page_options

        self._setup_ui()
        self.update_pagination()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addStretch()

        # Total
        self.total_items_label = QLabel()
        font = QFont()
        font.setPointSize(10)
        self.total_items_label.setFont(font)
        layout.addWidget(self.total_items_label)

        layout.addItem(QSpacerItem(16, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

        # Prev
        self.prev_btn = QPushButton("‹")
        self.prev_btn.setObjectName("PaginationBtn")
        self.prev_btn.setFixedWidth(28)
        self.prev_btn.clicked.connect(self.previous_page)
        layout.addWidget(self.prev_btn)

        # Page input
        page_container = QWidget()
        page_layout    = QHBoxLayout(page_container)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(4)

        page_layout.addWidget(QLabel("Page"))

        self.page_input = QSpinBox()
        self.page_input.setFixedWidth(54)
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.setObjectName("PageInput")
        line_edit = self.page_input.lineEdit()
        if line_edit:
            line_edit.returnPressed.connect(self.on_page_input_changed)
        self.page_input.editingFinished.connect(self.on_page_input_changed)
        page_layout.addWidget(self.page_input)

        self.of_label = QLabel()
        page_layout.addWidget(self.of_label)

        layout.addWidget(page_container)

        # Next
        self.next_btn = QPushButton("›")
        self.next_btn.setObjectName("PaginationBtn")
        self.next_btn.setFixedWidth(28)
        self.next_btn.clicked.connect(self.next_page)
        layout.addWidget(self.next_btn)

        layout.addItem(QSpacerItem(16, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

        # Items/page
        layout.addWidget(QLabel("Filas:"))

        self.items_per_page_combo = QComboBox()
        self.items_per_page_combo.setObjectName("PageSizeCombo")
        self.items_per_page_combo.setFixedWidth(65)
        for opt in self.items_per_page_options:
            self.items_per_page_combo.addItem(str(opt), opt)
        idx = self.items_per_page_combo.findData(self.items_per_page)
        if idx >= 0:
            self.items_per_page_combo.setCurrentIndex(idx)
        self.items_per_page_combo.currentIndexChanged.connect(self.on_items_per_page_changed)
        layout.addWidget(self.items_per_page_combo)

        layout.addStretch()

    def update_pagination(self):
        if self.total_items == 0:
            self.total_pages = 1
        else:
            self.total_pages = (self.total_items + self.items_per_page - 1) // self.items_per_page

        self.current_page = max(1, min(self.current_page, self.total_pages))

        self.total_items_label.setText(f"Total {self.total_items:,} records")
        self.page_input.setMaximum(self.total_pages)
        self.page_input.setValue(self.current_page)
        self.of_label.setText(f"of {self.total_pages}")

        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def set_total_items(self, total_items: int):
        self.total_items = total_items
        self.update_pagination()

    def set_current_page(self, page: int):
        if 1 <= page <= self.total_pages:
            self.current_page = page
            self.update_pagination()

    def previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.update_pagination()
            self.page_changed.emit(self.current_page)

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_pagination()
            self.page_changed.emit(self.current_page)

    def on_page_input_changed(self):
        page = self.page_input.value()
        if 1 <= page <= self.total_pages and page != self.current_page:
            self.current_page = page
            self.update_pagination()
            self.page_changed.emit(self.current_page)
        else:
            self.page_input.setValue(self.current_page)

    def on_items_per_page_changed(self, index: int):
        new_size = self.items_per_page_combo.currentData()
        if new_size != self.items_per_page:
            first_item = (self.current_page - 1) * self.items_per_page
            self.items_per_page  = new_size
            self.current_page    = (first_item // new_size) + 1
            self.update_pagination()
            self.items_per_page_changed.emit(self.items_per_page)

    def get_current_page(self) -> int:
        return self.current_page

    def get_items_per_page(self) -> int:
        return self.items_per_page
