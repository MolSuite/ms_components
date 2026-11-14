"""SVG icons recoloured (currentColor → a palette colour) and rendered once per (file, colour, size, dpr).

A theme change asks for a new colour, so it is a new key: nothing to invalidate.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


# ponytail: unbounded in practice (icons x themes x sizes is a few hundred); maxsize caps a leak.
@lru_cache(maxsize=1024)
def svg_pixmap(path: str | Path, color_hex: str, width: int, height: int, dpr: float) -> QPixmap:
    svg = Path(path).read_bytes().replace(b"currentColor", color_hex.encode())
    pixmap = QPixmap(max(1, round(width * dpr)), max(1, round(height * dpr)))
    pixmap.fill(Qt.GlobalColor.transparent)
    with QPainter(pixmap) as painter:
        QSvgRenderer(QByteArray(svg)).render(painter)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


@lru_cache(maxsize=1024)
def svg_icon(path: str | Path, color_hex: str, width: int, height: int, dpr: float) -> QIcon:
    return QIcon(svg_pixmap(path, color_hex, width, height, dpr))


def widget_svg_icon(widget, path: str | Path, size: QSize | None = None) -> QIcon:
    """`path` in the widget's button-text colour at its device pixel ratio (16 px by default)."""
    size = size or QSize(16, 16)
    return svg_icon(str(path), widget.palette().buttonText().color().name(), size.width(), size.height(),
                    max(1.0, widget.devicePixelRatioF()))


__all__ = ["svg_icon", "svg_pixmap", "widget_svg_icon"]
