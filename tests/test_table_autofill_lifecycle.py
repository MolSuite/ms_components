"""A deferred infinite-scroll fill must not outlive the table it accesses."""
import sys

import pytest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from sqlalchemy.orm import sessionmaker
from sqlmodel import Field, Session, SQLModel, create_engine

from ms_components.ms_table import ColumnDef, SmartTableView, TableConfig, TableLoadMode


class _AutofillRow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)


@pytest.mark.parametrize("destroy", ["table", "view"])
def test_pending_autofill_is_cancelled_when_its_table_is_destroyed(monkeypatch, destroy):
    app = QApplication.instance() or QApplication([])
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[_AutofillRow.__table__])
    factory = sessionmaker(bind=engine, class_=Session)
    with factory() as session:
        session.add(_AutofillRow())
        session.commit()

    class DB:
        def get_session(self):
            return factory()

    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, error, tb: errors.append(error))
    view = SmartTableView(DB(), TableConfig(model_class=_AutofillRow, columns=[ColumnDef("id")],
                                           load_mode=TableLoadMode.INFINITE))
    assert view._infinite_autofill_scheduled
    delete(view._table if destroy == "table" else view)
    app.processEvents()
    assert errors == []
    if destroy == "table":
        delete(view)
    engine.dispose()
