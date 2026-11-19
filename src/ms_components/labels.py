"""Labels shared by the components."""
from __future__ import annotations

import math

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QTextEdit


class ElidedLabel(QLabel):
    """A label that never widens its row: what does not fit ends in an ellipsis. `text()` is the
    whole text."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = str(text)
        self.updateGeometry()
        self._elide()

    def text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 4, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._full, Qt.ElideRight, self.width()))


class WrappedText(QTextEdit):
    """Read-only wrapped text that is as tall as its lines, up to `max_lines`, and scrolls past them.

    A word-wrapped QLabel in a layout sized to its content (SetMinimumSize) gets the height of a
    narrower width and clips its first and last lines. This one measures its own document at the
    width it is drawn at, again on every resize. It draws no frame or background, like a label;
    colour it with a style sheet (`color: ...`). `text()` is the whole text, surrounding blank
    lines dropped."""

    #: The theme styles every QTextEdit as an input (border, padding): that drew a box and a
    #: scroll bar around the text, and the padding was not in the height `_fit` asked for. Kept
    #: in this widget's own sheet, which outranks the application's, whatever a caller adds.
    _PLAIN = "QTextEdit { border: none; padding: 0; background: transparent; }"

    def __init__(self, text: str = "", parent=None, *, max_lines: int = 6) -> None:
        super().__init__(parent)
        self._max_lines = max(1, int(max_lines))
        self.setReadOnly(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        palette = self.viewport().palette()
        palette.setColor(QPalette.ColorRole.Base, Qt.transparent)
        self.viewport().setPalette(palette)
        self.viewport().setAutoFillBackground(False)
        self.document().setDocumentMargin(0)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self.setPlainText(str(text or "").strip())
        self._fit()

    def text(self) -> str:
        return self.toPlainText()

    def setStyleSheet(self, sheet: str) -> None:  # noqa: N802
        """`sheet` on top of the plain look; bare declarations ("color: ...") apply to the text."""
        sheet = str(sheet or "").strip()
        if sheet and "{" not in sheet:
            sheet = f"QTextEdit {{ {sheet} }}"
        super().setStyleSheet(f"{self._PLAIN}\n{sheet}")
        self._fit()

    def _fit(self) -> None:
        document = self.document()
        document.setTextWidth(self.viewport().width())
        cap = self._max_lines * self.fontMetrics().lineSpacing()
        # Rounded up: a fraction of a pixel short still brought up the scroll bar, which then
        # took its width from the text. It only ever shows past `max_lines`.
        needed = math.ceil(document.size().height())
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if needed > cap else Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(min(needed, cap) + 2 * self.frameWidth())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self._fit()  # another width wraps into another number of lines
