"""Table input signals, independent of any viewer or data model."""

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QWidget


class _Hub(QObject):
    """Where every table's `TableInteraction` repeats what it saw, for those that watch a window."""

    pressed = Signal(object, object, Qt.KeyboardModifiers)
    reselected = Signal(object, object, Qt.KeyboardModifiers)


_hub: _Hub | None = None


def _the_hub() -> _Hub:
    global _hub
    if _hub is None:
        _hub = _Hub()
    return _hub


class TableInteraction(QObject):
    """Observe one Qt table, or the tables under a window, including tables added later.

    ``pressed(view, index, modifiers)`` precedes native selection changes;
    ``reselected`` reports a click on an already selected cell.

    A window hears the tables that have one of their own (every `SmartTableView` has): a filter
    on the whole application, the way it was done before, put each of its events through Python,
    some 40 ms of every big view opened.
    """

    pressed = Signal(object, object, Qt.KeyboardModifiers)
    reselected = Signal(object, object, Qt.KeyboardModifiers)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._pressed = None
        hub = _the_hub()
        if isinstance(parent, QAbstractItemView):
            parent.viewport().installEventFilter(self)
        else:
            hub.pressed.connect(self._heard_pressed)
            hub.reselected.connect(self._heard_reselected)

    def _under(self, view) -> bool:
        return view is self.parent() or self.parent().isAncestorOf(view)

    def _heard_pressed(self, view, index, modifiers) -> None:
        if self._under(view):
            self.pressed.emit(view, index, modifiers)

    def _heard_reselected(self, view, index, modifiers) -> None:
        if self._under(view):
            self.reselected.emit(view, index, modifiers)

    def eventFilter(self, watched, event):
        view = self.parent()
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            index = view.indexAt(event.position().toPoint())
            if index.isValid():
                modifiers = event.modifiers()
                self._pressed = (index, modifiers, view.selectionModel().isSelected(index))
                self.pressed.emit(view, index, modifiers)
                _the_hub().pressed.emit(view, index, modifiers)
        elif event.type() == QEvent.Type.MouseButtonRelease and self._pressed is not None:
            index, modifiers, was_selected = self._pressed
            self._pressed = None
            if (event.button() == Qt.MouseButton.LeftButton and was_selected
                    and view.indexAt(event.position().toPoint()) == index):
                self.reselected.emit(view, index, modifiers)
                _the_hub().reselected.emit(view, index, modifiers)
        return super().eventFilter(watched, event)
