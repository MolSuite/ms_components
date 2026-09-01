"""Shift+wheel scrolls horizontally, the GTK/browser convention.

Qt has no such modifier: `QAbstractSlider::wheelEvent` reads Shift (and Ctrl) as
"scroll one page" on the *vertical* bar, so the event must be intercepted before
it reaches it. Instead of moving the bar by a made-up amount we hand the same
wheel event to the horizontal bar with the delta transposed and the modifier
cleared — the scroll speed then comes from Qt's own wheelScrollLines.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QWidget


class _ShiftHScrollFilter(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Exact match: Ctrl+Shift+wheel stays free for whoever wants to zoom.
        if event.type() != QEvent.Type.Wheel or event.modifiers() != Qt.KeyboardModifier.ShiftModifier:
            return False
        widget = obj if isinstance(obj, QWidget) else None
        while widget is not None and not isinstance(widget, QAbstractScrollArea):
            widget = widget.parentWidget()
        if widget is None:
            return False
        bar = widget.horizontalScrollBar()
        if bar.maximum() == 0:  # nothing to scroll sideways: let Qt do its thing
            return False
        angle, pixels = event.angleDelta(), event.pixelDelta()
        QApplication.sendEvent(
            bar,
            QWheelEvent(
                event.position(), event.globalPosition(),
                QPoint(pixels.y() or pixels.x(), 0),
                QPoint(angle.y() or angle.x(), 0),
                event.buttons(), Qt.KeyboardModifier.NoModifier,
                event.phase(), event.inverted(),
            ),
        )
        return True


def install_shift_hscroll(app: QApplication | None = None) -> None:
    """Enable Shift+wheel horizontal scrolling for every scroll area in the app."""
    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError("install_shift_hscroll requires a running QApplication")
    if getattr(app, "_shift_hscroll_filter", None) is not None:
        return
    filt = _ShiftHScrollFilter(app)
    app._shift_hscroll_filter = filt  # keep it alive (and make re-install a no-op)
    app.installEventFilter(filt)


def uninstall_shift_hscroll(app: QApplication | None = None) -> None:
    """Remove the application-wide filter before QApplication is destroyed."""
    app = app or QApplication.instance()
    if app is None:
        return
    filt = getattr(app, "_shift_hscroll_filter", None)
    if filt is None:
        return
    try:
        app.removeEventFilter(filt)
    finally:
        app._shift_hscroll_filter = None
