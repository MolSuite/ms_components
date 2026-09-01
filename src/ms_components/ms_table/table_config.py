"""
table_config.py
───────────────
Declarative configuration for SmartTableView.

Typical use:
    config = TableConfig(
        model_class=Order,
        columns=[
            ColumnDef("id", label="ID", width=60),
            ColumnDef("customer.name", label="Customer", join=Customer, editable=False),
            ColumnDef("total", label="Total", formatter=lambda v: f"${v:,.2f}"),
        ],
        default_sort=[SortSpec("id", descending=True)],
        page_size=20,
    )
"""

from __future__ import annotations

import typing
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Type

from sqlmodel import SQLModel


def choices_from_class(cls: type) -> tuple[str, ...]:
    """Extract the string values of a constants class (not an Enum).

    Useful for patterns such as:
        class MoleculeType:
            SMALL_MOLECULE = "small_molecule"
            PROTEIN        = "protein"
    """
    return tuple(
        v for k, v in vars(cls).items()
        if not k.startswith("_") and isinstance(v, str)
    )


# ──────────────────────────────────────────────
# Tipos auxiliares
# ──────────────────────────────────────────────

class FilterOperator(str, Enum):
    EQ        = "="
    NEQ       = "!="
    LT        = "<"
    LTE       = "<="
    GT        = ">"
    GTE       = ">="
    LIKE      = "LIKE"
    ILIKE     = "ILIKE"
    IN        = "IN"
    NOT_IN    = "NOT IN"
    IS_NULL   = "IS NULL"
    NOT_NULL  = "IS NOT NULL"


class AlignHint(str, Enum):
    LEFT   = "left"
    CENTER = "center"
    RIGHT  = "right"


class ColumnKind(str, Enum):
    TEXT    = "text"
    NUMBER  = "number"
    INTEGER = "integer"
    CHOICE  = "choice"


class TableLoadMode(str, Enum):
    PAGINATED = "paginated"
    INFINITE = "infinite"


# ──────────────────────────────────────────────
# ColumnDef
# ──────────────────────────────────────────────

@dataclass
class ColumnDef:
    """Define a visible column in the table.

    Args:
        field:      Path to the field. Supports dot-notation for joins:
                    "customer.name" → resolves Order.customer.name
        label:      Visible header. When None, the capitalised field is used.
        join:       SQLModel class to join in order to resolve this field.
                    May be a list for chained joins.
        width:      Initial width in px (None = auto).
        min_width:  Minimum width in px.
        max_width:  Maximum width in px.
        resizable:  Whether the user may resize it.
        sortable:   Whether the table may be sorted by this column.
        filterable: Whether the column may be filtered.
        editable:   Whether the cell is editable inline.
        visible:    Visible by default.
        align:      Content alignment.
        formatter:  Function (raw_value) → str used for display.
        delegate:   Name of a custom Qt delegate (for editors).
        tooltip:    Static tooltip, or callable(row_data) → str.
        db_column:  Override for the real DB column name (when it differs from field).
        expr:       SQLAlchemy expression producing the column value, for anything
                    that is not a model attribute (JSON_EXTRACT, CASE, func.*).
                    When set, `field` is only the key/label.
    """
    field:      str
    label:      Optional[str]          = None
    join:       Any                    = None   # Type[SQLModel] | list[Type[SQLModel]]
    width:      Optional[int]          = None
    min_width:  int                    = 50
    max_width:  Optional[int]          = None
    resizable:  bool                   = True
    sortable:   bool                   = True
    searchable: bool                   = True
    filterable: bool                   = True
    kind:       ColumnKind             = ColumnKind.TEXT
    choices:    tuple[str, ...]        = ()
    editable:   bool                   = False
    visible:    bool                   = True
    align:      AlignHint              = AlignHint.LEFT
    formatter:  Optional[Callable]     = None
    delegate:   Optional[str]          = None
    tooltip:    Any                    = None   # str | Callable
    db_column:  Optional[str]          = None
    expr:       Any                    = None   # SQLAlchemy ColumnElement

    # ── Fields for rendering widgets inside a cell ──────────────────────
    #
    # paint_factory:   (row_data: dict) → QPixmap | QImage | bytes(SVG) | str(SVG)
    #                  Static rendering via QPainter. Ideal for SVG/images.
    #                  Needs no interaction. Very efficient.
    #
    # widget_factory:  (row_data: dict) → QWidget
    #                  Persistent interactive widget, always visible in the cell.
    #                  Ideal for buttons, badges, combo boxes, etc.
    #
    # editor_factory:  (row_data: dict, parent: QWidget) → QWidget
    #                  Widget shown only when the cell enters edit mode.
    #                  Requires editable=True.
    #
    # editor_signal:   Name of the editor signal that commits the value
    #                  (e.g. "currentTextChanged", "value_changed").
    #
    # editor_getter:   (widget) → Any   Extracts the final value from the editor.
    #
    # cell_height:     Cell height in px for this column (None = default).
    #                  Useful when the content (SVG, image) needs more room.

    paint_factory:   Optional[Callable]     = None
    widget_factory:  Optional[Callable]     = None
    editor_factory:  Optional[Callable]     = None
    editor_signal:   Optional[str]          = None
    editor_getter:   Optional[Callable]     = None
    cell_height:     Optional[int]          = None

    def __post_init__(self):
        if self.label is None:
            # "customer.name" → "Customer Name"
            self.label = self.field.replace(".", " ").replace("_", " ").title()

    @property
    def display_key(self) -> str:
        """Unique key used internally (dots replaced)."""
        return self.field.replace(".", "__")

    @property
    def is_joined(self) -> bool:
        return "." in self.field or self.join is not None


# ──────────────────────────────────────────────
# FilterSpec
# ──────────────────────────────────────────────

@dataclass
class FilterSpec:
    """Specification of an active filter.

    Args:
        field:    Field name (same as ColumnDef.field).
        op:       Comparison operator.
        value:    Value to compare against (None for IS NULL / NOT NULL).
        label:    Friendly label shown in the UI chips.
    """
    field: str
    op:    FilterOperator = FilterOperator.ILIKE
    value: Any            = None
    label: Optional[str] = None

    def __post_init__(self):
        if self.label is None:
            self.label = f"{self.field} {self.op.value} {self.value}"


# ──────────────────────────────────────────────
# SortSpec
# ──────────────────────────────────────────────

@dataclass
class SortSpec:
    """Sort specification.

    Args:
        field:      Field to sort by.
        descending: True = DESC, False = ASC.
    """
    field:      str
    descending: bool = False


# ──────────────────────────────────────────────
# TableConfig
# ──────────────────────────────────────────────

# Predefined table options
DEFAULT_PAGE_SIZES      = [10, 15, 20, 25, 50, 100, 200]
DEFAULT_PAGE_SIZE       = 20
DEFAULT_MAX_EXPORT_ROWS = 10_000


def _auto_detect_kind(model_class: type, col_def: "ColumnDef") -> None:
    """Infer ColumnKind from the SQLAlchemy type / Python annotation."""
    if "." in col_def.field:
        return  # joined column - no direct access to the type

    try:
        from sqlalchemy import BigInteger, Float, Integer, Numeric, SmallInteger
        from sqlalchemy import Enum as SAEnum

        attr = getattr(model_class, col_def.field, None)
        if attr is None:
            return

        col_type = attr.property.columns[0].type

        if isinstance(col_type, (Integer, BigInteger, SmallInteger)):
            col_def.kind = ColumnKind.INTEGER
            return
        if isinstance(col_type, (Float, Numeric)):
            col_def.kind = ColumnKind.NUMBER
            return
        if isinstance(col_type, SAEnum):
            col_def.kind = ColumnKind.CHOICE
            col_def.choices = tuple(col_type.enums)
            return
    except Exception:
        pass

    # Fallback: check the Python annotation (e.g. Optional[SomeEnum])
    try:
        hints = typing.get_type_hints(model_class)
        hint = hints.get(col_def.field)
        if hint is None:
            return
        # Unwrap Optional[X] → X
        if typing.get_origin(hint) is typing.Union:
            args = [a for a in typing.get_args(hint) if a is not type(None)]
            hint = args[0] if args else hint
        if isinstance(hint, type) and issubclass(hint, Enum):
            col_def.kind = ColumnKind.CHOICE
            col_def.choices = tuple(e.value for e in hint)
    except Exception:
        pass


@dataclass
class ToolbarAction:
    """An action injected into the toolbar. Deliberately dumb: the component
    neither interprets `on_click` nor the objects it passes along - it just
    forwards them. All the domain semantics live in the host's closure, which is
    what keeps the table agnostic.

        on_click: callable(selected_objects) - same signature as context_menu_actions.
        icon:     QIcon (opaque to this layer) or None.
    """
    label:    str                                = ""
    icon:     Any                                = None
    on_click: Optional[Callable[[list], None]]   = None
    tooltip:  str                                = ""


@dataclass
class TableConfig:
    """Full configuration of a SmartTableView.

    Args:
        model_class:        Main SQLModel class (base table).
        columns:            List of ColumnDef. Their order is the column order.
        default_sort:       Initial sort.
        default_filters:    Filters active on startup.
        page_size:          Initial items per page.
        page_size_options:  Options offered by the pagination dropdown.
        load_mode:          "paginated" uses PaginationControl; "infinite"
                            loads the next page as the end comes into view.
        infinite_scroll_margin: Distance in px from the end at which more rows
                            are requested.
        max_export_rows:    Row cap for exports.
        selectable:         Allow row selection.
        multi_select:       Allow multi-selection.
        show_row_numbers:   Show the row-number column.
        show_vertical_header: Show Qt's native vertical header.
        show_checkboxes:    Show the selection checkbox column.
        alternating_rows:   Alternate row colours.
        allow_column_reorder: The user may reorder columns by dragging.
        allow_column_resize:  The user may resize columns.
        allow_row_resize:   The user may resize row heights.
        context_menu_actions: Extra context-menu actions.
                              dict[label, callable(selected_rows)]
        row_height:         Row height in px (None = auto).
        empty_message:      Text shown when there are no results.
        compact_controls:   Use a compact toolbar with collapsible panels for
                            filtering and sorting.
        show_filters:       False = "simple" table: no column offers a filter.
        show_search:        False = "simple" table: no column offers a search.
        infinite_cache_pages: Contiguous pages kept in INFINITE mode. Old pages
                              are replaced, so memory does not grow with scroll.
        max_loaded_rows:    Compatibility: extra absolute ceiling for the window.
    """
    model_class:            Type[SQLModel]
    columns:                list[ColumnDef]           = field(default_factory=list)
    default_sort:           list[SortSpec]            = field(default_factory=list)
    default_filters:        list[FilterSpec]          = field(default_factory=list)
    page_size:              int                       = DEFAULT_PAGE_SIZE
    page_size_options:      list[int]                 = field(default_factory=lambda: list(DEFAULT_PAGE_SIZES))
    load_mode:              TableLoadMode | str       = TableLoadMode.PAGINATED
    infinite_scroll_margin: int                       = 120
    infinite_cache_pages:   int                       = 2
    max_export_rows:        int                       = DEFAULT_MAX_EXPORT_ROWS
    selectable:             bool                      = True
    multi_select:           bool                      = True
    show_row_numbers:       bool                      = False
    show_vertical_header:   bool                      = False
    show_checkboxes:        bool                      = False
    alternating_rows:       bool                      = True
    allow_column_reorder:   bool                      = True
    allow_column_resize:    bool                      = True
    allow_row_resize:       bool                      = False
    context_menu_actions:   dict[str, Callable]       = field(default_factory=dict)
    row_height:             Optional[int]             = None
    empty_message:          str                       = "No data to show"
    compact_controls:       bool                      = True
    show_filters:           bool                      = True
    show_search:            bool                      = True
    max_loaded_rows:        int                       = 5_000
    # Embedded controls. Set to False when the host provides them from its own
    # chrome (ribbon + statusbar). The component stays self-sufficient by default
    # through the public API (refresh, open_table_menu, data_refreshed, record_total).
    #   embedded_controls  → Columns, Export, Reload and Settings
    #   show_record_count  → the "N records" label
    embedded_controls:      bool                      = True
    show_record_count:      bool                      = True
    # Toolbar of injected actions, grouped by zone (left / centre / right). The
    # built-ins are laid out as Columns/Export on the left and Reload/Settings on
    # the right. Whatever does not fit falls into a "☰" overflow that opens on
    # hover.
    toolbar_left:           list["ToolbarAction"]     = field(default_factory=list)
    toolbar_center:         list["ToolbarAction"]     = field(default_factory=list)
    toolbar_right:          list["ToolbarAction"]     = field(default_factory=list)
    # Opt-in: collapse the action row behind a hamburger button. Off by default -
    # on data tables a persistent toolbar is more discoverable.
    toolbar_collapsible:    bool                      = False
    # Action offered in the empty state: when the table is filled by one specific
    # action (import, create), a button that triggers it is more useful than
    # `empty_message`. When set it replaces the text. `on_click` receives [].
    empty_action:           Optional["ToolbarAction"]  = None

    def __post_init__(self) -> None:
        self.load_mode = TableLoadMode(self.load_mode)
        self.page_size = max(1, int(self.page_size))
        self.infinite_scroll_margin = max(0, int(self.infinite_scroll_margin))
        self.infinite_cache_pages = max(1, int(self.infinite_cache_pages))
        self.max_loaded_rows = max(self.page_size, int(self.max_loaded_rows))
        for col_def in self.columns:
            # Simple table: turning the per-column flag off is enough, the header honours it.
            if not self.show_filters:
                col_def.filterable = False
            if not self.show_search:
                col_def.searchable = False
            if col_def.kind == ColumnKind.TEXT and not col_def.choices and col_def.expr is None:
                _auto_detect_kind(self.model_class, col_def)

    def visible_columns(self) -> list[ColumnDef]:
        return [c for c in self.columns if c.visible]

    def column_by_field(self, field: str) -> Optional[ColumnDef]:
        return next((c for c in self.columns if c.field == field), None)
