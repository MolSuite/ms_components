"""A PROGRESS column fills the share of the cell its fraction says, clamped to 0..1."""
from __future__ import annotations

import sqlmodel  # noqa: F401  (pydantic before PySide6, or its lazy import breaks)
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QTableView

from ms_components.ms_table.cell_delegate import CellWidgetDelegate
from ms_components.ms_table.table_config import ColumnDef, ColumnKind


class _Model(QStandardItemModel):
    rows = [{"done": 0.5}, {"done": None}, {"done": 3.0}]

    def get_row_data(self, row):
        return self.rows[row]


def test_a_progress_column_fills_its_fraction_of_the_cell():
    app = QApplication.instance() or QApplication([])
    view, model = QTableView(), _Model(3, 1)
    view.setModel(model)
    delegate = CellWidgetDelegate(0, ColumnDef("done", kind=ColumnKind.PROGRESS), view)
    filled = []
    for row in range(3):
        image = QImage(200, 30, QImage.Format_ARGB32)
        image.fill(QColor("black"))
        option = QStyleOptionViewItem()
        option.widget, option.rect = view, image.rect()
        option.palette.setColor(QPalette.Highlight, QColor("red"))
        painter = QPainter(image)
        delegate.paint(painter, option, model.index(row, 0))
        painter.end()
        filled.append([image.pixelColor(x, 8) == QColor("red") for x in (20, 180)])
    assert filled == [[True, False], [False, False], [True, True]]
    assert app
