"""Tour content is data; observing a UI action never changes the application's slots."""
import os
from threading import Thread

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMenuBar, QPushButton, QVBoxLayout, QWidget
from shiboken6 import isValid

from ms_components.ms_tutorial import (
    Tutorial, TutorialController, TutorialEvent, TutorialStep, TutorialTarget, load_tutorial,
)
from ms_components.theme import apply_theme


@pytest.fixture
def ui():
    app = QApplication.instance() or QApplication([])
    apply_theme("github_light", app)
    window = QWidget()
    window.resize(900, 640)
    layout = QVBoxLayout(window)
    button = QPushButton("Run")
    layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
    layout.addStretch()
    other = QPushButton("Other")
    layout.addWidget(other)
    controller = TutorialController(targets={"run": TutorialTarget(button), "other": TutorialTarget(other)},
                                    events={"clicked": TutorialEvent(button.clicked)}, parent=window)
    window.show()
    app.processEvents()
    yield app, window, button, other, controller
    controller.stop()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def tour(*, interactive=False):
    return Tutorial("demo", "Demo", (
        TutorialStep("input", "run", "Input", "Load the input.", "clicked" if interactive else None),
        TutorialStep("output", "other", "Output", "Review the output."),
    ))


def test_informative_tour_blocks_clicks_keys_and_shortcuts_without_event_bindings(ui):
    app, window, button, other, controller = ui
    controller.events.clear()  # Informative tours do not need any application signal.
    clicks = []
    button.clicked.connect(lambda: clicks.append("clicked"))
    shortcut = QShortcut(QKeySequence("Ctrl+R"), window)
    shortcut.activated.connect(lambda: clicks.append("shortcut"))
    controller.start(tour())
    overlay = controller.overlay
    assert QApplication.widgetAt(button.mapToGlobal(button.rect().center())) is overlay
    QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=overlay.hole.center())
    QTest.keyClick(button, Qt.Key.Key_Space)
    QTest.keyClick(overlay.next_button, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    assert clicks == []
    QTest.mouseClick(overlay.next_button, Qt.MouseButton.LeftButton)
    assert controller.index == 1
    QTest.mouseClick(overlay.back_button, Qt.MouseButton.LeftButton)
    assert controller.index == 0
    completed = []
    controller.finished.connect(completed.append)
    controller.next()
    controller.next()
    assert completed == ["demo"] and not controller.is_active
    assert not controller._tracker.isActive()


def test_interactive_tour_observes_existing_slot_and_unsubscribes(ui):
    app, window, button, other, controller = ui
    application_calls = []
    button.clicked.connect(lambda: application_calls.append("application slot"))
    controller.start(tour(interactive=True))
    assert not controller.overlay.next_button.isEnabled()
    controller.next()
    assert controller.index == 0
    assert QApplication.widgetAt(button.mapToGlobal(button.rect().center())) is button
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert controller.index == 1 and application_calls == ["application slot"]
    controller.back()
    assert controller.overlay.next_button.isEnabled()  # A completed step can be revisited.
    QTest.keyClick(button, Qt.Key.Key_Escape)
    assert not controller.is_active
    button.click()
    app.processEvents()
    assert application_calls == ["application slot", "application slot"]
    controller.start(tour(interactive=True))
    assert not controller.overlay.next_button.isEnabled()  # New runs reset tutorial progress.


class Emitter(QObject):
    done = Signal(str, str)


def test_completion_while_on_another_step_is_checked_on_return(ui):
    app, window, button, other, controller = ui
    emitter = Emitter()
    completed = set()
    controller.events["job.done"] = TutorialEvent(
        emitter.done, accept=lambda job, status: job == "expected" and status == "completed",
        is_complete=lambda: "expected" in completed,
    )
    controller.start(Tutorial("jobs", "Jobs", (
        TutorialStep("first", "run", "Input", "Review input."),
        TutorialStep("job", "run", "Run", "Wait.", "job.done"),
        TutorialStep("last", "other", "Output", "Review output."),
    )))
    controller.next()
    assert controller.index == 1 and not controller.overlay.next_button.isEnabled()
    controller.back()
    completed.add("expected")
    emitter.done.emit("expected", "completed")
    app.processEvents()
    assert controller.index == 0
    controller.next()
    assert controller.index == 2
    controller.back()
    assert controller.index == 1 and controller.overlay.next_button.isEnabled()


def test_dynamic_instructions_refresh_without_reflowing_unchanged_text(ui):
    app, window, button, other, controller = ui
    instructions = ["Wait for the operation."]
    controller.instruction_provider = lambda step: instructions[0]
    controller.start(tour())
    assert controller.overlay.body.toPlainText() == instructions[0]
    instructions[0] = "The operation is ready. " * 100
    controller.refresh()
    assert controller.overlay.body.toPlainText() == instructions[0]
    assert instructions[0] in controller.overlay.accessibleDescription()
    controller.overlay.body.verticalScrollBar().setValue(20)
    controller.refresh()
    assert controller.overlay.body.verticalScrollBar().value() == 20


def test_outline_only_presentation_preserves_the_background(ui):
    app, window, button, other, controller = ui
    before = window.grab().toImage()
    controller.dim_background = False
    controller.start(tour(interactive=True))
    overlay = controller.overlay
    sample = next(QPoint(x, y) for x in range(10, window.width(), 20)
                  for y in range(10, window.height(), 20)
                  if not overlay.panel.geometry().contains(x, y)
                  and not overlay.hole.adjusted(-5, -5, 5, 5).contains(x, y))
    after = window.grab().toImage()
    assert after.pixelColor(sample) == before.pixelColor(sample)
    assert overlay.hole.size() == button.size()
    assert QApplication.widgetAt(button.mapToGlobal(button.rect().center())) is button


def test_guide_outline_changes_with_theme_and_keeps_target_clickable(ui):
    app, window, button, other, controller = ui
    controller.dim_background = False
    controller.start(tour(interactive=True))
    for theme, expected in (("github_light", "#8c4b00"), ("github_dark", "#ffd166")):
        apply_theme(theme, app)
        app.processEvents()
        image = window.grab().toImage()
        rect = controller.overlay.hole.adjusted(-9, -9, 9, 9).intersected(window.rect())
        colors = {image.pixelColor(x, y).name()
                  for x in range(rect.left(), rect.right() + 1)
                  for y in range(rect.top(), rect.bottom() + 1)}
        assert expected in colors
        assert QApplication.widgetAt(button.mapToGlobal(button.rect().center())) is button


def test_accepting_a_dialog_keeps_the_tutorial_active_but_closing_cancels(ui):
    app, window, button, other, controller = ui
    dialog = QDialog(window)
    action = QPushButton("Save", dialog)
    dialog.show()
    app.processEvents()
    controller.targets["dialog"] = TutorialTarget(lambda: action if dialog.isVisible() else button)
    controller.start(Tutorial("dialog", "Dialog", (
        TutorialStep("save", "dialog", "Save", "Save the form."),
    )))
    dialog.accept()
    app.processEvents()
    assert controller.is_active and controller.overlay.parentWidget() is window
    dialog.show()
    controller.refresh()
    dialog.close()
    assert not controller.is_active


def test_job_predicate_runs_in_ui_thread_and_ignores_stale_duplicate_events(ui):
    app, window, button, other, controller = ui
    emitter = Emitter()
    seen = []

    def accept(job_id, status):
        seen.append(QThread.currentThread() == QApplication.instance().thread())
        return job_id == "expected" and status == "completed"

    controller.events["job.done"] = TutorialEvent(emitter.done, accept)
    definition = Tutorial("jobs", "Jobs", (
        TutorialStep("first", "run", "Run", "Wait.", "job.done"),
        TutorialStep("second", "other", "Run again", "Wait again.", "job.done"),
    ))
    controller.start(definition)
    emitter.done.emit("another", "completed")
    emitter.done.emit("expected", "failed")
    app.processEvents()
    assert controller.index == 0
    worker = Thread(target=lambda: (emitter.done.emit("expected", "completed"),
                                    emitter.done.emit("expected", "completed")))
    worker.start()
    worker.join()
    for _ in range(3):
        app.processEvents()
    assert controller.index == 1 and controller.is_active
    assert seen and all(seen)
    emitter.done.emit("expected", "completed")
    app.processEvents()
    assert not controller.is_active


def test_cancel_before_delivery_cannot_advance_a_restarted_tour(ui):
    app, window, button, other, controller = ui
    definition = tour(interactive=True)
    controller.start(definition)
    button.click()
    controller.stop()
    controller.start(definition)
    app.processEvents()
    assert controller.index == 0
    button.click()
    app.processEvents()
    assert controller.index == 1


def test_dynamic_target_and_modal_dialog_use_their_own_host(ui):
    app, window, button, other, controller = ui
    dialog = QDialog(window)
    dialog.setModal(True)
    dialog.resize(540, 420)
    content = QVBoxLayout(dialog)
    label = QLabel("Details")
    content.addWidget(label, alignment=Qt.AlignmentFlag.AlignTop)
    controller.targets["run"] = TutorialTarget(button, prepare=dialog.hide)
    controller.targets["dialog"] = TutorialTarget(lambda: label, prepare=dialog.show)
    definition = Tutorial("windows", "Windows", (
        TutorialStep("main", "run", "Main", "Main window."),
        TutorialStep("dialog", "dialog", "Dialog", "Dialog content."),
    ))
    controller.start(definition)
    original_overlay = controller.overlay
    controller.next()
    app.processEvents()
    assert controller.overlay is not original_overlay
    assert controller.overlay.parentWidget() is dialog
    assert controller.overlay.isVisible()
    controller.back()
    assert controller.overlay.parentWidget() is window and not dialog.isVisible()
    controller.next()
    assert controller.overlay.parentWidget() is dialog and dialog.isVisible()
    QTest.keyClick(controller.overlay.next_button, Qt.Key.Key_Escape)
    assert not controller.is_active
    dialog.close()


def test_resize_and_long_text_keep_callout_visible_and_scrollable(ui):
    app, window, button, other, controller = ui
    definition = Tutorial("long", "Long tutorial", (
        TutorialStep("long", "run", "A title", "A long explanation. " * 300),
    ))
    controller.start(definition)
    window.resize(480, 400)
    app.processEvents()
    controller.refresh()
    overlay = controller.overlay
    assert overlay.rect().contains(overlay.panel.geometry())
    assert not overlay.panel.geometry().intersects(overlay.hole)
    assert overlay.body.verticalScrollBar().maximum() > 0
    overlay.body.verticalScrollBar().setValue(20)
    controller.refresh()
    assert overlay.body.verticalScrollBar().value() == 20
    assert overlay.hole.contains(overlay.mapFromGlobal(button.mapToGlobal(QPoint(2, 2))))


def test_menu_target_region_follows_the_action_geometry(ui):
    app, window, button, other, controller = ui
    bar = QMenuBar(window)
    file_menu = bar.addMenu("File")
    help_menu = bar.addMenu("Help")
    bar.setGeometry(20, 100, 600, 28)
    bar.show()
    app.processEvents()
    controller.targets["help"] = TutorialTarget(
        bar, rect=lambda: bar.actionGeometry(help_menu.menuAction())
    )
    controller.start(Tutorial("help", "Help", (TutorialStep("help", "help", "Help", "Documentation"),)))

    def expected_region():
        rect = bar.actionGeometry(help_menu.menuAction())
        rect.moveTopLeft(controller.overlay.mapFromGlobal(bar.mapToGlobal(rect.topLeft())))
        return rect

    assert controller.overlay.hole == expected_region()
    previous = controller.overlay.hole
    file_menu.menuAction().setText("Projects and input files")
    app.processEvents()
    controller.refresh()
    assert controller.overlay.hole == expected_region()
    assert controller.overlay.hole.left() > previous.left()


@pytest.mark.parametrize("repetitions", [1, 20])
def test_tracking_does_not_reflow_text_or_move_scrollbar_while_reading(ui, repetitions):
    app, window, button, other, controller = ui
    text = ("Open or create a project to enable the catalogs and tools. A typical workflow is: "
            "import a receptor and ligands, check the input, define a binding site, configure docking, "
            "then inspect the results. This tour does not require a project or sample data.")
    controller.start(Tutorial("reading", "Reading", (
        TutorialStep("workspace", "run", "Your workspace", text * repetitions),
    )))
    QTest.qWait(160)
    overlay = controller.overlay
    scrollbar = overlay.body.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum() // 2)
    before = (scrollbar.value(), scrollbar.maximum(), overlay.panel.geometry(),
              overlay.body.document().textWidth())
    ranges = []
    scrollbar.rangeChanged.connect(lambda low, high: ranges.append((low, high)))
    QTest.qWait(400)  # Several real tracker ticks, with the Qt event loop running.
    assert ranges == []
    assert (scrollbar.value(), scrollbar.maximum(), overlay.panel.geometry(),
            overlay.body.document().textWidth()) == before


def test_bad_bindings_do_not_cancel_the_existing_tour(ui):
    app, window, button, other, controller = ui
    controller.start(tour())
    with pytest.raises(ValueError, match="target"):
        controller.start(Tutorial("bad", "Bad", (TutorialStep("x", "missing", "X", "Text"),)))
    assert controller.is_active and controller.current_step.id == "input"
    controller.events.clear()
    with pytest.raises(ValueError, match="event"):
        controller.start(tour(interactive=True))


def test_deleted_target_and_prepare_errors_fail_with_cleanup(ui):
    app, window, button, other, controller = ui
    failures = []
    controller.failed.connect(lambda tutorial_id, message: failures.append(message))
    controller.start(tour())
    button.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    controller.refresh()
    assert failures and "unavailable" in failures[-1]
    assert not controller.is_active and controller.overlay is None

    def fail():
        raise RuntimeError("Cannot open panel")

    controller.targets["run"] = TutorialTarget(other, prepare=fail)
    controller.start(tour())
    assert "Cannot open panel" in failures[-1] and not controller.is_active


def test_closing_host_cancels_tutorial(ui):
    app, window, button, other, controller = ui
    controller.start(tour())
    window.close()
    assert not controller.is_active


def test_signal_resolver_rebinds_after_its_sender_is_recreated(ui):
    app, window, button, other, controller = ui
    emitter = Emitter()
    controller.events["clicked"] = TutorialEvent(lambda: emitter.done)
    controller.start(tour(interactive=True))
    emitter.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    controller.stop()  # A deleted sender must not prevent cleanup.
    emitter = Emitter()
    controller.start(tour(interactive=True))
    emitter.done.emit("new-sender", "completed")
    app.processEvents()
    assert controller.index == 1


def test_deleting_controller_removes_overlay_from_a_different_host(ui):
    app, window, button, other, controller = ui
    dialog = QDialog(window)
    dialog.resize(540, 420)
    label = QLabel("Another host", dialog)
    label.move(20, 20)
    dialog.show()
    observer = TutorialController(targets={**controller.targets, "run": TutorialTarget(label)}, parent=window)
    observer.start(tour())
    overlay = observer.overlay
    observer.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert not isValid(overlay) or not overlay.isVisible()
    dialog.close()


def test_toml_and_python_have_the_same_content(tmp_path):
    path = tmp_path / "tutorial.toml"
    path.write_text('''id = "demo"
title = "Demo"
[[steps]]
id = "input"
target = "run"
title = "Input"
text = "Load the input."
advance_on = "clicked"
[[steps]]
id = "output"
target = "other"
title = "Output"
text = "Review the output."
''')
    assert load_tutorial(path) == tour(interactive=True)


@pytest.mark.parametrize("content", [
    'id="x"\ntitle="X"',
    'id="x"\ntitle="X"\nsteps=[]',
    'id="x"\ntitle="X"\ncode="eval()"\nsteps=[]',
    'id="x"\ntitle="X"\n[[steps]]\nid="a"\ntarget="a"\ntitle="A"\ntext=42',
    'id="x"\ntitle="X"\n[[steps]]\nid="a"\ntarget="a"\ntitle="A"\ntext="x"\nwait=true',
    'id="x"\ntitle="X"\n[[steps]]\nid="a"\ntarget="a"\ntitle="A"\ntext="x"\nadvance_on=""',
])
def test_invalid_toml_is_rejected(tmp_path, content):
    path = tmp_path / "bad.toml"
    path.write_text(content)
    with pytest.raises(ValueError):
        load_tutorial(path)


def test_duplicate_step_ids_are_rejected():
    step = TutorialStep("duplicate", "run", "Run", "Text")
    with pytest.raises(ValueError, match="unique"):
        Tutorial("duplicate", "Duplicate", (step, step))


def test_a_later_step_on_a_hidden_target_fails_instead_of_running_unseen(ui):
    app, _window, _button, other, controller = ui
    failures = []
    controller.failed.connect(lambda _tid, message: failures.append(message))
    other.hide()
    controller.start(tour())
    controller.next()
    app.processEvents()
    assert not controller.is_active and "hidden" in failures[0]


def test_a_still_tour_does_not_repaint_on_every_tracker_tick(ui):
    app, _window, _button, _other, controller = ui
    controller.start(tour())
    QTest.qWait(200)
    paints = []

    class Counter(QObject):
        def eventFilter(self, _obj, event):
            if event.type() == QEvent.Type.Paint:
                paints.append(1)
            return False

    counter = Counter()
    controller.overlay.installEventFilter(counter)
    QTest.qWait(800)  # ten tracker ticks
    controller.overlay.removeEventFilter(counter)
    assert len(paints) <= 1


def test_close_only_mode_has_accessible_close_control_and_escape(ui):
    app, _window, button, _other, controller = ui
    controller.close_only = True
    tutorial = Tutorial("interactive", "Interactive", (
        TutorialStep("action", "run", "Action", "Click the action.", "clicked"),
    ))
    controller.start(tutorial)
    overlay = controller.overlay
    assert overlay.exit_button.text() == "×"
    assert overlay.exit_button.accessibleName() == "Close tutorial"
    assert overlay.exit_button.isVisible()
    assert not overlay.back_button.isVisible() and not overlay.next_button.isVisible()
    assert overlay.exit_button.geometry().right() > overlay.counter.geometry().right()
    assert overlay.panel.rect().contains(overlay.exit_button.geometry())
    QTest.mouseClick(overlay.exit_button, Qt.LeftButton)
    assert not controller.is_active
    controller.start(tutorial)
    QTest.keyClick(controller.overlay.exit_button, Qt.Key_Escape)
    assert not controller.is_active


def test_close_only_rejects_steps_that_need_next_button(ui):
    _app, _window, _button, _other, controller = ui
    controller.close_only = True
    with pytest.raises(ValueError, match="require an event"):
        controller.start(tour())
    assert not controller.is_active


def test_close_only_follows_target_into_another_window(ui):
    app, window, button, _other, controller = ui
    dialog = QDialog(window)
    action = QPushButton("Finish", dialog)
    button.clicked.connect(dialog.show)
    controller.targets["dialog"] = TutorialTarget(action)
    controller.events["finish"] = TutorialEvent(action.clicked)
    controller.close_only = True
    controller.start(Tutorial("dialog", "Dialog", (
        TutorialStep("open", "run", "Open", "Open dialog.", "clicked"),
        TutorialStep("finish", "dialog", "Finish", "Finish the task.", "finish"),
    )))
    QTest.mouseClick(button, Qt.LeftButton)
    app.processEvents()
    overlay = controller.overlay
    assert overlay.parentWidget() is dialog
    assert overlay.exit_button.isVisible() and overlay.exit_button.text() == "×"
    assert overlay.panel.rect().contains(overlay.exit_button.geometry())
    QTest.mouseClick(overlay.exit_button, Qt.LeftButton)
    assert not controller.is_active
    dialog.close()
