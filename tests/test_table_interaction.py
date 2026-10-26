import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from sqlmodel import Field, SQLModel

from ms_components.ms_table import ColumnDef, SmartTableView, TableConfig


class _InteractionRow(SQLModel, table=True):
    id: int = Field(primary_key=True)


@pytest.fixture
def table(monkeypatch):
    app = QApplication.instance() or QApplication(["table-interaction-test"])
    monkeypatch.setattr(SmartTableView, "refresh", lambda self: None)
    widget = SmartTableView(
        db=object(), config=TableConfig(
            model_class=_InteractionRow, columns=[ColumnDef("id")], show_row_numbers=False))
    widget._model.load_data([
        {"id": number, "__raw__": _InteractionRow(id=number)} for number in (1, 2)
    ], 2, 1)
    widget.resize(320, 260)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


@pytest.mark.parametrize("modifiers", [Qt.NoModifier, Qt.ShiftModifier, Qt.ControlModifier])
def test_cell_pressed_reports_modifiers_before_selection_and_keeps_row_clicked(table, modifiers):
    events = []
    table.cell_pressed.connect(lambda obj, field, mods: events.append(
        ("pressed", obj.id, field, mods, table.get_selected_objects())))
    table.row_clicked.connect(lambda obj: events.append(("clicked", obj.id)))
    position = table.view.visualRect(table._model.index(1, 0)).center()
    QTest.mouseClick(table.view.viewport(), Qt.LeftButton, modifiers, position)
    assert events == [("pressed", 2, "id", modifiers, []), ("clicked", 2)]


def test_empty_space_emits_no_cell_press(table):
    pressed = []
    table.cell_pressed.connect(lambda *args: pressed.append(args))
    QTest.mouseClick(table.view.viewport(), Qt.LeftButton, Qt.NoModifier,
                     QPoint(10, table.view.viewport().height() - 2))
    assert pressed == []


def test_reselecting_a_row_has_its_own_signal_without_faking_a_selection_change(table):
    selected, reselected = [], []
    table.selection_changed.connect(lambda rows: selected.append([row.id for row in rows]))
    table.row_reselected.connect(lambda row: reselected.append(row.id))
    position = table.view.visualRect(table._model.index(1, 0)).center()
    QTest.mouseClick(table.view.viewport(), Qt.LeftButton, Qt.NoModifier, position)
    QTest.mouseClick(table.view.viewport(), Qt.LeftButton, Qt.NoModifier, position)
    assert selected == [[2]]
    assert reselected == [2]
