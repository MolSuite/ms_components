from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QIcon, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSpacerItem, QSizePolicy, QPushButton, QSpinBox, QComboBox


class PaginationControl(QWidget):
    """
    Compact, modern pagination control.

    Elements:
    1. Total item count
    2. Previous button (<)
    3. Editable "Page X of Y" input (current page and goto in one)
    4. Next button (>)
    5. Dropdown with the number of items per page

    Signals:
        - page_changed(int): emitted when the page changes
        - items_per_page_changed(int): emitted when items per page changes
    """

    page_changed = Signal(int)
    items_per_page_changed = Signal(int)

    def __init__(self,
                 total_items=0,
                 items_per_page=15,
                 items_per_page_options=None,
                 parent=None):
        super().__init__(parent)

        self.total_items = total_items
        self.items_per_page = items_per_page
        self.current_page = 1
        self.total_pages = 1

        # Default options for items per page
        if items_per_page_options is None:
            self.items_per_page_options = [5, 10, 15, 20, 25, 50, 100]
        else:
            self.items_per_page_options = items_per_page_options

        self.setup_ui()
        self.update_pagination()

    def setup_ui(self):
        """Build the component UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        layout.addStretch()

        # ========== 1. TOTAL ITEMS ==========
        self.total_items_label = QLabel(f"Total {self.total_items:,} items")
        total_font = QFont()
        total_font.setPointSize(10)
        self.total_items_label.setFont(total_font)
        # self.total_items_label.setStyleSheet("color: #495057;")
        layout.addWidget(self.total_items_label)

        # Spacer
        layout.addItem(QSpacerItem(20, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

        # ========== 2. PREVIOUS BUTTON (<) ==========
        self.prev_btn = QPushButton()
        self.prev_btn.setFixedWidth(25)
        self.prev_btn.setIcon(QIcon.fromTheme("go-previous"))
        self.prev_btn.clicked.connect(self.previous_page)
        layout.addWidget(self.prev_btn)

        # ========== 3. INPUT EDITABLE "Page X of Y" ==========
        # Container for the composite input
        page_container = QWidget()
        page_layout = QHBoxLayout(page_container)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(5)

        # Label "Page"
        page_label = QLabel("Page")
        page_layout.addWidget(page_label)

        # Input for the current page (editable)
        self.page_input = QSpinBox()
        self.page_input.setFixedWidth(50)
        self.page_input.setAlignment(Qt.AlignCenter)

        # Enter changes the page
        line_edit = self.page_input.lineEdit()
        if line_edit is not None:
            line_edit.returnPressed.connect(self.on_page_input_changed)
        # Also validate on focus loss
        self.page_input.editingFinished.connect(self.on_page_input_changed)

        page_layout.addWidget(self.page_input)

        # Label "of Y"
        self.of_label = QLabel("of 1")
        # self.of_label.setStyleSheet("color: #495057; font-size: 13px;")
        page_layout.addWidget(self.of_label)

        layout.addWidget(page_container)

        # ========== 4. NEXT BUTTON (>) ==========
        self.next_btn = QPushButton()
        self.next_btn.setFixedWidth(25)
        self.next_btn.setIcon(QIcon.fromTheme("go-next"))
        self.next_btn.clicked.connect(self.next_page)
        layout.addWidget(self.next_btn)

        # Spacer
        layout.addItem(QSpacerItem(20, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

        # ========== 5. DROPDOWN - ITEMS PER PAGE ==========
        items_label = QLabel("Items/page:")
        # items_label.setStyleSheet("color: #495057; font-size: 13px;")
        layout.addWidget(items_label)

        self.items_per_page_combo = QComboBox()
        self.items_per_page_combo.setFixedWidth(60)
        # self.items_per_page_combo.setFixedHeight(35)

        # Add the options
        for option in self.items_per_page_options:
            self.items_per_page_combo.addItem(str(option), option)

        # Select the initial value
        index = self.items_per_page_combo.findData(self.items_per_page)
        if index >= 0:
            self.items_per_page_combo.setCurrentIndex(index)

        self.items_per_page_combo.currentIndexChanged.connect(self.on_items_per_page_changed)
        layout.addWidget(self.items_per_page_combo)

        # Flexible spacer at the end
        layout.addStretch()

    def update_pagination(self):
        """Refresh the pagination state."""
        # Compute the total number of pages
        if self.total_items == 0:
            self.total_pages = 1
        else:
            self.total_pages = (self.total_items + self.items_per_page - 1) // self.items_per_page

        # Make sure current_page stays within a valid range
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        if self.current_page < 1:
            self.current_page = 1

        # Refresh labels and inputs
        self.total_items_label.setText(f"Total {self.total_items:,} items")
        self.page_input.setValue(self.current_page)
        self.of_label.setText(f"of {self.total_pages}")

        # Refresh button state
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

        # Refresh the input validator
        self.page_input.setMaximum(self.total_pages)

    def set_total_items(self, total_items):
        """Set the total item count."""
        self.total_items = total_items
        self.update_pagination()

    def set_current_page(self, page):
        """Set the current page."""
        if 1 <= page <= self.total_pages:
            self.current_page = page
            self.update_pagination()

    def previous_page(self):
        """Go to the previous page."""
        if self.current_page > 1:
            self.current_page -= 1
            self.update_pagination()
            self.page_changed.emit(self.current_page)

    def next_page(self):
        """Go to the next page."""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_pagination()
            self.page_changed.emit(self.current_page)

    def on_page_input_changed(self):
        """Handle a direct change in the page input."""
        page = int(self.page_input.value())
        if 1 <= page <= self.total_pages:
            if page != self.current_page:
                self.current_page = page
                self.update_pagination()
                self.page_changed.emit(self.current_page)
            return

        # If it ends up out of range for any reason, restore the previous value.
        self.page_input.setValue(self.current_page)

    def on_items_per_page_changed(self, index):
        """Handle a change of items per page."""
        new_items_per_page = self.items_per_page_combo.currentData()
        if new_items_per_page != self.items_per_page:
            self.items_per_page = new_items_per_page

            # Work out which page we land on after the change,
            # trying to keep the first item of the current page visible
            first_item_index = (self.current_page - 1) * self.items_per_page
            self.current_page = (first_item_index // new_items_per_page) + 1

            self.update_pagination()
            self.items_per_page_changed.emit(self.items_per_page)

    def get_current_page(self):
        """Return the current page."""
        return self.current_page

    def get_items_per_page(self):
        """Return the items per page."""
        return self.items_per_page
