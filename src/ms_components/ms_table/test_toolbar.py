"""Self-check for the agnostic ms_table toolbar (zones + overflow + collapsible).

Run: QT_QPA_PLATFORM=offscreen python test_toolbar.py
Uses isHidden() (not isVisible()) because the widget tree is never shown.
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolButton
from sqlmodel import Field, Session, SQLModel, create_engine
from sqlalchemy.orm import sessionmaker

from ms_components.theme import apply_theme
from ms_components.ms_table import ColumnDef, SmartTableView, TableConfig, ToolbarAction


class _Thing(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = ""


def _db():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session)

    class DB:
        def get_session(self):
            return factory()

    return DB()


def main() -> None:
    QApplication.instance() or QApplication([])
    clicked: list = []

    cfg = TableConfig(
        model_class=_Thing,
        columns=[ColumnDef("id"), ColumnDef("name")],
        embedded_controls=True, show_record_count=True,
        toolbar_left=[ToolbarAction(label="Export", on_click=lambda o: clicked.append(("exp", o)))],
        toolbar_right=[ToolbarAction(label="Create Set", on_click=lambda o: clicked.append(("set", o)))],
    )
    t = SmartTableView(db=_db(), config=cfg)

    assert t._columns_action and t._refresh_btn and t._export_btn
    assert len(t._injected_actions) == 2
    assert t._toolbar.toolButtonStyle() == Qt.ToolButtonIconOnly

    # Overflow is QToolBar's job: wide → everything fits; narrow → extension button.
    # The bar's width is forced, not the view's: the table has its own minimum.
    app = QApplication.instance()
    t.resize(1200, 400); t.show(); app.processEvents()
    ext = t._toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
    assert ext is not None and ext.isHidden()
    t._toolbar.setFixedWidth(120); app.processEvents()
    assert not ext.isHidden(), "the narrow bar should show »"
    # The extension is the table's hamburger menu, not the native arrow.
    apply_theme("github_light", app)
    app.processEvents()
    assert ext.arrowType() == Qt.NoArrow
    assert ext.text() == ""
    assert not ext.icon().isNull()
    assert ext.width() >= 16, f"hamburger squashed: {ext.width()}px"
    t._toolbar.setFixedWidth(1000); app.processEvents()
    assert ext.isHidden()

    # The counter lives outside the bar: it never falls into the popup.
    assert t._result_count_label.parent() is t._toolbar_row

    # Injected click forwards the current selection (empty here).
    t._injected_actions[0][1].trigger()
    assert clicked == [("exp", [])], clicked

    # Icons / text / both: QToolBar provides it.
    t.set_toolbar_button_style(Qt.ToolButtonIconOnly)
    assert t._toolbar.toolButtonStyle() == Qt.ToolButtonIconOnly

    # set_toolbar_actions: a tool borrows the bar and gives it back.
    t.set_toolbar_actions("tool.dock", [ToolbarAction(label="Dock", on_click=lambda o: clicked.append(("dock", o)))])
    acts = t._toolbar.actions()
    assert [a.text() for a in t._keyed_actions["tool.dock"]] == ["Dock"]
    assert acts.index(t._keyed_actions["tool.dock"][0]) < acts.index(t._zone_anchor), "should land in the left zone"
    t._keyed_actions["tool.dock"][0].trigger()
    assert clicked[-1] == ("dock", [])
    # Re-pushing the same key replaces instead of accumulating.
    t.set_toolbar_actions("tool.dock", [ToolbarAction(label="Dock2", on_click=lambda o: None)])
    assert [a.text() for a in t._keyed_actions["tool.dock"]] == ["Dock2"]
    assert len([a for a in t._toolbar.actions() if a.text() == "Dock"]) == 0
    # Empty list == clear; the config's own zones survive.
    t.set_toolbar_actions("tool.dock", [])
    assert "tool.dock" not in t._keyed_actions
    assert [a.text() for a in t._toolbar.actions() if a.text() in {"Dock", "Dock2"}] == []
    assert len(t._injected_actions) == 2

    # A table configured without any toolbar still has to show a runtime action.
    t3 = SmartTableView(db=_db(), config=TableConfig(
        model_class=_Thing, columns=[ColumnDef("id")], embedded_controls=False, show_record_count=False))
    assert t3._toolbar is None
    t3.set_toolbar_actions("tool.x", [ToolbarAction(label="X", on_click=lambda o: None)])
    assert t3._toolbar is not None and t3._toolbar_row is t3.layout().itemAt(0).widget()
    assert [a.text() for a in t3._keyed_actions["tool.x"]] == ["X"]

    # Collapsible mode: manual toggle.
    cfg2 = TableConfig(
        model_class=_Thing, columns=[ColumnDef("id")], embedded_controls=True,
        toolbar_collapsible=True,
        toolbar_left=[ToolbarAction(label="A", on_click=lambda o: None)],
    )
    t2 = SmartTableView(db=_db(), config=cfg2)
    assert t2._actions_collapsed
    assert not t2._injected_actions[0][1].isVisible()
    t2._toggle_toolbar_collapsed()
    assert t2._injected_actions[0][1].isVisible()
    # A borrowed action obeys the same collapse state, whenever it arrives.
    t2._toggle_toolbar_collapsed()
    t2.set_toolbar_actions("tool.y", [ToolbarAction(label="Y", on_click=lambda o: None)])
    assert not t2._keyed_actions["tool.y"][0].isVisible()
    t2._toggle_toolbar_collapsed()
    assert t2._keyed_actions["tool.y"][0].isVisible()

    print("OK")
    sys.stdout.flush()
    os._exit(0)   # avoid pymol/Qt teardown segfault in headless


if __name__ == "__main__":
    main()
