"""
smart_table
───────────
Advanced table component for PySide6 + SQLModel.

Exports:
    SmartTableView     → Main widget.
    TableConfig        → Declarative configuration.
    ColumnDef          → Column definition.
    FilterSpec         → Filter specification.
    FilterOperator     → Comparison operators.
    SortSpec           → Sort specification.
    AlignHint          → Column alignment.
    QueryBuilder       → Direct access to the builder (tests / advanced use).
    SmartTableModel    → Qt model (advanced use / subclassing).
    PaginationControl  → Standalone pagination control.
"""

from .action_header import ActionHeader
from .column_panel import ColumnConfigDialog
from .filter_panel import FilterPanel
from .metric_filter_bar import MetricFilterBar
from .sort_panel import SortPanel
from .pagination_control import PaginationControl
from .query_builder import QueryBuilder
from .session_provider import SessionProvider
from .smart_table_view import SmartTableView
from .table_config import (
    AlignHint,
    ColumnDef,
    ColumnKind,
    FilterOperator,
    FilterSpec,
    SortSpec,
    TableLoadMode,
    TableConfig,
    ToolbarAction,
    choices_from_class,
    DEFAULT_PAGE_SIZE,
    DEFAULT_PAGE_SIZES,
)
from .table_model import SmartTableModel

__all__ = [
    "SmartTableView",
    "SessionProvider",
    "TableConfig",
    "ToolbarAction",
    "ColumnDef",
    "ColumnKind",
    "FilterSpec",
    "FilterOperator",
    "SortSpec",
    "TableLoadMode",
    "AlignHint",
    "ActionHeader",
    "QueryBuilder",
    "SmartTableModel",
    "PaginationControl",
    "FilterPanel",
    "MetricFilterBar",
    "SortPanel",
    "ColumnConfigDialog",
    "DEFAULT_PAGE_SIZE",
    "DEFAULT_PAGE_SIZES",
    "choices_from_class",
]
