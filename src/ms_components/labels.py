"""Labels shared by the components."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel


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
