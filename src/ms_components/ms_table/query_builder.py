"""
query_builder.py
────────────────
Translates TableConfig + UI state (filters, sort, page) into SQLModel/SQLAlchemy
queries.

Design:
  - No Qt dependency → testable as plain Python.
  - Returns (items: list[dict], total: int) to feed the Qt model.
  - Supports automatic joins driven by ColumnDef.join.
  - Pagination happens in the DB, not in memory.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, text
from sqlmodel import select, col

from .session_provider import SessionProvider
from .table_config import (
    ColumnDef, FilterOperator, FilterSpec, SortSpec, TableConfig
)


class QueryBuilder:
    """Builds and runs paginated queries from a TableConfig.

    Usage:
        builder = QueryBuilder(db, config)
        builder.set_filters([FilterSpec("name", FilterOperator.ILIKE, "%ann%")])
        builder.set_sort([SortSpec("id", descending=True)])
        builder.set_page(1)
        rows, total = builder.fetch()
    """

    def __init__(self, db: SessionProvider, config: TableConfig):
        self._db            = db
        self._config        = config
        self._filters: list[FilterSpec] = list(config.default_filters)
        # Filter overlays imposed by an external host (e.g. a tool narrowing a
        # shared table). They compose with the user's filters using AND without
        # overwriting them, and are cleared by key when the host goes away.
        self._external: dict[str, list[FilterSpec]] = {}
        # Same as _external but holding already-built SQLAlchemy expressions (see
        # set_external_clause): whatever FilterSpec cannot describe.
        self._external_clauses: dict[str, Any] = {}
        self._sorts:   list[SortSpec]   = list(config.default_sort)
        self._page:    int              = 1
        self._page_size: int            = config.page_size
        self._search_text:   str        = ""
        self._search_fields: list[str]  = []

    # ──────────────────────────────────────────
    # State setters (called from the UI)
    # ──────────────────────────────────────────

    def set_filters(self, filters: list[FilterSpec]) -> None:
        self._filters = filters
        self._page = 1

    def add_filter(self, f: FilterSpec) -> None:
        self._filters = [x for x in self._filters if x.field != f.field]
        self._filters.append(f)
        self._page = 1

    def remove_filter(self, field: str) -> None:
        self._filters = [x for x in self._filters if x.field != field]
        self._page = 1

    def clear_filters(self) -> None:
        self._filters = []
        self._search_fields: list[str] = []
        self._search_text: str = ""
        self._page = 1

    # ── External overlays (host-driven; they never touch the user's filters) ──

    def set_external_filters(self, key: str, filters: list[FilterSpec]) -> None:
        if filters:
            self._external[key] = list(filters)
        else:
            self._external.pop(key, None)
        self._page = 1

    def clear_external_filters(self, key: str) -> None:
        self._external.pop(key, None)
        self._page = 1

    def set_external_clause(self, key: str, clause) -> None:
        """Overlay a raw SQLAlchemy clause under `key` (None removes it).

        Escape hatch for what FilterSpec cannot express - subqueries
        (`~exists(...)`), OR across fields, functions. It composes with AND just
        like `set_external_filters`, and because it is an already-built expression
        the builder does not interpret it: making sure it references the right
        model is the caller's responsibility.
        """
        if clause is None:
            self._external_clauses.pop(key, None)
        else:
            self._external_clauses[key] = clause
        self._page = 1

    def _all_filters(self) -> list[FilterSpec]:
        """The user's filters plus every external overlay, ANDed together."""
        overlay = [f for specs in self._external.values() for f in specs]
        return self._filters + overlay

    # ── Global quick search (OR across several columns) ──

    def set_search(self, text: str, fields: list[str]) -> None:
        """Enable an ILIKE search ORed across the given fields."""
        self._search_text   = text
        self._search_fields = fields
        self._page = 1

    def remove_search(self) -> None:
        """Disable the quick search and show everything again."""
        self._search_text   = ""
        self._search_fields = []
        self._page = 1

    def set_sort(self, sorts: list[SortSpec]) -> None:
        self._sorts = sorts

    def set_page(self, page: int) -> None:
        self._page = max(1, page)

    def set_page_size(self, size: int) -> None:
        self._page_size = size
        self._page = 1

    # ──────────────────────────────────────────
    # Fetch principal
    # ──────────────────────────────────────────

    def all_ids(self) -> list[int]:
        """PKs of every row matching the current filters/search (no pagination).

        Lets a caller resolve "everything the table currently shows" into an id set
        without materializing rows. Honors filters + quick search, ignores paging.
        """
        pk = self._get_pk_attr()
        if pk is None:
            return []
        stmt = self._build_base_statement().with_only_columns(pk)
        with self._db.get_session() as session:
            return [int(value) for value in session.exec(stmt).all() if value is not None]

    def count(self) -> int:
        """Row total under the current filters/search, without fetching any row.

        For hosts that want to keep the counter live (e.g. while a job inserts
        records) without reloading the visible rows.
        """
        with self._db.get_session() as session:
            return int(session.exec(self._build_count_statement()).one())  # type: ignore[arg-type]

    def cursor_of(self, row: dict) -> tuple[Any, Any] | None:
        """Keyset cursor `(sort_value, pk)` for an already-loaded row."""
        raw = row.get("__raw__")
        pk = self._get_pk_attr()
        if raw is None or pk is None:
            return None
        pk_value = getattr(raw, pk.key, None)
        if not self._sorts:
            return (None, pk_value)
        sort = self._sorts[0]
        col_def = self._config.column_by_field(sort.field)
        key = col_def.display_key if col_def is not None else sort.field
        return ((row.get("__cursor_values__") or {}).get(key, row.get(key)), pk_value)

    def fetch_after(self, cursor: tuple[Any, Any] | None) -> tuple[list[dict], int]:
        """Next page by keyset: `WHERE (sort, pk) > cursor`, with no OFFSET.

        OFFSET makes the engine walk and discard the previous N rows, so page 500
        costs 500 times the first one. The cursor does not: it is always an index
        seek. The cursor is composite because the visible order is rarely unique
        (two identical scores).
        """
        stmt = self._build_base_statement()
        clause = self._keyset_clause(cursor)
        if clause is not None:
            stmt = stmt.where(clause)
        with self._db.get_session() as session:
            total: int = session.exec(self._build_count_statement()).one()  # type: ignore[arg-type]
            rows = [self._row_to_dict(r) for r in session.exec(stmt.limit(self._page_size)).all()]
        return rows, total

    def fetch_window_after(self, cursor: tuple[Any, Any] | None) -> tuple[list[dict], bool]:
        """The page after the cursor, without ``COUNT(*)``.

        Infinite scroll only needs to know whether another page exists. Asking for
        one extra row answers that without re-counting a potentially huge table on
        every move.
        """
        stmt = self._build_base_statement()
        clause = self._keyset_clause(cursor)
        if clause is not None:
            stmt = stmt.where(clause)
        with self._db.get_session() as session:
            raw = session.exec(stmt.limit(self._page_size + 1)).all()
        has_more = len(raw) > self._page_size
        return [self._row_to_dict(row) for row in raw[:self._page_size]], has_more

    def fetch_window_at(self, page_index: int) -> tuple[list[dict], bool]:
        """Direct load for a scrollbar jump to a page that has not been walked yet.

        The normal path is still keyset via :meth:`fetch_window_after`. OFFSET only
        shows up when the user drags the scrollbar to a position with no known
        cursor.
        """
        offset = max(0, int(page_index)) * self._page_size
        stmt = self._build_base_statement().offset(offset).limit(self._page_size + 1)
        with self._db.get_session() as session:
            raw = session.exec(stmt).all()
        has_more = len(raw) > self._page_size
        return [self._row_to_dict(row) for row in raw[:self._page_size]], has_more

    def _keyset_clause(self, cursor: tuple[Any, Any] | None):
        if cursor is None:
            return None
        from sqlalchemy import and_, or_

        sort_value, pk_value = cursor
        pk = self._get_pk_attr()
        if pk is None:
            return None
        if not self._sorts:
            return pk > pk_value
        sort = self._sorts[0]
        attr = self._resolve_attr(sort.field)
        if attr is None:
            return pk > pk_value
        if sort_value is None:
            # NULLs come first in ascending SQLite: past the null block, anything goes.
            return attr.is_not(None) if not sort.descending else and_(attr.is_(None), pk > pk_value)
        ahead = attr < sort_value if sort.descending else attr > sort_value
        return or_(ahead, and_(attr == sort_value, pk > pk_value))

    def fetch(self) -> tuple[list[dict], int]:
        """Run the query and return (rows_as_dicts, total_count)."""
        stmt      = self._build_base_statement()
        count_stmt = self._build_count_statement()
        with self._db.get_session() as session:
            total: int = session.exec(count_stmt).one()  # type: ignore[arg-type]

            offset = (self._page - 1) * self._page_size
            stmt   = stmt.offset(offset).limit(self._page_size)

            raw_rows = session.exec(stmt).all()
            rows     = [self._row_to_dict(r) for r in raw_rows]
        return rows, total

    # ──────────────────────────────────────────
    # Internal construction
    # ──────────────────────────────────────────

    def _collect_joins(self) -> list:
        """Return the list of classes to join (deduplicated, in order)."""
        seen   = set()
        joins  = []
        for col_def in self._config.columns:
            if col_def.join is None:
                continue
            targets = col_def.join if isinstance(col_def.join, list) else [col_def.join]
            for target in targets:
                if target not in seen:
                    seen.add(target)
                    joins.append(target)
        return joins

    def _expr_columns(self) -> list[ColumnDef]:
        """Columns whose value SQL computes (JSON_EXTRACT, CASE, func.*), not the ORM."""
        return [c for c in self._config.columns if c.expr is not None]

    def _build_base_statement(self):
        model  = self._config.model_class
        expr_cols = self._expr_columns()
        stmt   = select(model, *(c.expr.label(c.display_key) for c in expr_cols))

        # JOINs
        for join_model in self._collect_joins():
            stmt = stmt.join(join_model, isouter=True)

        # WHERE - advanced filters (ANDed together)
        for f in self._all_filters():
            clause = self._build_filter_clause(f)
            if clause is not None:
                stmt = stmt.where(clause)

        # WHERE - raw clauses imposed by a host (subqueries, OR, ...)
        for clause in self._external_clauses.values():
            stmt = stmt.where(clause)

        # WHERE - quick search (OR across filterable columns)
        search_clause = self._build_search_clause()
        if search_clause is not None:
            stmt = stmt.where(search_clause)

        # ORDER BY
        if self._sorts:
            for sort in self._sorts:
                attr = self._resolve_attr(sort.field)
                if attr is not None:
                    stmt = stmt.order_by(attr.desc() if sort.descending else attr.asc())
            # PK tie-break: without it two rows with the same score have undefined
            # order and the keyset cursor skips or repeats rows across pages.
            pk = self._get_pk_attr()
            if pk is not None:
                stmt = stmt.order_by(pk)
        else:
            # Default order: primary key of the main table
            pk = self._get_pk_attr()
            if pk is not None:
                stmt = stmt.order_by(pk)

        return stmt

    def _build_count_statement(self):
        model = self._config.model_class
        pk    = self._get_pk_attr()
        count_col = func.count(pk) if pk is not None else func.count()
        stmt  = select(count_col)

        for join_model in self._collect_joins():
            stmt = stmt.join(join_model, isouter=True)  # type: ignore[arg-type]

        for f in self._all_filters():
            clause = self._build_filter_clause(f)
            if clause is not None:
                stmt = stmt.where(clause)

        for clause in self._external_clauses.values():
            stmt = stmt.where(clause)

        search_clause = self._build_search_clause()
        if search_clause is not None:
            stmt = stmt.where(search_clause)

        return stmt

    def _build_search_clause(self):
        """OR-ILIKE across every quick-search column."""
        if not self._search_text or not self._search_fields:
            return None
        from sqlalchemy import or_
        value = f"%{self._search_text}%"
        clauses = []
        for field in self._search_fields:
            attr = self._resolve_attr(field)
            if attr is not None:
                clauses.append(attr.ilike(value))
        if not clauses:
            return None
        return or_(*clauses)

    def _build_filter_clause(self, f: FilterSpec):
        """Convert a FilterSpec into a SQLAlchemy clause."""
        attr = self._resolve_attr(f.field)
        if attr is None:
            return None

        op = f.op
        v  = f.value

        match op:
            case FilterOperator.EQ:       return attr == v
            case FilterOperator.NEQ:      return attr != v
            case FilterOperator.LT:       return attr < v
            case FilterOperator.LTE:      return attr <= v
            case FilterOperator.GT:       return attr > v
            case FilterOperator.GTE:      return attr >= v
            case FilterOperator.LIKE:     return attr.like(v)
            case FilterOperator.ILIKE:    return attr.ilike(v)
            case FilterOperator.IN:       return attr.in_(v)
            case FilterOperator.NOT_IN:   return attr.not_in(v)
            case FilterOperator.IS_NULL:  return attr.is_(None)
            case FilterOperator.NOT_NULL: return attr.is_not(None)
            case _:                       return None

    def _resolve_attr(self, field_path: str):
        """
        Resolves "customer.name" → Customer.name (SQLAlchemy attribute).
        Resolves "total"          → Order.total.
        A column with `expr` returns that expression: filtering and sorting by it
        work the same way.
        """
        by_expr = self._config.column_by_field(field_path)
        if by_expr is not None and by_expr.expr is not None:
            return by_expr.expr
        parts = field_path.split(".")
        if len(parts) == 1:
            return getattr(self._config.model_class, parts[0], None)

        # Look up the matching ColumnDef to get the join class
        col_def = self._config.column_by_field(field_path)
        if col_def is None or col_def.join is None:
            return None

        join_classes = col_def.join if isinstance(col_def.join, list) else [col_def.join]
        # The last segment is the attribute; the one before it picks the class
        target_class = join_classes[-1]
        attr_name    = parts[-1]
        return getattr(target_class, attr_name, None)

    def _get_pk_attr(self):
        """Return the primary-key attribute of the main table."""
        model = self._config.model_class
        # SQLModel / SQLAlchemy maps __table__.primary_key
        try:
            pk_cols = list(model.__table__.primary_key.columns)
            if pk_cols:
                return getattr(model, pk_cols[0].name, None)
        except Exception:
            pass
        return None

    # ──────────────────────────────────────────
    # Row serialisation
    # ──────────────────────────────────────────

    def _row_to_dict(self, row: Any) -> dict:
        """
        Convert a row (SQLModel instance) into a flat dict.
        Joined fields are resolved by following each ColumnDef's dot-notation.
        """
        data: dict = {}
        cursor_values: dict[str, Any] = {}
        is_tuple   = isinstance(row, (tuple, list)) or hasattr(row, "_mapping")
        main_obj   = row[0] if is_tuple else row
        # Expression columns come back in the select, in order, after the model.
        expr_values = {
            col_def.display_key: row[index + 1]
            for index, col_def in enumerate(self._expr_columns())
        } if is_tuple else {}

        for col_def in self._config.columns:
            key = col_def.display_key
            try:
                value = expr_values[key] if key in expr_values else self._resolve_value(main_obj, col_def)
            except Exception:
                value = None
            cursor_values[key] = value

            # Apply the formatter if there is one
            if col_def.formatter is not None and value is not None:
                try:
                    value = col_def.formatter(value)
                except Exception:
                    pass

            data[key] = value

        # Keep the raw object around for editing / actions
        data["__raw__"] = main_obj
        data["__cursor_values__"] = cursor_values
        return data

    def _resolve_value(self, obj: Any, col_def: ColumnDef) -> Any:
        """Walk dot-notation over the ORM object."""
        parts = col_def.field.split(".")
        current = obj
        for part in parts:
            if current is None:
                return None
            current = getattr(current, part, None)
        return current

    # ──────────────────────────────────────────
    # Declarative export (for jobs)
    # ──────────────────────────────────────────

    _SPEC_OPS = {
        FilterOperator.EQ: "", FilterOperator.NEQ: "__ne",
        FilterOperator.LT: "__lt", FilterOperator.LTE: "__lte",
        FilterOperator.GT: "__gt", FilterOperator.GTE: "__gte",
        FilterOperator.IN: "__in", FilterOperator.NOT_IN: "__not_in",
        FilterOperator.IS_NULL: "__is_null", FilterOperator.NOT_NULL: "__is_not_null",
    }

    def to_query_spec(self) -> dict:
        """The "filtered" selection as QuerySpec kwargs, ready to hand to a job.

        Returns a dict rather than a QuerySpec so the table does not take ms_flow as
        a dependency; the host does `QuerySpec(**builder.to_query_spec())`. This is
        what avoids materialising a list of ids: the job receives the query, not its
        result.

        Raises when any part of the current state is not expressible (expression
        columns, LIKE/ILIKE filters over joins): staying quiet and sending a wider
        query would be worse.
        """
        model = self._config.model_class
        table = getattr(getattr(model, "__table__", None), "name", "") or model.__name__.lower()

        filters: dict[str, Any] = {}
        for f in self._all_filters():
            col_def = self._config.column_by_field(f.field)
            if col_def is not None and col_def.expr is not None:
                raise ValueError(f"Column '{f.field}' filters on a SQL expression; QuerySpec cannot carry it.")
            if "." in f.field:
                raise ValueError(f"Filter on joined field '{f.field}' has no QuerySpec equivalent.")
            if f.op in (FilterOperator.LIKE, FilterOperator.ILIKE):
                filters[f"{f.field}__contains"] = str(f.value).strip("%")
                continue
            suffix = self._SPEC_OPS.get(f.op)
            if suffix is None:
                raise ValueError(f"Filter operator {f.op} has no QuerySpec equivalent.")
            filters[f"{f.field}{suffix}"] = f.value

        if self._external_clauses:
            raise ValueError("Raw SQLAlchemy clauses set by the host cannot be exported to QuerySpec.")
        if self._search_text and self._search_fields:
            # Quick search is an OR across columns; QuerySpec filters are ANDed.
            raise ValueError("Quick search (OR across columns) has no QuerySpec equivalent.")

        order = tuple(
            f"-{s.field}" if s.descending else s.field
            for s in self._sorts
            if "." not in s.field
        )
        return {"table": table, "filters": filters, "order": order}

    # ──────────────────────────────────────────
    # State getters (to keep the UI in sync)
    # ──────────────────────────────────────────

    @property
    def current_page(self) -> int:
        return self._page

    @property
    def page_size(self) -> int:
        return self._page_size

    @property
    def active_filters(self) -> list[FilterSpec]:
        return list(self._filters)

    @property
    def active_sorts(self) -> list[SortSpec]:
        return list(self._sorts)
