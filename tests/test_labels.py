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


def test_wrapped_text_stays_plain_under_a_theme_that_boxes_every_text_edit():
    """The theme gives every QTextEdit an input's border and padding: the Project dialog's
    path drew as a box with a scroll bar, its lines cut by the padding `_fit` did not count."""
    app = QApplication.instance() or QApplication([])
    before = app.styleSheet()
    app.setStyleSheet("QTextEdit { border: 1px solid red; border-radius: 4px; padding: 3px 6px; }")
    try:
        host, view = _shown("/home/user/molsuite_projects/AmpC_DUDE-Z_virtual_screening_Unidock " * 2,
                            260, max_lines=8)
        view.setStyleSheet("color: palette(placeholder-text);")  # as a caller colours it
        for _ in range(5):
            app.processEvents()
        assert view.frameWidth() == 0 and view.contentsMargins().top() == 0
        assert view.height() >= view.document().size().height()  # every line shows
        assert not view.verticalScrollBar().isVisible()
        assert "color: palette(placeholder-text)" in view.styleSheet()
        host.deleteLater()
    finally:
        app.setStyleSheet(before)
