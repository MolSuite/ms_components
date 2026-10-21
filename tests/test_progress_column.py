"""A PROGRESS column fills the share of the cell its fraction says, clamped to 0..1,
in the tone its row asks for."""
from __future__ import annotations

import sqlmodel  # noqa: F401  (pydantic before PySide6, or its lazy import breaks)
from PySide6.QtGui import QColor, QImage, QPainter, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QTableView

from ms_components import theme
from ms_components.ms_table.cell_delegate import CellWidgetDelegate
from ms_components.ms_table.table_config import ColumnDef, ColumnKind


class _Model(QStandardItemModel):
    rows = [{"done": 0.5}, {"done": None}, {"done": 3.0, "state": "failed"}]

    def get_row_data(self, row):
        return self.rows[row]


def _tone(pixel: QColor) -> str:
    if pixel.green() - pixel.red() > 40:
        return "green"
    return "red" if pixel.red() - pixel.green() > 40 else "track"


def test_a_progress_column_fills_its_fraction_of_the_cell():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(theme.base_qss() + theme.tone_qss(theme.THEMES["dracula"]))
    try:
        view, model = QTableView(), _Model(3, 1)
        view.setModel(model)
        column = ColumnDef("done", kind=ColumnKind.PROGRESS,
                           progress_tone=lambda row: "red" if row.get("state") else "green")
        delegate = CellWidgetDelegate(0, column, view)
        filled = []
        for row in range(3):
            image = QImage(200, 30, QImage.Format_ARGB32)
            image.fill(QColor("black"))
            option = QStyleOptionViewItem()
            option.widget, option.rect = view, image.rect()
            painter = QPainter(image)
            delegate.paint(painter, option, model.index(row, 0))
            painter.end()
            filled.append([_tone(image.pixelColor(x, 8)) for x in (20, 180)])
        assert filled == [["green", "track"], ["track", "track"], ["red", "red"]]
    finally:
        app.setStyleSheet("")
