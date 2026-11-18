from __future__ import annotations

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget, QLayout

from ms_components.labels import WrappedText


def _shown(text: str, width: int, max_lines: int = 3) -> tuple[QWidget, WrappedText]:
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setSizeConstraint(QLayout.SetMinimumSize)  # where a wrapped QLabel lost lines
    view = WrappedText(text, max_lines=max_lines)
    layout.addWidget(view)
    host.setFixedWidth(width)
    host.show()
    for _ in range(5):
        app.processEvents()
    return host, view


def test_wrapped_text_is_as_tall_as_its_lines():
    host, view = _shown("One short line.", 400)
    line = view.fontMetrics().lineSpacing()
    assert view.height() >= line and view.height() < 2 * line
    assert not view.verticalScrollBar().isVisible()
    host.deleteLater()


def test_wrapped_text_stops_at_max_lines_and_scrolls_past_them():
    long = "Fixed-seed docking of a ligand pair. " * 30
    host, view = _shown(long, 300, max_lines=3)
    line = view.fontMetrics().lineSpacing()
    assert view.height() == 3 * line
    assert view.document().size().height() > view.height()  # the rest is a scroll away
    assert view.verticalScrollBar().maximum() > 0
    host.deleteLater()


def test_wrapped_text_refits_when_it_gets_wider():
    text = "word " * 40
    host, view = _shown(text, 200, max_lines=20)
    narrow = view.height()
    host.setFixedWidth(600)
    for _ in range(5):
        QApplication.processEvents()
    assert view.height() < narrow
    host.deleteLater()


def test_wrapped_text_drops_surrounding_blank_lines():
    app = QApplication.instance() or QApplication([])
    view = WrappedText("\n\n  Description.  \n\n")
    assert view.text() == "Description."
    assert view.isReadOnly()
    del app
