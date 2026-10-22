"""A faint, centred icon painted under a widget's own children (welcome pages, empty states)."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QWidget


class Backdrop(QWidget):
    """``icon`` drawn at ``opacity``, scaled to 80 % of the shorter side; ``None`` draws nothing."""

    # One fixed-size render, scaled: asking the icon for each widget size would cache a
    # multi-MB pixmap per size (~1 GB after a long window resize with a caching icon engine).
    RENDER_PX = 512

    def __init__(self, icon: QIcon | None = None, parent: QWidget | None = None, *, opacity: float = 0.06):
        super().__init__(parent)
        self._icon = icon
        self._opacity = opacity

    def paintEvent(self, event) -> None:
        if self._icon is not None:
            side = int(min(self.width(), self.height()) * 0.8)
            painter = QPainter(self)
            painter.setOpacity(self._opacity)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(QRect((self.width() - side) // 2, (self.height() - side) // 2, side, side),
                               self._icon.pixmap(QSize(self.RENDER_PX, self.RENDER_PX)))
            painter.end()
        super().paintEvent(event)


__all__ = ["Backdrop"]
