from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMenu, QToolButton
from sqlalchemy.orm import sessionmaker
from sqlmodel import Field, Session, SQLModel, create_engine

from ms_components.ms_table import (
    ColumnDef,
    SmartTableView,
    TableConfig,
    ToolbarAction,
)


class _ToolbarRow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)


def _app() -> QApplication:
    return QApplication.instance() or QApplication(["table-toolbar-test"])


def _db():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session)

    class DB:
        def get_session(self):
            return factory()

    return DB()


def _table(*, collapsible: bool = False) -> SmartTableView:
    return SmartTableView(
        db=_db(),
        config=TableConfig(
            model_class=_ToolbarRow,
            columns=[ColumnDef("id")],
            embedded_controls=True,
            show_record_count=False,
            toolbar_collapsible=collapsible,
            toolbar_left=[ToolbarAction(label="Injected action")],
        ),
    )


def test_embedded_toolbar_overflow_contains_builtin_actions():
    app = _app()
    table = _table()
    table.resize(240, 200)
    table.show()
    app.processEvents()

    # Qt keeps the first action visible and moves the remaining commands into
    # the extension menu. A non-zero usable width is required for the extension
    # button itself.
    table._toolbar.setFixedWidth(60)
    app.processEvents()

    extension = table._toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
    assert extension is not None and not extension.isHidden()
    menu = extension.menu()
    assert isinstance(menu, QMenu)
    overflow_labels = {action.text() for action in menu.actions()}
    assert {"Export", "Reload", "Settings", "Injected action"} <= overflow_labels

    # Built-ins keep icon+text metadata in the requested order while the toolbar
    # displays icons by default. Export and Settings retain their option menus.
    toolbar_actions = table._toolbar.actions()
    builtin_labels = [action.text() for action in toolbar_actions if action in table._builtin_actions]
    assert builtin_labels == ["Columns", "Export", "Reload", "Settings"]
    assert table._toolbar.toolButtonStyle() == Qt.ToolButtonIconOnly
    assert all(action.text() and not action.icon().isNull() for action in table._builtin_actions)
    assert table._columns_action.menu() is None
    assert [action.text() for action in table._export_action.menu().actions()] == ["CSV…"]
    assert table._settings_action.menu() is not None

    # The native chevrons are replaced by a real hamburger icon.
    assert extension.text() == ""
    assert not extension.icon().isNull()
    assert extension.arrowType() == Qt.NoArrow
    assert extension.iconSize() == QSize(14, 14)
    assert extension.width() >= extension.iconSize().width() + 4
    assert table._toolbar_row.layout().contentsMargins().top() == 1
    assert table._toolbar_row.layout().contentsMargins().bottom() == 1

    table.close()


def test_overflow_menu_opens_on_hover():
    app = _app()
    table = _table()
    table.resize(240, 200)
    table.show()
    table._toolbar.setFixedWidth(60)
    app.processEvents()

    extension = table._overflow_btn
    menu = extension.menu()
    shown: list[bool] = []
    menu.aboutToShow.connect(lambda: shown.append(True))
    QTimer.singleShot(20, menu.close)

    QApplication.sendEvent(extension, QEvent(QEvent.Type.Enter))
    app.processEvents()

    assert shown
    table.close()


def test_collapsible_toolbar_hides_actions_not_action_widgets():
    _app()
    table = _table(collapsible=True)

    assert all(not action.isVisible() for action in table._builtin_actions)
    table._toggle_toolbar_collapsed()
    assert all(action.isVisible() for action in table._builtin_actions)

    table.close()
