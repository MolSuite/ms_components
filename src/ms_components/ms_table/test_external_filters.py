"""External filter-overlay contract for QueryBuilder.

A host (e.g. a tool driving a shared table) can impose transient filters by key
that compose in AND with the user's interactive filters without touching them,
and clearing a key restores the exact prior filter set.

Run: python -m ms_components.ms_table.test_external_filters
"""
from .table_config import TableConfig, ColumnDef, FilterSpec, FilterOperator
from .query_builder import QueryBuilder


class _Attr:
    def __init__(self, name):
        self.name = name


class _Mol:
    id = _Attr("id")
    mw = _Attr("mw")
    is_receptor = _Attr("is_receptor")


def _builder():
    cfg = TableConfig(
        model_class=_Mol,
        columns=[ColumnDef("id", label="ID")],
        default_filters=[FilterSpec("is_receptor", FilterOperator.EQ, True)],
    )
    return QueryBuilder(db=None, config=cfg)


def test_overlay_composes_and_restores():
    qb = _builder()
    assert [f.field for f in qb._all_filters()] == ["is_receptor"]

    # user column filter
    qb.set_filters([
        FilterSpec("is_receptor", FilterOperator.EQ, True),
        FilterSpec("mw", FilterOperator.GTE, 100),
    ])

    # a tool overlay stacks in AND; user filters stay intact
    qb.set_external_filters("tool.filter", [FilterSpec("id", FilterOperator.GTE, 5)])
    assert {f.field for f in qb._all_filters()} == {"is_receptor", "mw", "id"}
    assert [f.field for f in qb.active_filters] == ["is_receptor", "mw"]

    # a second key stacks independently
    qb.set_external_filters("tool.other", [FilterSpec("mw", FilterOperator.EQ, 42)])
    assert len(qb._all_filters()) == 4

    # clearing one key restores only the prior set
    qb.clear_external_filters("tool.other")
    assert {f.field for f in qb._all_filters()} == {"is_receptor", "mw", "id"}
    qb.clear_external_filters("tool.filter")
    assert {f.field for f in qb._all_filters()} == {"is_receptor", "mw"}

    # empty overlay == clear
    qb.set_external_filters("tool.filter", [FilterSpec("id", FilterOperator.EQ, 1)])
    qb.set_external_filters("tool.filter", [])
    assert {f.field for f in qb._all_filters()} == {"is_receptor", "mw"}


if __name__ == "__main__":
    test_overlay_composes_and_restores()
    print("OK: overlay composes in AND, clears by key, restores prior set")
