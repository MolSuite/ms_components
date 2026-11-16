"""Table input signals, independent of any viewer or data model."""

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QApplication, QWidget


class TableInteraction(QObject):
    """Observe one Qt table or the tables under a window, including tables added later.

    ``pressed(view, index, modifiers)`` precedes native selection changes;
    ``reselected`` reports a click on an already selected cell.
    """

    pressed = Signal(object, object, Qt.KeyboardModifiers)
    reselected = Signal(object, object, Qt.KeyboardModifiers)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._pressed = None
        if isinstance(parent, QAbstractItemView):
            parent.viewport().installEventFilter(self)
        else:
            QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        kind = event.type()  # read once: window-wide, this runs for every event in the app
        if (kind == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and isinstance(watched, QWidget)):
            view = watched.parentWidget()
            if (isinstance(view, QAbstractItemView) and watched is view.viewport()
                    and (view is self.parent() or self.parent().isAncestorOf(view))):
                index = view.indexAt(event.position().toPoint())
                if index.isValid():
                    self._pressed = (view, index, event.modifiers(), view.selectionModel().isSelected(index))
                    self.pressed.emit(view, index, event.modifiers())
        elif kind == QEvent.Type.MouseButtonRelease and self._pressed is not None:
            view, index, modifiers, was_selected = self._pressed
            self._pressed = None
            if (event.button() == Qt.MouseButton.LeftButton and watched is view.viewport()
                    and was_selected and view.indexAt(event.position().toPoint()) == index):
                self.reselected.emit(view, index, modifiers)
        return False  # never touch a deleted `watched` (teardown re-enters filters; errors chain and balloon)
