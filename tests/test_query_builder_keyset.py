"""Table navigation: keyset under infinite scroll, expression columns, export to QuerySpec.

What deserves a test is that page N does not cost N times the first one (no OFFSET), that the
composite cursor does not skip rows when the sort ties, and that memory stays a bounded window.
"""
from __future__ import annotations

from typing import Optional

import pytest
from sqlalchemy import case
from sqlalchemy.pool import StaticPool
from PySide6.QtCore import QThreadPool
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
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[Hit.__table__])
    with Session(engine) as session:
        for i in range(N_ROWS):
            # score tied on purpose: the PK tie-break is what makes the cursor correct.
            session.add(Hit(id=i + 1, name=f"lig-{i:05d}", score=float(i % 10)))
        session.commit()
    return _Db(engine)


def _settle(app) -> None:
    """Let the table's worker queries finish and deliver their results."""
    for _ in range(5):
        QThreadPool.globalInstance().waitForDone()
        app.processEvents()


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


def test_infinite_scroll_replaces_old_pages_and_counts_once(db, monkeypatch):
    """One COUNT per refresh, none per scrolled page: "100+ records" is not an answer to
    "how many are there", but paying for a COUNT on every page would be."""
    app = QApplication.instance() or QApplication(["ms-table-window-test"])
    view = SmartTableView(db, _config(infinite_cache_pages=2, max_loaded_rows=N_ROWS))
    _settle(app)  # the COUNT runs on a worker
    assert view._model.total_items == N_ROWS and view._model.total_is_exact

    monkeypatch.setattr(view._builder, "count", lambda: pytest.fail("scrolling must not COUNT"))
    for _ in range(10):
        view.load_next_page()

    assert view._model.loaded_count == 2 * PAGE  # the window still slides
    assert view._model.window_start == 9 * PAGE
    assert view._model.total_items == N_ROWS
    assert view._infinite_loaded_end == 11 * PAGE  # the frontier, which is what the label shows


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


def test_refresh_goes_back_to_the_top(db):
    """refresh() reloads from the top, so the scrollbar goes there too: left deep down it
    would jump to a page of a query that no longer exists (a scope push on 3.85M rows
    froze the app on that jump)."""
    app = QApplication.instance() or QApplication(["ms-table-refresh-test"])
    view = SmartTableView(db, _config(infinite_cache_pages=3, max_loaded_rows=N_ROWS))
    view.resize(600, 400)
    view.show()
    _settle(app)
    for _ in range(2):
        view.load_next_page()
    view._table.verticalScrollBar().setValue(2 * PAGE + 10)
    app.processEvents()

    view.refresh()
    _settle(app)

    assert view._table.verticalScrollBar().value() == 0
    last = view._viewport_row_capacity() - 1
    assert view._model.is_row_loaded(last) and view._model.get_raw_object(last).id == last + 1
    view.close()


def test_a_scrollbar_jump_loads_on_a_worker_and_drops_stale_results(db):
    """A drag to the end loads behind an overlay and lands on the right rows; a refresh
    while a jump is in flight wins over the jump's late result."""
    app = QApplication.instance() or QApplication(["ms-table-jump-test"])
    view = SmartTableView(db, _config(infinite_cache_pages=3, max_loaded_rows=N_ROWS))
    view.resize(600, 400)
    view.show()
    _settle(app)

    target = N_ROWS - 50
    view._table.verticalScrollBar().setValue(target)
    assert view._loading_overlay.isVisible()
    _settle(app)
    assert not view._loading_overlay.isVisible()
    first = view._table.verticalScrollBar().value()
    for row in (first, first + view._viewport_row_capacity() - 1):
        assert view._model.get_raw_object(row).id == row + 1

    view._table.verticalScrollBar().setValue(N_ROWS // 2)  # jump, then refresh before it lands
    view.refresh()
    _settle(app)
    assert view._model.window_start == 0 and view._model.get_raw_object(0).id == 1
    view.close()


def test_rows_added_after_a_short_last_page_get_fetched_not_left_blank():
    """A running job: the first load brought 3 rows, refresh_counts() then says 30. The
    short page must be fetched again, or rows 3..29 show as blank rows forever."""
    app = QApplication.instance() or QApplication(["ms-table-tail-test"])
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[Hit.__table__])
    add = lambda ids: (lambda s: (s.add_all([Hit(id=i, name=f"l{i}") for i in ids]), s.commit()))(Session(engine))
    add(range(1, 4))
    view = SmartTableView(_Db(engine), _config())
    view.resize(600, 900)
    view.show()
    app.processEvents()
    assert view._model.loaded_count == 3

    for end in (11, 31):  # the job keeps going: every tick, more rows
        add(range(view._model.rowCount() + 1, end))
        assert view.refresh_counts()
        _settle(app)
        assert view._model.rowCount() == end - 1
        assert [view._model.get_raw_object(row).id for row in range(end - 1)] == list(range(1, end))
    view.close()



class Gap(SQLModel, table=True):
    __tablename__ = "gap"
    id: Optional[int] = Field(default=None, primary_key=True)
    score: Optional[float] = None


@pytest.mark.parametrize("descending", [False, True])
def test_keyset_walks_a_null_block_longer_than_a_page(descending):
    """A ΔΔG column is NULL for every ligand without that off-target: the walk must keep
    the whole null block (ascending: first; descending: last), not drop it after page 1."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[Gap.__table__])
    with Session(engine) as session:
        session.add_all([Gap(id=i, score=None if i % 3 else float(i)) for i in range(1, 351)])
        session.commit()
    config = TableConfig(model_class=Gap, columns=[ColumnDef("score")], page_size=PAGE,
                         load_mode=TableLoadMode.INFINITE,
                         default_sort=[SortSpec("score", descending=descending)])
    builder = QueryBuilder(_Db(engine), config)
    seen, cursor = [], None
    while True:
        rows, has_more = builder.fetch_window_after(cursor)
        seen += [row["__raw__"].id for row in rows]
        if not has_more:
            break
        cursor = builder.cursor_of(rows[-1])
    assert sorted(seen) == list(range(1, 351))


@pytest.mark.parametrize("backend", ["sqlite", "duckdb", "duckdb-rank"])
@pytest.mark.parametrize("sort", [None, SortSpec("score"), SortSpec("score", descending=True)])
def test_a_jump_lands_on_the_same_rows_as_offset(backend, sort, tmp_path, monkeypatch):
    """A scrollbar jump seeks by key (OFFSET over the key only, or row_number() on DuckDB)
    from the nearest known cursor; the page it lands on is what OFFSET would have given."""
    if backend.startswith("duckdb"):
        pytest.importorskip("duckdb_engine")
    if backend == "duckdb-rank":  # the row_number() arm, normally only past 100k rows
        monkeypatch.setattr("ms_components.ms_table.query_builder.DUCKDB_RANK_FROM", 0)
    engine = create_engine("sqlite://" if backend == "sqlite" else f"duckdb:///{tmp_path / 'hits.duckdb'}")
    with engine.begin() as conn:  # duckdb-engine has no SERIAL, so not create_all()
        conn.exec_driver_sql("CREATE TABLE hit (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, score FLOAT NOT NULL)")
    with Session(engine) as session:
        session.add_all(Hit(id=i + 1, name=f"lig-{i:05d}", score=float(i % 10)) for i in range(N_ROWS))
        session.commit()
    builder = QueryBuilder(_Db(engine), _config())
    if sort is not None:
        builder.set_sort([sort])
    with Session(engine) as session:
        expected = [hit.id for hit in session.exec(builder._build_base_statement()).all()]

    for page in (0, 1, 17, N_ROWS // PAGE - 1):
        rows, has_more = builder.fetch_window_at(page)
        assert [row["__raw__"].id for row in rows] == expected[page * PAGE:(page + 1) * PAGE]
        assert has_more == (page < N_ROWS // PAGE - 1)
    anchor_rows, _ = builder.fetch_window_at(9)  # walk on from page 10's cursor
    rows, _ = builder.fetch_window_at(30, anchor=builder.cursor_of(anchor_rows[-1]), anchor_page=10)
    assert [row["__raw__"].id for row in rows] == expected[30 * PAGE:31 * PAGE]
    assert builder.fetch_window_at(N_ROWS // PAGE + 5) == ([], False)
