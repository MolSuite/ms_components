"""
smart_table_view.py
───────────────────
Main widget orchestrating:
  FilterPanel + SortPanel + QTableView + PaginationControl

Usage:
    from sqlmodel import Session, create_engine
    from sqlalchemy.orm import sessionmaker
    from smart_table import SmartTableView, TableConfig, ColumnDef, SortSpec

    engine  = create_engine("sqlite:///mydb.db")

    class DB:
        def __init__(self, engine):
            self._session_factory = sessionmaker(bind=engine, class_=Session)

        def get_session(self):
            return self._session_factory()

    db = DB(engine)

    config = TableConfig(
        model_class=Order,
        columns=[
            ColumnDef("id",            label="ID",       width=60),
            ColumnDef("customer.name", label="Cliente",  join=Customer),
            ColumnDef("total",         label="Total",    align=AlignHint.RIGHT,
                      formatter=lambda v: f"${float(v):,.2f}"),
            ColumnDef("status",        label="Status"),
        ],
        default_sort=[SortSpec("id", descending=True)],
        page_size=20,
        show_row_numbers=True,
    )

    table = SmartTableView(db=db, config=config)
    table.row_double_clicked.connect(lambda obj: print("Open:", obj))
    layout.addWidget(table)
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import (
    QByteArray, QEvent, QItemSelectionModel, QObject, QRunnable, QSize,
    QSortFilterProxyModel, Qt, QThreadPool, QTimer, Signal,
)
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QMenu, QPushButton, QSizePolicy, QFrame,
    QTableView, QToolBar, QToolButton, QVBoxLayout, QWidget
)
from ..backdrop import Backdrop
from .action_header import ActionHeader, FilterPopup, SearchPopup
from .cell_delegate import CellWidgetDelegate
from .column_panel import ColumnConfigDialog
from .pagination_control import PaginationControl
from .query_builder import QueryBuilder
from .session_provider import SessionProvider
from .table_config import ColumnDef, ColumnKind, FilterOperator, FilterSpec, SortSpec, TableConfig, TableLoadMode, ToolbarAction
from .table_model import COLUMN_DEF_ROLE, RAW_OBJECT_ROLE, SmartTableModel
from .table_interaction import TableInteraction

_TOOLBAR_ICONS = Path(__file__).parent / "icons"


class _Delivery(QObject):
    """Carries a worker's result back to the GUI thread (queued signal)."""
    done = Signal(object, object)


class _Query(QRunnable):
    def __init__(self, fn, finish, delivery: _Delivery):
        super().__init__()
        self._fn, self._finish, self._delivery = fn, finish, delivery

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # re-raised on the GUI thread, like a synchronous query
            result = exc
        self._delivery.done.emit(self._finish, result)


class SmartTableView(QWidget):
    """
    Smart table with pagination, filtering, sorting and column configuration.

    Signals:
        cell_pressed(object, str, Qt.KeyboardModifiers):
            (raw_obj, field, modifiers) before a left press changes the selection.
        row_clicked(object):          SQLModel object for the clicked row.
        row_reselected(object):       An already selected row was clicked again.
        row_double_clicked(object):   SQLModel object for the double-clicked row.
        selection_changed(list):      List of selected objects.
        edit_committed(object, str, object):
            (raw_obj, field, new_value) when an inline edit is committed.
        data_refreshed(int):          Total item count after each load.
    """

    cell_pressed        = Signal(object, str, Qt.KeyboardModifiers)
    row_clicked         = Signal(object)
    row_reselected      = Signal(object)
    row_double_clicked  = Signal(object)
    selection_changed   = Signal(list)
    edit_committed      = Signal(object, str, object)
    data_refreshed      = Signal(int)
    refresh_clicked     = Signal()   # user pressed the toolbar refresh button
    view_state_changed  = Signal()   # visible columns or sort changed interactively

    def __init__(
        self,
        db: SessionProvider,
        config: TableConfig,
        parent=None
    ):
        super().__init__(parent)
        self._db      = db
        self._config  = config
        self._builder = QueryBuilder(db, config)
        self._model   = SmartTableModel(config)
        self._loading_more = False
        self._infinite_autofill_scheduled = False
        self._infinite_pages: dict[int, list[dict]] = {}
        self._infinite_page_cursors: dict[int, tuple | None] = {0: None}
        self._infinite_has_more = False
        self._infinite_frontier_page = 0
        self._infinite_total_hint = 0
        self._infinite_total_exact = True
        # How far the scroll has reached, in rows. Not `loaded_count`: the window drops
        # pages behind the cursor, so that one shrinks while this keeps growing.
        self._infinite_loaded_end = 0
        # Bumped whenever the query changes: a worker's result from an older one is dropped.
        self._generation = 0
        self._jumps_in_flight = 0
        self._delivery = _Delivery(self)
        self._delivery.done.connect(lambda finish, result: finish(result))
        self._active_popup: QWidget | None = None

        self._setup_ui()
        self._connect_signals()
        self._update_control_summaries()
        self._sync_header()
        self.refresh()                  # Initial load

    def is_user_interacting(self) -> bool:
        scrollbars = (
            self._table.verticalScrollBar(),
            self._table.horizontalScrollBar(),
        )
        if any(bar.isSliderDown() for bar in scrollbars):
            return True
        if self._table.hasFocus():
            return True
        state = self._table.state()
        return state != QAbstractItemView.NoState

    def background_refresh(self) -> bool:
        if self.is_user_interacting():
            return False
        self.refresh_preserving_view()
        return True

    def refresh_counts(self) -> bool:
        """Refresh only the record counter (COUNT), without reloading rows.

        Meant for running jobs: the user watches the total grow and infinite scroll
        knows there are more pages, but the visible rows do not shift under the
        cursor. Returns False when the table is empty (nothing to preserve: the
        host should do a plain refresh()).
        """
        if self._model.loaded_count == 0:
            return False
        self._run_async(self._builder.count, self._apply_count)
        return True

    def _apply_count(self, total: int) -> None:
        if self._is_infinite_mode():
            self._infinite_total_hint = total
            self._infinite_total_exact = True
            self._infinite_has_more = self._infinite_loaded_end < total
            tail = self._infinite_pages.get(self._infinite_frontier_page)
            if tail is not None and len(tail) < self._builder.page_size and self._infinite_has_more:
                # The last page came back short and rows were added since: forget it, so the
                # autofill set_total() triggers fetches it again once it is in view. Kept, its
                # rows past the old end would stay blank forever.
                del self._infinite_pages[self._infinite_frontier_page]
                # The next page's cursor is the short page's last row: wrong now, so it is
                # found by offset instead.
                self._infinite_page_cursors.pop(self._infinite_frontier_page + 1, None)
        self._model.set_total(total)

    def _viewport_row_capacity(self) -> int:
        """How many rows fit in the visible viewport (minimum 1)."""
        row_height = self._table.rowHeight(0) if self._model.loaded_count else 0
        if row_height <= 0:
            row_height = self._table.verticalHeader().defaultSectionSize() or 24
        return max(1, self._table.viewport().height() // row_height)

    def ensure_viewport_filled(self, *, force: bool = False) -> bool:
        """One tick of a job's start-up: reload rows only once there are enough to
        fill the visible viewport (or once the host decides it has waited long
        enough, force=True).

        Returns True when the viewport is full (or there is nothing else to fetch):
        the host then switches to "counters only" mode. False = still waiting, call
        again.
        """
        loaded = self._model.loaded_count
        capacity = self._viewport_row_capacity()
        if loaded >= capacity:
            return True
        total = self._builder.count()
        if not force and total < capacity:
            return False  # not enough molecules yet to fill the view
        if total <= loaded:
            return force
        self.refresh()
        return force or self._model.loaded_count >= capacity

    def refresh_preserving_view(self) -> None:
        vertical_scroll = self._table.verticalScrollBar().value()
        horizontal_scroll = self._table.horizontalScrollBar().value()
        selected_ids = self._selected_object_ids()
        if self._is_infinite_mode():
            page_index = max(0, vertical_scroll // self._builder.page_size)
            cursor = self._infinite_page_cursors.get(page_index, False)
            self._new_generation()

            def show(result) -> None:
                rows, has_more = result
                self._infinite_pages = {page_index: rows}
                self._infinite_page_cursors = {page_index: cursor} if cursor is not False else {}
                self._infinite_page_cursors.setdefault(0, None)
                if rows:
                    self._infinite_page_cursors[page_index + 1] = self._builder.cursor_of(rows[-1])
                end = page_index * self._builder.page_size + len(rows)
                self._infinite_frontier_page = page_index
                self._infinite_loaded_end = end
                self._infinite_has_more = has_more
                self._infinite_total_hint = max(self._infinite_total_hint, end + int(has_more))
                self._model.load_data(
                    rows,
                    self._infinite_total_hint,
                    page_index + 1,
                    window_start=page_index * self._builder.page_size,
                    total_is_exact=self._infinite_total_exact,
                )
                self._restore_selected_object_ids(selected_ids)
                self._table.verticalScrollBar().setValue(vertical_scroll)
                self._table.horizontalScrollBar().setValue(horizontal_scroll)

            if cursor is not False:  # the page's own cursor: a keyset seek, cheap enough here
                show(self._builder.fetch_window_after(cursor))
            else:
                self._jump(lambda: self._builder.fetch_window_at(page_index), show)
            self._run_async(self._builder.count, self._apply_count)
            return
        current_page = self._builder.current_page

        rows, total, page = self._fetch_loaded_window()
        self._model.load_data(rows, total, page)
        self._restore_selected_object_ids(selected_ids)
        self._table.verticalScrollBar().setValue(vertical_scroll)
        self._table.horizontalScrollBar().setValue(horizontal_scroll)

    def patch_loaded_rows(self, key: str, patches: dict[Any, dict[str, Any]]) -> bool:
        """Patch visible cached rows by a raw-object/key value; no model reset or reselection."""
        changed = False
        for row in self._model.loaded_rows:
            data = self._model.get_row_data(row) or {}
            raw = data.get("__raw__")
            identity = data.get(key, getattr(raw, key, None))
            values = patches.get(identity)
            if values is not None:
                changed = self._model.patch_loaded_row(row, values) or changed
        return changed

    # ──────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar (opcional) ───────────────
        # embedded_controls → Columns, Export, Reload and Settings;
        # show_record_count → the count label.
        # The host may turn them off and drive everything from a ribbon + statusbar;
        # the component stays usable via open_table_menu(), refresh() and the
        # data_refreshed signal.
        self._refresh_btn = None
        self._export_btn = None
        self._columns_action = None
        self._settings_action = None
        self._refresh_action = None
        self._export_action = None
        self._builtin_actions: list[QAction] = []
        self._builtin_action_icons: dict[QAction, str] = {}
        self._overflow_btn = None
        self._result_count_label = None
        self._selected_count = 0
        self._collapse_btn = None
        self._toolbar = None
        self._toolbar_row = None
        self._injected_actions: list[tuple[ToolbarAction, QAction]] = []
        self._keyed_actions: dict[str, list[QAction]] = {}
        # False while a host has lent the table out (see set_config_actions_visible).
        self._config_actions_visible = True
        self._zone_anchor: QAction | None = None
        self._actions_collapsed = self._config.toolbar_collapsible

        cfg = self._config
        if (cfg.embedded_controls or cfg.show_record_count
                or cfg.toolbar_left or cfg.toolbar_center or cfg.toolbar_right):
            root.addWidget(self._build_toolbar())

        # ── Table View ───────────────────────
        self._table = QTableView()
        self._table.setModel(self._model)
        self._input = TableInteraction(self._table)
        self._input.pressed.connect(self._on_cell_pressed)
        self._input.reselected.connect(lambda _view, index, _mods: self.row_reselected.emit(index.data(RAW_OBJECT_ROLE)))
        self._table.setObjectName("SmartTable")

        sel_mode = (QAbstractItemView.ExtendedSelection
                    if self._config.multi_select
                    else QAbstractItemView.SingleSelection)
        self._table.setSelectionMode(sel_mode)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.DoubleClicked |
                                    QAbstractItemView.SelectedClicked)
        self._table.setAlternatingRowColors(self._config.alternating_rows)
        self._table.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
        self._table.setSortingEnabled(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.doubleClicked.connect(self._on_double_click)

        # ActionHeader replaces the native header
        self._header = ActionHeader(self._config, self._table)
        self._table.setHorizontalHeader(self._header)
        self._header.setSectionResizeMode(QHeaderView.Interactive)
        self._header.setStretchLastSection(True)
        if self._config.allow_column_reorder:
            self._header.setSectionsMovable(True)

        v_header = self._table.verticalHeader()
        if self._config.row_height:
            v_header.setDefaultSectionSize(self._config.row_height)
        v_header.setVisible(self._config.show_vertical_header)
        v_header.setSectionResizeMode(
            QHeaderView.Interactive if self._config.allow_row_resize else QHeaderView.Fixed
        )

        self._apply_column_widths()
        self._apply_dynamic_row_height()

        self._delegates: dict[int, CellWidgetDelegate] = {}
        self._install_delegates()

        root.addWidget(self._table, stretch=1)
        self._loading_overlay = QLabel("Loading…", self._table.viewport())
        self._loading_overlay.setAlignment(Qt.AlignCenter)
        self._loading_overlay.setAutoFillBackground(True)
        self._loading_overlay.hide()

        # ── Empty state overlay ──────────────
        # With `empty_action`, a button sits under the message and triggers the
        # action that fills the table (import, create): the text says what is
        # happening, the button fixes it.
        self._empty_label = QLabel(self._config.empty_message)
        self._empty_label.setObjectName("EmptyLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        action = self._config.empty_action
        if action is None and self._config.empty_backdrop is None:
            self._empty_widget = self._empty_label
        else:
            self._empty_widget = Backdrop(self._config.empty_backdrop, opacity=0.08)
            empty_layout = QVBoxLayout(self._empty_widget)
            empty_layout.setAlignment(Qt.AlignCenter)
            empty_layout.setSpacing(12)
            self._empty_label.setStyleSheet("font-size: 16px;")
            empty_layout.addWidget(self._empty_label)
        if action is not None:
            button = QPushButton(action.label)
            button.setObjectName("EmptyActionButton")
            if action.icon is not None:
                button.setIcon(action.icon)
            button.setToolTip(action.tooltip or action.label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet("font-size: 15px; padding: 8px 24px;")
            if action.on_click is not None:
                button.clicked.connect(lambda _=False, cb=action.on_click: cb([]))
            empty_layout.addSpacing(16)
            empty_layout.addWidget(button, alignment=Qt.AlignCenter)
        self._empty_widget.setVisible(False)
        root.addWidget(self._empty_widget, stretch=1)

        # ── Pagination ───────────────────────
        self._pagination = PaginationControl(
            total_items=0,
            items_per_page=self._config.page_size,
            items_per_page_options=self._config.page_size_options,
        )
        self._pagination.setContentsMargins(0, 4, 0, 8)
        self._pagination.setVisible(not self._is_infinite_mode())
        root.addWidget(self._pagination)

    def _is_infinite_mode(self) -> bool:
        return self._config.load_mode == TableLoadMode.INFINITE

    def _install_delegates(self):
        """Install CellWidgetDelegate on the columns that define a factory."""
        default_delegate = self._table.itemDelegate()
        for logical_idx, delegate in self._delegates.items():
            delegate.clear_widget_cache()
            if default_delegate is not None:
                self._table.setItemDelegateForColumn(logical_idx, default_delegate)
        self._delegates.clear()
        visible = self._config.visible_columns()
        offset  = 1 if self._config.show_row_numbers else 0

        for i, col_def in enumerate(visible):
            has_delegate = (
                col_def.paint_factory  is not None or
                col_def.widget_factory is not None or
                col_def.editor_factory is not None or
                col_def.cell_height    is not None or
                col_def.kind == ColumnKind.PROGRESS
            )
            if has_delegate:
                logical_idx = i + offset
                delegate = CellWidgetDelegate(logical_idx, col_def, self._table)
                self._table.setItemDelegateForColumn(logical_idx, delegate)
                self._delegates[logical_idx] = delegate
        self._apply_dynamic_row_height()

    def _apply_dynamic_row_height(self):
        visible = self._config.visible_columns()
        dynamic_height = max(
            (int(col.cell_height) for col in visible if col.cell_height is not None),
            default=0,
        )
        if dynamic_height > 0:
            self._table.verticalHeader().setDefaultSectionSize(dynamic_height)
            return
        if self._config.row_height:
            self._table.verticalHeader().setDefaultSectionSize(self._config.row_height)
            return
        self._table.verticalHeader().setDefaultSectionSize(30)

    def _refresh_persistent_widgets(self):
        """
        For columns with a widget_factory: place the widget in every visible cell.
        Called after each load_data.
        """
        visible = self._config.visible_columns()
        offset  = 1 if self._config.show_row_numbers else 0

        # Clear previous widgets on delegates that have a widget_factory
        for delegate in self._delegates.values():
            delegate.clear_widget_cache()

        for i, col_def in enumerate(visible):
            if col_def.widget_factory is None:
                continue

            logical_idx = i + offset

            for row in self._model.loaded_rows:
                index = self._model.index(row, logical_idx)
                row_data = self._model.get_row_data(row) or {}
                try:
                    widget = col_def.widget_factory(row_data)
                    if widget is not None:
                        self._table.setIndexWidget(index, widget)
                        # Keep a reference on the delegate for cleanup
                        if logical_idx in self._delegates:
                            self._delegates[logical_idx]._persistent_widgets[row] = widget
                except Exception as e:
                    import traceback; traceback.print_exc()

    def _apply_column_widths(self):
        visible = self._config.visible_columns()
        h       = self._table.horizontalHeader()

        offset = 1 if self._config.show_row_numbers else 0

        for i, col_def in enumerate(visible):
            idx = i + offset
            if col_def.width:
                h.resizeSection(idx, col_def.width)
            if col_def.min_width:
                h.setMinimumSectionSize(col_def.min_width)

    # ──────────────────────────────────────────
    # Full menu for external hosts
    # ──────────────────────────────────────────

    def open_table_menu(self, anchor: QWidget | None = None) -> None:
        """Pop up the full menu for external hosts (a ribbon, for instance).

        The embedded toolbar exposes these options as actions of its own.
        ``anchor`` lets another host open the same collection under one of its own
        controls.
        """
        menu = QMenu(self)
        columns_action = menu.addAction("Columns", self._open_column_config)
        columns_action.setIcon(self._toolbar_icon("columns.svg"))
        menu.addMenu(self._create_export_menu(menu))
        if self._toolbar is not None:
            menu.addMenu(self._create_toolbar_style_menu(menu))

        if anchor is not None:
            menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        else:
            from PySide6.QtGui import QCursor
            menu.exec(QCursor.pos())

    def _create_export_menu(self, parent: QWidget) -> QMenu:
        menu = QMenu("Export", parent)
        menu.setIcon(self._toolbar_icon("export.svg"))
        menu.addAction("CSV…", self._export_csv)
        return menu

    def _create_toolbar_style_menu(self, parent: QWidget) -> QMenu:
        menu = QMenu("Settings", parent)
        menu.setIcon(self._toolbar_icon("settings.svg"))
        menu.aboutToShow.connect(lambda m=menu: self._populate_toolbar_style_menu(m))
        self._populate_toolbar_style_menu(menu)
        return menu

    def _populate_toolbar_style_menu(self, menu: QMenu) -> None:
        menu.clear()
        if self._toolbar is None:
            return
        for label, style in (
            ("Icon and text", Qt.ToolButtonTextBesideIcon),
            ("Icon only", Qt.ToolButtonIconOnly),
            ("Text only", Qt.ToolButtonTextOnly),
        ):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._toolbar.toolButtonStyle() == style)
            action.triggered.connect(
                lambda checked=False, selected_style=style:
                self.set_toolbar_button_style(selected_style)
            )

    @property
    def record_total(self) -> int:
        """Row total under the current filters (for the host's statusbar)."""
        return int(self._model.total_items)

    # ──────────────────────────────────────────
    # Signals → logic
    # ──────────────────────────────────────────

    def _connect_signals(self):
        self._header.actionClicked.connect(self._on_header_action)

        self._pagination.page_changed.connect(self._on_page_changed)
        self._pagination.items_per_page_changed.connect(self._on_page_size_changed)
        self._table.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

        self._model.data_loaded.connect(self._on_data_loaded)
        self._model.edit_requested.connect(self.edit_committed)

        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._table.clicked.connect(self._on_row_clicked)

    # ──────────────────────────────────────────
    # Handlers
    # ──────────────────────────────────────────

    # ── Header actions ──────────────���─────────────────────────────────────

    def _on_header_action(
        self, logical_index: int, action: str, modifiers: Qt.KeyboardModifiers
    ) -> None:
        offset  = 1 if self._config.show_row_numbers else 0
        col_idx = logical_index - offset
        visible = self._config.visible_columns()
        if not (0 <= col_idx < len(visible)):
            return
        col_def  = visible[col_idx]
        additive = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if action == "sort":
            self._handle_sort(col_def, additive)
        elif action == "search":
            self._open_column_search(logical_index, col_def)
        elif action == "filter":
            self._open_column_filter(logical_index, col_def)

    def _handle_sort(self, col_def: ColumnDef, additive: bool) -> None:
        sorts    = list(self._builder.active_sorts)
        existing = next((s for s in sorts if s.field == col_def.field), None)

        if existing is None:
            new_sort  = SortSpec(col_def.field, descending=False)
            new_sorts = (sorts + [new_sort]) if additive else [new_sort]
        elif not existing.descending:
            existing.descending = True
            new_sorts = sorts
        else:
            new_sorts = [s for s in sorts if s.field != col_def.field]

        self._builder.set_sort(new_sorts)
        self._sync_header()
        self.refresh(reset_page=False)
        self.view_state_changed.emit()

    def _open_column_search(self, logical_index: int, col_def: ColumnDef) -> None:
        current_text = ""
        for f in self._builder.active_filters:
            if f.field == col_def.field and f.op == FilterOperator.ILIKE:
                v = str(f.value)
                current_text = v.strip("%")
                break

        popup = SearchPopup(col_def.label, current_text, self)
        popup.applied.connect(lambda text, field=col_def.field: self._apply_column_search(field, text))
        popup.cleared.connect(lambda field=col_def.field: self._clear_column_search(field))
        self._show_popup(popup, logical_index)
        popup.editor.setFocus()

    def _open_column_filter(self, logical_index: int, col_def: ColumnDef) -> None:
        current = next(
            (f for f in self._builder.active_filters
             if f.field == col_def.field and f.op != FilterOperator.ILIKE),
            None,
        )
        popup = FilterPopup(col_def, current, self)
        popup.applied.connect(
            lambda op, val, field=col_def.field: self._apply_column_filter(field, op, val)
        )
        popup.cleared.connect(lambda field=col_def.field: self._clear_column_filter(field))
        self._show_popup(popup, logical_index)
        popup.focus_editor()

    def set_external_filters(self, key: str, filters: list[FilterSpec]) -> None:
        """Set (or replace) an external filter overlay under `key` and reload.

        It composes with the user's interactive filters using AND, without touching
        them; passing an empty list is the same as `clear_external_filters(key)`.
        """
        self._builder.set_external_filters(key, filters)
        self.refresh()

    def clear_external_filters(self, key: str) -> None:
        self._builder.clear_external_filters(key)
        self.refresh()

    def set_external_clause(self, key: str, clause) -> None:
        """Set (or, with None, drop) a raw SQLAlchemy clause under `key` and reload.

        For conditions FilterSpec cannot express - typically a `~exists(...)`
        against another table.
        """
        self._builder.set_external_clause(key, clause)
        self.refresh()

    def _apply_column_search(self, field: str, text: str) -> None:
        rest = [f for f in self._builder.active_filters
                if not (f.field == field and f.op == FilterOperator.ILIKE)]
        if text.strip():
            rest.append(FilterSpec(field, FilterOperator.ILIKE, f"%{text}%"))
        self._builder.set_filters(rest)
        self._sync_header()
        self.refresh()

    def _clear_column_search(self, field: str) -> None:
        self._builder.set_filters([
            f for f in self._builder.active_filters
            if not (f.field == field and f.op == FilterOperator.ILIKE)
        ])
        self._sync_header()
        self.refresh()

    def _apply_column_filter(self, field: str, op: FilterOperator, value: Any) -> None:
        rest = [f for f in self._builder.active_filters
                if not (f.field == field and f.op != FilterOperator.ILIKE)]
        rest.append(FilterSpec(field, op, value))
        self._builder.set_filters(rest)
        self._sync_header()
        self.refresh()

    def _clear_column_filter(self, field: str) -> None:
        self._builder.set_filters([
            f for f in self._builder.active_filters
            if not (f.field == field and f.op != FilterOperator.ILIKE)
        ])
        self._sync_header()
        self.refresh()

    def _show_popup(self, popup: QWidget, logical_index: int) -> None:
        if self._active_popup is not None:
            self._active_popup.close()
        self._active_popup = popup
        popup.move(self._header.popup_position(logical_index))
        popup.show()

    def _sync_header(self) -> None:
        active = self._builder.active_filters
        self._header.set_query_state(
            self._builder.active_sorts,
            {f.field for f in active if f.op == FilterOperator.ILIKE},
            {f.field for f in active if f.op != FilterOperator.ILIKE},
        )

    def _on_page_changed(self, page: int):
        if self._is_infinite_mode():
            return
        self._builder.set_page(page)
        self.refresh(reset_page=False)

    def set_empty_state(self, message: str | None = None, *, show_action: bool | None = None):
        """Change the empty state at runtime: `None` restores what the config declares.

        A host that filters the table from outside knows something the table does
        not: "there is no data" and "the filter lets nothing through" are different
        states, and the action that fills the table (import, create) does not fix
        the second one.
        """
        self._empty_label.setText(message or self._config.empty_message)
        button = self._empty_widget.findChild(QPushButton, "EmptyActionButton")
        if button is not None:
            button.setVisible(True if show_action is None else bool(show_action))

    def _on_page_size_changed(self, size: int):
        self._builder.set_page_size(size)
        self.refresh()

    def _on_data_loaded(self, total: int, page: int):
        if not self._is_infinite_mode():
            self._pagination.set_total_items(total)
            self._pagination.set_current_page(page)
        has_data = self._model.loaded_count > 0
        self._table.setVisible(has_data)
        self._empty_widget.setVisible(not has_data)
        self._update_result_count_label(total)
        self.data_refreshed.emit(total)
        # Place persistent widgets in the new cells
        self._refresh_persistent_widgets()
        self._schedule_infinite_autofill()

    def _on_cell_pressed(self, _view, index, modifiers):
        raw, column = index.data(RAW_OBJECT_ROLE), index.data(COLUMN_DEF_ROLE)
        if raw is not None and column is not None:
            self.cell_pressed.emit(raw, column.field, modifiers)

    def _on_row_clicked(self, index):
        raw = self._model.data(index, RAW_OBJECT_ROLE)
        if raw is not None:
            self.row_clicked.emit(raw)

    def _on_double_click(self, index):
        raw = self._model.data(index, RAW_OBJECT_ROLE)
        if raw is not None:
            self.row_double_clicked.emit(raw)

    def _on_selection_changed(self, *_):
        objs = self.get_selected_objects()
        self._selected_count = len(objs)
        self._update_result_count_label(self._model.total_items)
        self.selection_changed.emit(objs)


    def _on_scroll_changed(self, value: int) -> None:
        if not self._is_infinite_mode():
            return
        capacity = self._viewport_row_capacity()
        margin_rows = max(1, self._config.infinite_scroll_margin // max(1, self._table.rowHeight(0)))
        first = max(0, int(value))
        last = min(max(0, self._model.rowCount() - 1), first + capacity - 1)
        if first < self._model.window_start:
            self._ensure_infinite_row(first)
        elif last >= self._model.window_end - margin_rows:
            self._ensure_infinite_row(last)

    def _schedule_infinite_autofill(self) -> None:
        if not self._is_infinite_mode() or self._infinite_autofill_scheduled:
            return
        self._infinite_autofill_scheduled = True
        QTimer.singleShot(0, self._auto_fill_infinite_viewport)

    def _auto_fill_infinite_viewport(self) -> None:
        self._infinite_autofill_scheduled = False
        if not self._is_infinite_mode():
            return
        if self._loading_more:
            self._schedule_infinite_autofill()
            return
        if self._model.total_items == 0:
            return
        # A refresh reloads from the top but leaves the scrollbar where it was, so no scroll
        # signal comes: load the rows the viewport shows, or they stay blank until one does.
        self._on_scroll_changed(self._table.verticalScrollBar().value())
        if not self._infinite_has_more:
            return
        if self._model.loaded_count >= self._viewport_row_capacity():
            return
        self.load_next_page()

    def _on_refresh_clicked(self):
        # Reload this table where the user is looking (scroll and selection kept), then let
        # the host (e.g. DockingStudio) refresh surrounding state.
        self.refresh_preserving_view()
        self.refresh_clicked.emit()

    # ──────────────────────────────────────────
    # Toolbar (agnostic: opaque ToolbarAction zones + built-ins)
    # ──────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        """Toolbar row: a real QToolBar (overflow ☰ + icon/text style for free) plus the
        record label pinned outside it, so a narrow table never hides the count."""
        cfg = self._config
        self._toolbar_row = QWidget()
        self._toolbar_row.setObjectName("SmartTableToolbar")
        # A bare QWidget ignores its stylesheet background without this.
        self._toolbar_row.setAttribute(Qt.WA_StyledBackground, True)
        self._apply_toolbar_chrome()
        row = QHBoxLayout(self._toolbar_row)
        row.setContentsMargins(6, 1, 6, 1)
        row.setSpacing(8)

        self._toolbar = QToolBar(self._toolbar_row)
        self._toolbar.setMovable(False)      # lives inside a widget, not a QMainWindow
        self._toolbar.setFloatable(False)
        self._toolbar.setContentsMargins(0, 0, 0, 0)
        self._toolbar.setIconSize(QSize(16, 16))
        self._toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        row.addWidget(self._toolbar, 1)

        if cfg.embedded_controls:
            self._columns_action, _ = self._add_toolbar_action(
                "Columns", "columns.svg", "Configure columns",
                self._open_column_config,
            )
            export_menu = self._create_export_menu(self._toolbar)
            self._export_action, self._export_btn = self._add_toolbar_action(
                "Export", "export.svg", "Export data",
                menu=export_menu,
            )

        self._add_zone(cfg.toolbar_left)
        # Anchor for set_toolbar_actions(): runtime actions land at the tail of the left zone.
        self._zone_anchor = self._toolbar.addWidget(self._spacer())
        self._add_zone(cfg.toolbar_center)

        if cfg.embedded_controls:
            self._refresh_action, self._refresh_btn = self._add_toolbar_action(
                "Reload", "reload.svg", "Reload the table from the database",
                self._on_refresh_clicked,
            )

        self._add_zone(cfg.toolbar_right)

        if cfg.embedded_controls:
            toolbar_style_menu = self._create_toolbar_style_menu(self._toolbar)
            self._settings_action, _ = self._add_toolbar_action(
                "Settings", "settings.svg", "Change the button style",
                menu=toolbar_style_menu,
            )

        if cfg.toolbar_collapsible:
            self._collapse_btn = self._icon_btn("≡", "Show/hide actions", self._toggle_toolbar_collapsed)
            row.addWidget(self._collapse_btn)   # outside the bar: never auto-hidden
            self._apply_collapsed_state()

        if cfg.show_record_count:
            self._result_count_label = QLabel("0 records")
            self._result_count_label.setObjectName("ToolbarMeta")
            self._result_count_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
            self._result_count_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
            row.addWidget(self._result_count_label)

        self._configure_overflow_button()
        return self._toolbar_row

    @staticmethod
    def _spacer() -> QWidget:
        """Elastic spacer: QToolBar has no addStretch()."""
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return w

    def set_toolbar_button_style(self, style: Qt.ToolButtonStyle) -> None:
        """Icons / text / both for the toolbar actions."""
        if self._toolbar is not None:
            self._toolbar.setToolButtonStyle(style)

    def _apply_toolbar_chrome(self) -> None:
        """Paint the toolbar as a band so the actions read as chrome, not as content.

        The header's tone (`dark`): window/base/alternate-base are within a couple of steps
        of each other in the flat light themes, so they separate nothing. Re-applied on
        PaletteChange, so it still follows a live theme switch.
        """
        if self._toolbar_row is None:
            return
        self._toolbar_row.setStyleSheet(
            "#SmartTableToolbar { background: palette(dark);"
            " border-bottom: 1px solid palette(mid); }"
            " QToolBar { background: transparent; border: 0; }"
        )

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_toolbar_chrome()
            self._refresh_toolbar_icons()

    @staticmethod
    def _as_icon(icon) -> QIcon:
        return icon if isinstance(icon, QIcon) else QIcon(str(icon))

    def _icon_btn(self, text: str, tooltip: str, callback) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("ToolbarBtn")
        btn.setText(text)
        btn.setAutoRaise(True)
        btn.setToolTip(tooltip)
        if callback:
            btn.clicked.connect(lambda checked=False: callback())
        return btn

    def _add_toolbar_action(
        self,
        text: str,
        icon_name: str,
        tooltip: str,
        callback=None,
        *,
        menu: QMenu | None = None,
    ) -> tuple[QAction, QToolButton]:
        """Add a command that remains available in an embedded toolbar's overflow.

        ``QToolBar.addWidget()`` cannot reproduce its widgets in the extension
        popup unless the toolbar belongs to a ``QMainWindow``. These controls are
        commands, so native actions are the appropriate representation. Each
        action keeps both icon and text: the toolbar defaults to icons while its
        overflow menu uses the descriptive text.
        """
        action = QAction(text, self._toolbar)
        action.setIcon(self._toolbar_icon(icon_name))
        action.setToolTip(tooltip)
        if menu is not None:
            action.setMenu(menu)
        if callback:
            action.triggered.connect(lambda checked=False: callback())
        self._toolbar.addAction(action)
        self._builtin_actions.append(action)
        self._builtin_action_icons[action] = icon_name

        button = self._toolbar.widgetForAction(action)
        if not isinstance(button, QToolButton):
            raise RuntimeError("QToolBar did not create a QToolButton for QAction")
        button.setObjectName("ToolbarBtn")
        if menu is not None:
            button.setPopupMode(QToolButton.InstantPopup)
        return action, button

    def _toolbar_icon(self, name: str) -> QIcon:
        """Render a currentColor SVG using the live palette."""
        icon_path = _TOOLBAR_ICONS / name
        svg = icon_path.read_bytes().replace(
            b"currentColor", self.palette().buttonText().color().name().encode()
        )
        dpr = max(1.0, self.devicePixelRatioF())
        logical_size = self._toolbar.iconSize() if self._toolbar is not None else QSize(16, 16)
        pixmap = QPixmap(
            max(1, round(logical_size.width() * dpr)),
            max(1, round(logical_size.height() * dpr)),
        )
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg)).render(painter)
        painter.end()
        return QIcon(pixmap)

    def _refresh_toolbar_icons(self) -> None:
        for action, icon_name in self._builtin_action_icons.items():
            action.setIcon(self._toolbar_icon(icon_name))
        if self._overflow_btn is not None:
            self._overflow_btn.setIcon(self._toolbar_icon("menu.svg"))

    def _configure_overflow_button(self) -> None:
        """Turn QToolBar's extension control into the table's hover menu."""
        self._overflow_btn = self._toolbar.findChild(
            QToolButton, "qt_toolbar_ext_button"
        )
        if self._overflow_btn is None:
            return
        self._overflow_btn.setArrowType(Qt.NoArrow)
        self._overflow_btn.setText("")
        self._overflow_btn.setIcon(self._toolbar_icon("menu.svg"))
        self._overflow_btn.setIconSize(QSize(14, 14))
        self._overflow_btn.setFixedWidth(20)
        self._overflow_btn.setMinimumHeight(18)
        self._overflow_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._overflow_btn.setToolTip("More actions")
        self._overflow_btn.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self._overflow_btn and event.type() == QEvent.Type.Enter:
            QTimer.singleShot(0, self._show_overflow_menu)
        return super().eventFilter(watched, event)

    def _show_overflow_menu(self) -> None:
        button = self._overflow_btn
        if button is None or button.isHidden() or not button.isEnabled():
            return
        menu = button.menu()
        if menu is None or menu.isVisible():
            return
        button.showMenu()

    def _add_zone(self, actions) -> None:
        for action in actions or []:
            act = self._make_action(action)
            self._injected_actions.append((action, act))
            self._toolbar.addAction(act)

    def _make_action(self, action: ToolbarAction) -> QAction:
        act = QAction(action.label or "", self._toolbar)
        if action.icon is not None:
            act.setIcon(self._as_icon(action.icon))
        act.setToolTip(action.tooltip or action.label)
        if action.on_click:
            act.triggered.connect(lambda checked=False, a=action: a.on_click(self.get_selected_objects()))
        return act

    def set_toolbar_actions(self, key: str, actions: list[ToolbarAction]) -> None:
        """Put a host's commands on this table's toolbar while it needs them.

        Same shape as `set_external_filters`: keyed by the host (a tool id), replacing
        whatever that key had, and an empty list is `clear_toolbar_actions(key)`. A tool that
        narrows a table can now also act on it, and gives both back on the way out.
        """
        self.clear_toolbar_actions(key)
        if not actions:
            return
        if self._toolbar is None:
            # Config asked for no toolbar; a runtime action still has to be reachable.
            self.layout().insertWidget(0, self._build_toolbar())
        added = [self._make_action(a) for a in actions]
        for act in added:
            act.setVisible(not self._actions_collapsed)
            self._toolbar.insertAction(self._zone_anchor, act)
        self._keyed_actions[key] = added

    def set_config_actions_visible(self, visible: bool) -> None:
        """Show/hide the actions the config declares (toolbar_left/center/right).

        The built-in controls (Columns, Export, Reload, Settings) stay: they describe the
        table. The config's own actions describe the *catalog* — a table lent to a tool
        should not still be offering "Import…".
        """
        self._config_actions_visible = bool(visible)
        self._apply_collapsed_state()

    def clear_toolbar_actions(self, key: str) -> None:
        for act in self._keyed_actions.pop(key, []):
            self._toolbar.removeAction(act)

    def _toggle_toolbar_collapsed(self) -> None:
        self._actions_collapsed = not self._actions_collapsed
        self._apply_collapsed_state()

    def _apply_collapsed_state(self) -> None:
        hidden = self._actions_collapsed
        for action in self._builtin_actions:
            action.setVisible(not hidden)
        for _, act in self._injected_actions:
            act.setVisible(not hidden and self._config_actions_visible)
        for acts in self._keyed_actions.values():
            for act in acts:
                act.setVisible(not hidden)

    # ── View state (persistable table preferences) ───────────────────────
    def view_state(self) -> dict:
        """Current user-facing table prefs: visible column fields + active sort.
        Suitable for JSON/TOML persistence by the host app."""
        return {
            "columns": [c.field for c in self._config.columns if c.visible],
            "sort": [{"field": s.field, "descending": bool(s.descending)} for s in self._builder.active_sorts],
        }

    def apply_view_state(self, state: dict | None) -> None:
        """Apply a previously saved view_state(). Unknown fields are ignored;
        an empty/missing 'columns' leaves the config-defined visibility intact."""
        if not state:
            return
        columns = state.get("columns")
        if columns:
            wanted = set(columns)
            known = {c.field for c in self._config.columns}
            # Only apply if it references real columns; keep at least one visible.
            if wanted & known:
                for c in self._config.columns:
                    c.visible = c.field in wanted
        sort = state.get("sort")
        if sort:
            self._builder.set_sort(
                [SortSpec(s["field"], descending=bool(s.get("descending"))) for s in sort if s.get("field")]
            )
        self._install_delegates()
        self._sync_header()
        self.refresh()

    def _open_column_config(self):
        dlg = ColumnConfigDialog(self._config, parent=self)
        dlg.columns_changed.connect(self._on_columns_changed)
        dlg.exec()

    def _on_columns_changed(self, ordered_cols):
        self._config.columns = ordered_cols
        self._install_delegates()
        self._update_control_summaries()
        self._sync_header()
        self.refresh()
        self._apply_column_widths()
        self.view_state_changed.emit()

    def _show_context_menu(self, pos):
        index = self._table.indexAt(pos)
        menu  = QMenu(self)

        if index.isValid():
            raw = self._model.data(index, RAW_OBJECT_ROLE)
            # Right-clicking inside the selection acts on the whole selection (file-manager
            # behaviour); right-clicking outside it acts on the single row under the cursor.
            selected = self.get_selected_objects()
            targets = selected if any(obj is raw for obj in selected) else [raw]

            for label, callback in self._config.context_menu_actions.items():
                action = menu.addAction(label)
                action.triggered.connect(
                    lambda checked, cb=callback, objs=targets: cb(list(objs))
                )

            if self._config.context_menu_actions:
                menu.addSeparator()

        copy_action = menu.addAction("Copiar celda")
        copy_action.triggered.connect(lambda: self._copy_cell(index))

        copy_row_action = menu.addAction("Copy row")
        copy_row_action.triggered.connect(
            lambda: self._copy_row(index.row()) if index.isValid() else None
        )

        menu.addSeparator()
        menu.addAction("Export CSV").triggered.connect(self._export_csv)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _copy_cell(self, index):
        if not index.isValid():
            return
        text = self._model.data(index, Qt.DisplayRole) or ""
        QApplication.clipboard().setText(str(text))

    def _copy_row(self, row: int):
        row_data = self._model.get_row_data(row)
        if row_data is None:
            return
        visible = self._config.visible_columns()
        parts   = [str(row_data.get(c.display_key, "")) for c in visible]
        QApplication.clipboard().setText("\t".join(parts))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "export.csv", "CSV (*.csv)"
        )
        if not path:
            return
        visible = self._config.visible_columns()
        headers = [c.label for c in visible]
        rows    = [self._model.get_row_data(i) for i in self._model.loaded_rows]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in rows:
                if row:
                    writer.writerow([row.get(c.display_key, "") for c in visible])

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def refresh(self, reset_page: bool = True) -> None:
        """Reload data from the DB with the current filter/sort/page state."""
        if self._is_infinite_mode():
            self._builder.set_page(1)
            self._new_generation()
            # The first page stays on this thread (hosts select it right after refresh());
            # it is a keyset seek. The COUNT is what costs at millions of rows.
            rows, has_more = self._builder.fetch_window_after(None)
            self._infinite_pages = {0: rows}
            self._infinite_page_cursors = {0: None}
            if rows:
                self._infinite_page_cursors[1] = self._builder.cursor_of(rows[-1])
            self._infinite_frontier_page = 0
            self._infinite_loaded_end = len(rows)
            self._infinite_has_more = has_more
            self._infinite_total_hint = len(rows) + int(has_more)
            self._infinite_total_exact = not has_more
            self._model.load_data(
                rows,
                self._infinite_total_hint,
                1,
                window_start=0,
                total_is_exact=self._infinite_total_exact,
            )
            # New rows from the top: a scrollbar left deep down would jump to a page of a
            # query that no longer exists.
            self._table.verticalScrollBar().setValue(0)
            if has_more:
                self._run_async(self._builder.count, self._apply_count)
            return
        if reset_page:
            self._builder.set_page(1)

        rows, total = self._builder.fetch()
        self._model.load_data(rows, total, self._builder.current_page)

    def _fetch_loaded_window(self) -> tuple[list[dict], int, int]:
        current_page = self._builder.current_page
        rows, total = self._builder.fetch()
        return rows, total, current_page

    def _selected_object_ids(self) -> set[int]:
        ids: set[int] = set()
        for obj in self.get_selected_objects():
            value = getattr(obj, "id", None)
            try:
                numeric = int(value)
            except (TypeError, ValueError):
                continue
            if numeric > 0:
                ids.add(numeric)
        return ids

    def _restore_selected_object_ids(self, selected_ids: set[int]) -> None:
        if not selected_ids:
            return
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return
        selection_model.blockSignals(True)
        try:
            selection_model.clearSelection()
            for row in self._model.loaded_rows:
                raw = self._model.get_raw_object(row)
                value = getattr(raw, "id", None) if raw is not None else None
                try:
                    numeric = int(value)
                except (TypeError, ValueError):
                    continue
                if numeric not in selected_ids:
                    continue
                left = self._model.index(row, 0)
                right = self._model.index(row, max(0, self._model.columnCount() - 1))
                selection_model.select(
                    left,
                    QItemSelectionModel.Select | QItemSelectionModel.Rows,
                )
                if right.isValid():
                    selection_model.setCurrentIndex(left, QItemSelectionModel.NoUpdate)
        finally:
            selection_model.blockSignals(False)

    def load_next_page(self) -> None:
        """Load the next page and drop old pages that fell outside the window."""
        if not self._is_infinite_mode() or self._loading_more:
            return
        if not self._infinite_has_more:
            return
        self._load_infinite_page(self._infinite_frontier_page + 1)

    def _load_infinite_page(self, page_index: int) -> None:
        if page_index < 0 or self._loading_more or page_index in self._infinite_pages:
            return
        if page_index in self._infinite_page_cursors:
            # Keyset from a known cursor: an index seek, stays on this thread.
            self._store_infinite_page(
                page_index, self._builder.fetch_window_after(self._infinite_page_cursors[page_index]))
            return
        # A scrollbar jump: walk from the nearest known cursor before it, on a worker.
        anchor_page = max((page for page in self._infinite_page_cursors if page < page_index), default=0)
        anchor = self._infinite_page_cursors.get(anchor_page)
        self._jump(lambda: self._builder.fetch_window_at(page_index, anchor, anchor_page),
                   lambda result: self._store_infinite_page(page_index, result))

    def _store_infinite_page(self, page_index: int, result: tuple[list[dict], bool]) -> None:
        rows, _has_more = result
        self._infinite_pages[page_index] = rows
        if rows:
            self._infinite_page_cursors[page_index + 1] = self._builder.cursor_of(rows[-1])
        if page_index >= self._infinite_frontier_page:
            self._infinite_frontier_page = page_index
            end = page_index * self._builder.page_size + len(rows)
            self._infinite_loaded_end = end
            # `not rows` also stops the autofill loop when rows vanished under us.
            if self._infinite_total_exact:
                self._infinite_has_more = bool(rows) and end < self._infinite_total_hint
            else:  # the COUNT has not landed yet: grow the hint with what the pages say
                self._infinite_has_more = bool(rows) and _has_more
                self._infinite_total_hint = max(self._infinite_total_hint, end + int(_has_more))
        self._replace_infinite_window(page_index)

    # ── Queries off the GUI thread ───────────────────────────────────────

    def _new_generation(self) -> None:
        self._generation += 1
        self._loading_more = False
        self._jumps_in_flight = 0
        self._loading_overlay.hide()

    def _run_async(self, fn, done, *, jump: bool = False) -> None:
        """`fn()` on the thread pool, `done(result)` back here unless the query changed."""
        generation = self._generation

        def finish(result) -> None:
            if generation != self._generation:
                return
            if jump:
                self._jumps_in_flight -= 1
                self._loading_more = self._jumps_in_flight > 0
                self._loading_overlay.setVisible(self._loading_more)
            if isinstance(result, Exception):
                raise result
            done(result)

        if jump:
            self._jumps_in_flight += 1
            self._loading_more = True
            self._loading_overlay.setGeometry(self._table.viewport().rect())
            self._loading_overlay.show()
        QThreadPool.globalInstance().start(_Query(fn, finish, self._delivery))

    def _jump(self, fn, done) -> None:
        """A page load the user waits for: overlay on, and while it runs `_loading_more`
        swallows further scrollbar moves. When it lands the autofill loads wherever the
        scrollbar ended up, so a fast drag costs one query in flight, not one per tick."""
        self._run_async(fn, done, jump=True)

    def _replace_infinite_window(self, focus_page: int) -> None:
        cache_pages = max(
            1,
            min(
                self._config.infinite_cache_pages,
                max(1, self._config.max_loaded_rows // self._builder.page_size),
            ),
        )
        known_pages = sorted(self._infinite_pages)
        if not known_pages:
            return
        # Only pages contiguous with the focus: the model window is one run of rows, so a gap
        # (a jump from page 0 to 2) would show page 2's rows where page 1's belong.
        step = -1 if focus_page >= max(known_pages) else 1
        keep = [focus_page]
        while len(keep) < cache_pages and keep[-1] + step in self._infinite_pages:
            keep.append(keep[-1] + step)
        keep.sort()
        self._infinite_pages = {page: self._infinite_pages[page] for page in keep}
        start_page = min(keep)
        rows = [row for page in sorted(keep) for row in self._infinite_pages[page]]
        end = (max(keep) * self._builder.page_size) + len(self._infinite_pages[max(keep)])
        scroll_value = self._table.verticalScrollBar().value()
        selected_ids = self._selected_object_ids()
        self._builder.set_page(focus_page + 1)
        self._model.load_data(
            rows,
            self._infinite_total_hint,
            focus_page + 1,
            window_start=start_page * self._builder.page_size,
            total_is_exact=self._infinite_total_exact,
        )
        self._restore_selected_object_ids(selected_ids)
        self._table.verticalScrollBar().setValue(scroll_value)

    def _ensure_infinite_row(self, row: int) -> None:
        if row < 0 or self._model.is_row_loaded(row):
            return
        self._load_infinite_page(row // self._builder.page_size)

    def set_db(self, db: SessionProvider) -> None:
        """Replace the session provider (useful on project switch or reconnect)."""
        self._db = db
        self._builder = QueryBuilder(db, self._config)
        self._update_control_summaries()
        self.refresh()

    @property
    def view(self):
        """The inner QTableView — for hosts that need to scope focus or shortcuts to it."""
        return self._table

    def repaint_rows(self) -> None:
        """Repaint the visible rows without re-querying (host state changed, not the data)."""
        self._table.viewport().update()

    def get_selected_objects(self) -> list[Any]:
        """Return the list of selected SQLModel objects."""
        indexes = self._table.selectionModel().selectedRows()
        objs = []
        for idx in indexes:
            raw = self._model.data(idx, RAW_OBJECT_ROLE)
            if raw is not None:
                objs.append(raw)
        return objs

    def get_selected_object(self) -> Optional[Any]:
        """Return the first selected object, or None."""
        objs = self.get_selected_objects()
        return objs[0] if objs else None

    def all_filtered_ids(self) -> list[int]:
        """PKs of every row matching the current filters/search (across all pages)."""
        return self._builder.all_ids()

    def set_filter(self, spec: FilterSpec) -> None:
        """Apply a filter programmatically."""
        self._builder.add_filter(spec)
        self._sync_header()
        self._update_control_summaries()
        self.refresh()

    def set_filters(self, filters: list[FilterSpec]) -> None:
        """Replace the whole scope and reload exactly once.

        This is the right operation for external controls that change receptor,
        ligand, protocol and metrics as a single state transition.
        """
        self._builder.set_filters(list(filters))
        self._sync_header()
        self._update_control_summaries()
        self.refresh()

    def select_first_row(self) -> bool:
        """Select the first materialised row; never the sentinel row."""
        if self._model.loaded_count == 0:
            return False
        self._table.selectRow(self._model.window_start)
        return True

    def clear_filters(self) -> None:
        self._builder.clear_filters()
        self._sync_header()
        self._update_control_summaries()
        self.refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_infinite_autofill()

    def _update_control_summaries(self) -> None:
        self._update_result_count_label(self._model.total_items)

    def _update_result_count_label(self, total: int) -> None:
        if self._result_count_label is None:
            return

        total = max(0, int(total))
        loaded = self._model.loaded_count

        if not self._is_infinite_mode():
            text = ""  # the pagination bar already shows the total; do not repeat it
        else:
            # How far the scroll got, out of how many there are. `loaded` is the window,
            # which shrinks behind the cursor - the frontier is what the user counts.
            reached = min(max(self._infinite_loaded_end, loaded), total)
            text = f"{reached:,} of {total:,} records" if reached < total else f"{total:,} records"
        # The selection sits next to the total: the other half of "what am I looking at".
        if self._selected_count > 0:
            text = f"{self._selected_count:,} sel · {text}" if text else f"{self._selected_count:,} sel"

        self._result_count_label.setText(text)
        self._result_count_label.setVisible(bool(text))
        self._result_count_label.setToolTip("Current total of results in the table")
