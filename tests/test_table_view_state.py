"""Qt-free unit test for SmartTableView.view_state / apply_view_state.

These methods carry the persistable-table-prefs logic (visible columns + sort);
we exercise them on a duck-typed stub so no QApplication or DB is needed.
"""
from __future__ import annotations

from types import SimpleNamespace

from ms_components.ms_table.smart_table_view import SmartTableView
from ms_components.ms_table.table_config import ColumnDef, SortSpec


def _stub():
    columns = [ColumnDef(field="name"), ColumnDef(field="mw"), ColumnDef(field="logp")]
    builder = SimpleNamespace(active_sorts=[], set_sort=lambda s: setattr(builder, "active_sorts", list(s)))
    return SimpleNamespace(
        _config=SimpleNamespace(columns=columns),
        _builder=builder,
        _install_delegates=lambda: None,
        _sync_header=lambda: None,
        refresh=lambda *a, **k: None,
    )


def test_view_state_reports_visible_columns_and_sort():
    stub = _stub()
    stub._config.columns[2].visible = False  # hide logp
    stub._builder.active_sorts = [SortSpec("mw", descending=True)]
    state = SmartTableView.view_state(stub)
    assert state["columns"] == ["name", "mw"]
    assert state["sort"] == [{"field": "mw", "descending": True}]


def test_apply_view_state_sets_visibility_and_sort():
    stub = _stub()
    SmartTableView.apply_view_state(stub, {"columns": ["mw"], "sort": [{"field": "name"}]})
    visible = [c.field for c in stub._config.columns if c.visible]
    assert visible == ["mw"]
    assert stub._builder.active_sorts == [SortSpec("name", descending=False)]


def test_apply_view_state_ignores_unknown_columns_and_empty():
    stub = _stub()
    SmartTableView.apply_view_state(stub, None)  # no-op
    assert all(c.visible for c in stub._config.columns)
    # A columns list referencing only unknown fields must not blank the table.
    SmartTableView.apply_view_state(stub, {"columns": ["ghost"]})
    assert all(c.visible for c in stub._config.columns)
