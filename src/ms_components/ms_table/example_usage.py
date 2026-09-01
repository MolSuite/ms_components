"""
example_usage.py
────────────────
Full SmartTableView example with SQLModel.

Models:
    Customer → Order (1:N)

Run:
    pip install pyside6 sqlmodel
    python example_usage.py
"""

import sys
from datetime import date, timedelta
from random import choice, randint, uniform

from sqlalchemy.orm import sessionmaker
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select

from ms_components.ms_table import ColumnDef, AlignHint, SortSpec
from ms_components.ms_table.smart_table_view import (
    SmartTableView,
    TableConfig,
)


# ──────────────────────────────────────────────────────────────
# Modelos SQLModel
# ──────────────────────────────────────────────────────────────

class Customer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str
    country: str
    orders: list["Order"] = Relationship(back_populates="customer")


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id")
    product: str
    total: float
    status: str  # pending | shipped | delivered | cancelled
    order_date: str  # ISO date string, for simplicity

    customer: Customer | None = Relationship(back_populates="orders")


class DemoDB:
    def __init__(self, engine):
        self._session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            class_=Session,
        )

    def get_session(self) -> Session:
        return self._session_factory()


# ──────────────────────────────────────────────────────────────
# Seed data
# ──────────────────────────────────────────────────────────────

COUNTRIES = ["Colombia", "México", "Argentina", "Chile", "España", "Perú"]
PRODUCTS = ["Laptop Pro", "Wireless Mouse", "Mechanical Keyboard",
            "4K Monitor", "BT Headphones", "Webcam", "USB-C Hub"]
STATUSES = ["pending", "shipped", "delivered", "cancelled"]
NAMES = ["Ana García", "Luis Rodríguez", "María López", "Carlos Martínez",
         "Sofía Herrera", "Diego Torres", "Valentina Ramos", "Andrés Flores"]


def seed_database(engine):
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.exec(select(Customer)).first():
            return  # Data already there

        customers = []
        for i, name in enumerate(NAMES):
            c = Customer(
                name=name,
                email=f"{name.split()[0].lower()}@example.com",
                country=choice(COUNTRIES),
            )
            session.add(c)
            customers.append(c)
        session.flush()

        base_date = date.today() - timedelta(days=365)
        for _ in range(200):
            cust = choice(customers)
            session.add(Order(
                customer_id=cust.id,
                product=choice(PRODUCTS),
                total=round(uniform(25.0, 1500.0), 2),
                status=choice(STATUSES),
                order_date=str(base_date + timedelta(days=randint(0, 365))),
            ))
        session.commit()


# ──────────────────────────────────────────────────────────────
# Demo application
# ──────────────────────────────────────────────────────────────

QSS = """
/* ──── Ventana base ──── */
QMainWindow, QWidget { background: #0f1117; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; font-size: 13px; }

/* ──── Tabla ──── */
QTableView#SmartTable {
    background: #161b27;
    alternate-background-color: #1a2035;
    gridline-color: #2d3748;
    border: 1px solid #2d3748;
    border-radius: 8px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QHeaderView::section {
    background: #1e2a3a;
    color: #94a3b8;
    padding: 6px 10px;
    border: none;
    border-right: 1px solid #2d3748;
    border-bottom: 1px solid #2d3748;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
QHeaderView::section:hover { background: #263145; color: #e2e8f0; }

/* ──── Toolbar buttons ──── */
QPushButton#ToolbarBtn {
    background: #1e2a3a;
    color: #94a3b8;
    border: 1px solid #2d3748;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
}
QPushButton#ToolbarBtn:hover { background: #263145; color: #e2e8f0; border-color: #4a5568; }
QPushButton#ToolbarBtn:pressed { background: #1a2035; }

/* ──── Search / Filter ──── */
QLineEdit {
    background: #1e2a3a;
    color: #e2e8f0;
    border: 1px solid #2d3748;
    border-radius: 6px;
    padding: 5px 10px;
}
QLineEdit:focus { border-color: #2563eb; }

/* ──── Filter chips ──── */
QFrame#FilterChip {
    background: #1e3a5f;
    border: 1px solid #2563eb;
    border-radius: 12px;
}
QLabel#ChipLabel { color: #93c5fd; font-size: 12px; }
QPushButton#ChipRemove {
    background: transparent;
    color: #60a5fa;
    border: none;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#ChipRemove:hover { color: #ef4444; }

/* ──── Sort pills ──── */
QFrame#SortChip {
    background: #1a2e1a;
    border: 1px solid #16a34a;
    border-radius: 10px;
}
QLabel#SortLabel { color: #86efac; font-size: 12px; }
QLabel#SortArrow { color: #4ade80; font-weight: bold; }
QPushButton#SortToggle, QPushButton#SortRemove {
    background: transparent;
    color: #4ade80;
    border: none;
    font-size: 12px;
}
QPushButton#SortRemove:hover { color: #ef4444; }

/* ──── Add Filter btn ──── */
QPushButton#AddFilterBtn {
    background: #1e3a5f;
    color: #60a5fa;
    border: 1px solid #2563eb;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
}
QPushButton#AddFilterBtn:hover { background: #1e4a8a; }
QPushButton#ClearFiltersBtn {
    background: transparent;
    color: #94a3b8;
    border: 1px solid #4a5568;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
}
QPushButton#ClearFiltersBtn:hover { color: #ef4444; border-color: #ef4444; }

/* ──── Pagination ──── */
QPushButton#PaginationBtn {
    background: #1e2a3a;
    color: #94a3b8;
    border: 1px solid #2d3748;
    border-radius: 5px;
    font-size: 16px;
    padding: 1px 4px;
}
QPushButton#PaginationBtn:enabled:hover { background: #263145; color: #e2e8f0; }
QPushButton#PaginationBtn:disabled { opacity: 0.35; }
QSpinBox#PageInput {
    background: #1e2a3a;
    color: #e2e8f0;
    border: 1px solid #2d3748;
    border-radius: 5px;
    padding: 2px 4px;
}
QComboBox#PageSizeCombo {
    background: #1e2a3a;
    color: #e2e8f0;
    border: 1px solid #2d3748;
    border-radius: 5px;
    padding: 2px 6px;
}

/* ──── Empty state ──── */
QLabel#EmptyLabel { color: #4a5568; font-size: 15px; padding: 40px; }

/* ──── Column config hint ──── */
QLabel#ColumnConfigHint { color: #64748b; font-size: 11px; padding: 4px; }
QLabel#JoinBadge {
    background: #2d1f5e;
    color: #a78bfa;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
}
QLabel#DragHandle { color: #4a5568; font-size: 16px; }

/* ──── Dialogs ──── */
QDialog { background: #161b27; color: #e2e8f0; }
QFormLayout QLabel { color: #94a3b8; }
QComboBox {
    background: #1e2a3a;
    color: #e2e8f0;
    border: 1px solid #2d3748;
    border-radius: 6px;
    padding: 4px 8px;
}
QComboBox QAbstractItemView {
    background: #1e2a3a;
    color: #e2e8f0;
    selection-background-color: #2563eb;
    border: 1px solid #2d3748;
}
QListWidget {
    background: #1a2035;
    border: 1px solid #2d3748;
    border-radius: 6px;
    color: #e2e8f0;
}
QListWidget::item:hover { background: #263145; }
QListWidget::item:selected { background: #1e3a5f; }
QDialogButtonBox QPushButton {
    background: #2563eb;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 18px;
    min-width: 70px;
}
QDialogButtonBox QPushButton:hover { background: #1d4ed8; }
QDialogButtonBox QPushButton[text="Cancel"],
QDialogButtonBox QPushButton[text="Cancel"] {
    background: #1e2a3a;
    color: #94a3b8;
    border: 1px solid #2d3748;
}
QCheckBox { color: #e2e8f0; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #4a5568; background: #1e2a3a; }
QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
QScrollArea { border: none; }
"""


def status_formatter(value):
    icons = {
        "pending": "⏳ Pendiente",
        "shipped": "🚚 Enviado",
        "delivered": "✅ Entregado",
        "cancelled": "❌ Cancelado",
    }
    return icons.get(value, value)


def main():
    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)

    # In-memory DB for the demo
    engine = create_engine("sqlite:///:memory:", echo=False)
    seed_database(engine)
    db = DemoDB(engine)

    # ── Table configuration ──
    config = TableConfig(
        model_class=Order,
        columns=[
            ColumnDef("id", label="ID", width=60, sortable=True,
                      align=AlignHint.RIGHT),
            ColumnDef("customer.name", label="Customer", width=160, join=Customer,
                      filterable=True),
            ColumnDef("customer.country", label="Country", width=110, join=Customer,
                      filterable=True),
            ColumnDef("product", label="Product", width=180, filterable=True),
            ColumnDef("total", label="Total", width=100, align=AlignHint.RIGHT,
                      formatter=lambda v: f"${float(v):,.2f}"),
            ColumnDef("status", label="Status", width=130,
                      formatter=status_formatter, filterable=True),
            ColumnDef("order_date", label="Date", width=110, align=AlignHint.CENTER),
            ColumnDef("customer.email", label="Email", width=200, join=Customer,
                      visible=False),
        ],
        # default_sort=[SortSpec("id", descending=True)],
        page_size=20,
        page_size_options=[10, 20, 50, 100],
        show_row_numbers=True,
        multi_select=True,
        context_menu_actions={
            "View details": lambda rows: print("View:", [r.id for r in rows]),
            "Mark as shipped": lambda rows: print("Shipped:", [r.id for r in rows]),
        },
        empty_message="No orders match the applied filters",
    )

    # ── Window ──
    window = QMainWindow()
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(0)

    title = QLabel("📦  Order Management")
    title.setStyleSheet("font-size: 20px; font-weight: 700; color: #e2e8f0; padding-bottom: 12px;")
    layout.addWidget(title)

    table = SmartTableView(db=db, config=config)
    table.row_double_clicked.connect(
        lambda obj: print(f"Double click: Order #{obj.id} — {obj.product}")
    )
    layout.addWidget(table)

    window.setCentralWidget(central)
    window.setWindowTitle("SmartTableView — Demo")
    window.resize(1100, 700)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
