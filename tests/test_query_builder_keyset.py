"""Table navigation: keyset under infinite scroll, expression columns, export to QuerySpec.

What deserves a test is that page N does not cost N times the first one (no OFFSET), that the
composite cursor does not skip rows when the sort ties, and that memory stays a bounded window.
"""
from __future__ import annotations

from typing import Optional

import pytest
from sqlalchemy import case
from PySide6.QtWidgets import QApplication
from sqlmodel import Field, Session, SQLModel, create_engine

from ms_components.ms_table.query_builder import QueryBuilder
from ms_components.ms_table.smart_table_view import SmartTableView
from ms_components.ms_table.table_config import (
    ColumnDef, FilterOperator, FilterSpec, SortSpec, TableConfig, TableLoadMode,
)

N_ROWS = 5_000
PAGE = 100


class Hit(SQLModel, table=True):
    __tablename__ = "hit"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = ""
    score: float = 0.0


class _Db:
    def __init__(self, engine):
        self._engine = engine

    def get_session(self) -> Session:
        return Session(self._engine)


@pytest.fixture(scope="module")
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=None)
    SQLModel.metadata.create_all(engine, tables=[Hit.__table__])
    with Session(engine) as session:
        for i in range(N_ROWS):
            # score tied on purpose: the PK tie-break is what makes the cursor correct.
            session.add(Hit(id=i + 1, name=f"lig-{i:05d}", score=float(i % 10)))
        session.commit()
    return _Db(engine)


def _config(**kwargs) -> TableConfig:
    return TableConfig(
        model_class=Hit,
        columns=[ColumnDef("name"), ColumnDef("score")],
        page_size=PAGE,
        load_mode=TableLoadMode.INFINITE,
        **kwargs,
    )


def test_keyset_walks_the_whole_table_without_offset(db):
    builder = QueryBuilder(db, _config())
    builder.set_sort([SortSpec("score", descending=False)])

    seen: list[int] = []
    cursor = None
    while True:
        rows, total = builder.fetch_after(cursor)
        if not rows:
            break
        seen.extend(row["__raw__"].id for row in rows)
        cursor = builder.cursor_of(rows[-1])

    assert total == N_ROWS
    assert len(seen) == N_ROWS  # neither skips nor repeats rows despite the tied scores
    assert len(set(seen)) == N_ROWS
    sql = str(builder._build_base_statement().compile(compile_kwargs={"literal_binds": True}))
    assert "OFFSET" not in sql.upper()


def test_infinite_scroll_replaces_old_pages_without_counting(db, monkeypatch):
    QApplication.instance() or QApplication(["ms-table-window-test"])
    view = SmartTableView(db, _config(infinite_cache_pages=2, max_loaded_rows=N_ROWS))
    monkeypatch.setattr(view._builder, "count", lambda: pytest.fail("infinite scroll must not COUNT"))

    for _ in range(10):
        view.load_next_page()

    assert view._model.loaded_count == 2 * PAGE
    assert view._model.window_start == 9 * PAGE
    assert view._model.total_items == 11 * PAGE + 1  # boundary + one sentinel row
    assert not view._model.total_is_exact


def test_a_column_can_be_a_sql_expression(db):
    band = case((Hit.score >= 5.0, "high"), else_="low")
    config = TableConfig(
        model_class=Hit,
        columns=[ColumnDef("name"), ColumnDef("band", expr=band)],
        page_size=10,
    )
    builder = QueryBuilder(db, config)
    builder.set_filters([FilterSpec("band", FilterOperator.EQ, "high")])
    rows, total = builder.fetch()

    assert total == N_ROWS // 2  # the expression can be filtered on, not just displayed
    assert {row["band"] for row in rows} == {"high"}


def test_to_query_spec_exports_the_filtered_selection(db):
    builder = QueryBuilder(db, _config())
    builder.set_filters([
        FilterSpec("score", FilterOperator.LTE, 3.0),
        FilterSpec("name", FilterOperator.ILIKE, "%lig%"),
    ])
    builder.set_sort([SortSpec("score", descending=True)])

    assert builder.to_query_spec() == {
        "table": "hit",
        "filters": {"score__lte": 3.0, "name__contains": "lig"},
        "order": ("-score",),
    }


def test_to_query_spec_refuses_what_it_cannot_express(db):
    builder = QueryBuilder(db, _config())
    builder.set_search("lig", ["name", "score"])
    with pytest.raises(ValueError, match="search"):
        builder.to_query_spec()


def test_simple_table_hides_filters_and_search():
    config = TableConfig(
        model_class=Hit,
        columns=[ColumnDef("name"), ColumnDef("score")],
        show_filters=False,
        show_search=False,
    )
    assert not any(c.filterable or c.searchable for c in config.columns)
