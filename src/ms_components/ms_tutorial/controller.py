"""Attach a tour to existing widgets/signals without changing their slots."""
from __future__ import annotations

from collections.abc import Callable, Mapping
import weakref

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal, SignalInstance, Slot
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from shiboken6 import isValid

from .bindings import TutorialEvent, TutorialTarget
from .models import Tutorial, TutorialStep
from .overlay import TutorialOverlay


class _EventRelay(QObject):
    """Capture arbitrary signal arguments; evaluate them only in the UI thread."""
    received = Signal(object)

    def __init__(self, event: TutorialEvent, callback, parent: QObject):
        super().__init__(parent)
        self.binding = event
        self.callback = callback
        self.active = True
        self.received.connect(self.deliver, Qt.ConnectionType.QueuedConnection)
        source = event.signal if isinstance(event.signal, SignalInstance) else event.signal()
        self.connection = source.connect(self.capture)

    def capture(self, *args):
        self.received.emit(args)

    @Slot(object)
    def deliver(self, args):
        if self.active:
            self.callback(self.binding, args)

    def close(self):
        self.active = False
        QObject.disconnect(self.connection)
        self.deleteLater()


class TutorialController(QObject):
    """One active tour, with Python bindings and plain-data content.

    Targets may belong to different windows or dialogs. ``prepare`` only reveals
    the relevant UI; the component never submits jobs or invokes business actions.
    """
    started = Signal(str)
    step_changed = Signal(str, int)
    finished = Signal(str)
    cancelled = Signal(str)
    failed = Signal(str, str)

    def __init__(self, *, targets: Mapping[str, TutorialTarget],
                 events: Mapping[str, TutorialEvent] | None = None,
                 instruction_provider: Callable[[TutorialStep], str] | None = None,
                 dim_background: bool = True,
                 close_only: bool = False,
                 click_only_close: bool = False,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.targets = dict(targets)
        self.events = dict(events or {})
        self.instruction_provider = instruction_provider
        self.dim_background = dim_background
        self.close_only = close_only
        self.click_only_close = click_only_close
        self._tutorial: Tutorial | None = None
        self._index = -1
        self._completed: set[str] = set()
        self._overlay: TutorialOverlay | None = None
        self._target: QWidget | None = None
        self._relay: _EventRelay | None = None
        self._previous_focus = None
        self._tracker = QTimer(self)
        self._tracker.setInterval(80)
        self._tracker.timeout.connect(self.refresh)

    @property
    def is_active(self) -> bool:
        return self._tutorial is not None

    @property
    def index(self) -> int:
        return self._index

    @property
    def current_step(self) -> TutorialStep | None:
        return self._tutorial.steps[self._index] if self.is_active and self._index >= 0 else None

    @property
    def overlay(self) -> TutorialOverlay | None:
        """The current window's overlay; replaced when the tour moves between windows."""
        return self._overlay if self._overlay is not None and isValid(self._overlay) else None

    def start(self, tutorial: Tutorial):
        """Validate bindings before replacing the active tour. Must run in the UI thread."""
        for step in tutorial.steps:
            if self.close_only and step.advance_on is None:
                raise ValueError("Close-only tutorials require an event for every step")
            if not isinstance(self.targets.get(step.target), TutorialTarget):
                raise ValueError(f"Unregistered tutorial target: {step.target}")
            if step.advance_on is not None and not isinstance(self.events.get(step.advance_on), TutorialEvent):
                raise ValueError(f"Unregistered tutorial event: {step.advance_on}")
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("TutorialController requires a QApplication")
        self.stop()
        focus = app.focusWidget()
        self._previous_focus = weakref.ref(focus) if focus is not None else None
        self._tutorial = tutorial
        self._completed.clear()
        app.installEventFilter(self)
        self._tracker.start()
        self.started.emit(tutorial.id)
        if self._tutorial is tutorial:
            self._show_step(0)

    @Slot()
    def stop(self):
        """Cancel and disconnect only the tutorial's own signal subscription."""
        if self.is_active:
            tutorial_id = self._cleanup()
            self.cancelled.emit(tutorial_id)

    @Slot()
    def next(self):
        step = self.current_step
        if step is None or (step.advance_on is not None and step.id not in self._completed):
            return
        if self._index == len(self._tutorial.steps) - 1:
            self.finished.emit(self._cleanup())
        else:
            self._show_step(self._index + 1)

    @Slot()
    def back(self):
        if self.is_active and self._index > 0:
            self._show_step(self._index - 1)

    def _disconnect_event(self):
        if self._relay is not None:
            self._relay.close()
            self._relay = None

    def _cleanup(self) -> str:
        tutorial_id = self._tutorial.id
        self._tutorial = None
        self._index = -1
        self._tracker.stop()
        QApplication.instance().removeEventFilter(self)
        self._disconnect_event()
        if self.overlay is not None:
            self._overlay.hide()
            self._overlay.deleteLater()
        self._overlay = None
        self._target = None
        focus = self._previous_focus() if self._previous_focus is not None else None
        self._previous_focus = None
        if focus is not None and isValid(focus) and focus.isVisible() and focus.isEnabled():
            focus.setFocus()
        return tutorial_id

    def _fail(self, message: str):
        tutorial_id = self._cleanup()
        self.failed.emit(tutorial_id, message)

    def _show_step(self, index: int):
        self._disconnect_event()
        self._index = index
        step = self.current_step
        try:
            binding = self.targets[step.target]
            if binding.prepare is not None:
                binding.prepare()
            source = binding.widget
            target = source() if callable(source) else source
            # A step starts on a visible target; only a target that hides mid-step just hides the
            # overlay (and comes back). Otherwise the tour would stay active, unseen, eating Escape.
            if isinstance(target, QWidget) and isValid(target) and not target.isVisible():
                raise ValueError(f"Target '{step.target}' is hidden; provide a prepare callback")
            self.refresh()
            if not self.is_active:
                return
            if step.advance_on is not None:
                self._relay = _EventRelay(self.events[step.advance_on], self._on_event, self)
            self.step_changed.emit(step.id, index)
            if self.overlay is not None and self.overlay.isVisible():
                if step.advance_on is not None and self._target.isEnabled():
                    self._target.setFocus()
                else:
                    self.overlay.focus_guide()
            if step.advance_on is not None and step.id not in self._completed:
                check = self.events[step.advance_on].is_complete
                if check is not None and check():
                    self._completed.add(step.id)
                    self.next()
        except Exception as exc:
            if self.is_active:
                self._fail(f"Cannot show tutorial step '{step.id}': {exc}")

    @Slot()
    def refresh(self):
        """Resolve the current target and instructions after an application UI change."""
        step = self.current_step
        if step is None:
            return
        try:
            source = self.targets[step.target].widget
            target = source() if callable(source) else source
            if not isinstance(target, QWidget) or not isValid(target):
                raise ValueError(f"Target '{step.target}' is unavailable")
            self._target = target
            if not target.isVisible():
                if self.overlay is not None:
                    self.overlay.hide()
                else:
                    raise ValueError(f"Target '{step.target}' is hidden; provide a prepare callback")
                return
            host = target.window()
            if self.overlay is None or self.overlay.parentWidget() is not host:
                if self.overlay is not None:
                    self.overlay.hide()
                    self.overlay.deleteLater()
                self._overlay = TutorialOverlay(host, dim_background=self.dim_background, close_only=self.close_only,
                                                click_only_close=self.click_only_close)
                self._overlay.next_requested.connect(self.next)
                self._overlay.back_requested.connect(self.back)
                self._overlay.exit_requested.connect(self.stop)
                self.destroyed.connect(self._overlay.deleteLater)
            if self.overlay.step is not step:
                self.overlay.set_step(self._tutorial.title, step, self._index, len(self._tutorial.steps))
            if self.instruction_provider is not None:
                self.overlay.set_text(self.instruction_provider(step))
            self.overlay.next_button.setEnabled(step.advance_on is None or step.id in self._completed)
            region = self.targets[step.target].rect
            self.overlay.reposition(target, interactive=step.advance_on is not None,
                                    rect=region() if region is not None else None)
        except Exception as exc:
            self._fail(f"Cannot resolve tutorial step '{step.id}': {exc}")

    def _on_event(self, event: TutorialEvent, args: tuple):
        if not self.is_active:
            return
        try:
            if event.accept is not None and not event.accept(*args):
                return
        except Exception as exc:
            self._fail(f"Tutorial event validation failed: {exc}")
            return
        self._completed.add(self.current_step.id)
        self.next()

    @Slot(int)
    def _on_dialog_finished(self, result: int):
        if self.is_active:
            if result == QDialog.DialogCode.Accepted:
                self.refresh()
            else:
                self.stop()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self.is_active or not isinstance(watched, QWidget) or self.overlay is None:
            return False
        if watched.window() is not self.overlay.window():
            return False
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            if not self.click_only_close:
                self.stop()
            return True
        if (self.click_only_close and watched is self.overlay.exit_button
                and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)):
            return True
        if event.type() == QEvent.Type.Close and watched is self.overlay.parentWidget():
            if isinstance(watched, QDialog):
                self.overlay.hide()
                watched.finished.connect(self._on_dialog_finished, Qt.ConnectionType.SingleShotConnection)
                return False
            self.stop()
            return False
        if not self.overlay.isVisible():
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        allowed = watched is self.overlay or self.overlay.isAncestorOf(watched)
        if self.current_step.advance_on is not None and self._target is not None and isValid(self._target):
            allowed |= watched is self._target or self._target.isAncestorOf(watched)
        if event.type() == QEvent.Type.FocusIn and not allowed:
            if (self.click_only_close and self.current_step.advance_on is not None
                    and self._target is not None and isValid(self._target)):
                self._target.setFocus()
            else:
                self.overlay.focus_guide()
        return not allowed and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
