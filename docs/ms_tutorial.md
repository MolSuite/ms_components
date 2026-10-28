# Guided tutorials

`ms_components.ms_tutorial` supplies informative and interactive tours for any
Qt Widgets application. It imports no application, project catalog, or orchestrator.
No existing application slot needs a tutorial call.

## Python bindings, optional TOML content

Use **Python for widget/signal bindings**. They are live Qt objects and may need
application logic to reveal a panel or verify a result. Use either **Python or
TOML for tutorial content**. Both produce the same `Tutorial` model.

TOML is useful when editing explanations or translating a tour without touching
bindings. It uses Python 3.12's standard-library `tomllib`, so no YAML dependency
is needed. Files contain symbolic IDs, never Python expressions, imports, widget
attribute paths, or executable callbacks. Unknown keys and invalid definitions
raise `ValueError`; TOML syntax and filesystem errors propagate to the caller.

```toml
id = "first-import"
title = "Import your data"

[[steps]]
id = "overview"
target = "input.panel"
title = "Input panel"
text = "Configure your input here, then review the resulting records."

[[steps]]
id = "import"
target = "input.run"
title = "Import the example"
text = "Run the import. This step advances only after the expected job succeeds."
advance_on = "input.imported"
```

```python
from ms_components.ms_tutorial import (
    TutorialController, TutorialEvent, TutorialTarget, load_tutorial,
)

window.tutorials = TutorialController(
    targets={
        "input.panel": TutorialTarget(lambda: window.input_panel,
                                      prepare=window.show_input_panel),
        "input.run": TutorialTarget(lambda: window.input_panel.run_button),
    },
    events={
        "input.imported": TutorialEvent(
            window.monitor_bridge.job_finished,
            accept=lambda job_id, status: job_id == expected_job_id() and status == "completed",
        ),
    },
    parent=window,
)
window.tutorials.start(load_tutorial("first_import.toml"))
```

Names such as `input.panel` are plain dictionary keys. The application supplies
their meaning; `ms_tutorial` knows nothing about AMDockVS or Molsuite's job statuses.
The example's `expected_job_id()` and `show_input_panel` are application-provided
functions, not methods required by this component. Real operations still go
through the application's existing APIs.

For a small tour, define the content in Python instead:

```python
from ms_components.ms_tutorial import Tutorial, TutorialStep

overview = Tutorial("overview", "Interface overview", (
    TutorialStep("input", "input.panel", "Input", "Configure your data here."),
    TutorialStep("run", "input.run", "Run", "This submits the configured operation."),
))
window.tutorials.start(overview)
```

## Informative and interactive steps

- Without `advance_on`, a step is **informative**: Next/Back control the tour.
  The spotlight remains visible but blocks clicks and keyboard actions on the host
  window. The component never clicks controls or executes application actions.
- With `advance_on`, a step is **interactive**: the spotlight admits real input to
  its target, and Next stays disabled until the named event is accepted. Completion
  advances automatically. Other application slots retain their existing connections.
- `TutorialEvent.accept` receives the signal's arguments. Use it to match the job,
  project, selection, or success state that the step actually expects. A request or
  button click does not in general prove that an asynchronous operation succeeded.
- Events are observed only while their step is active. Already completed steps may
  be revisited with Back and left with Next. A new run resets tutorial completion,
  without resetting application data. Multiple queued copies of an old event do
  not complete a later step, even if both steps use the same signal.

For asynchronous operations that may finish while the user has gone Back, supply
`TutorialEvent(signal, accept=..., is_complete=lambda: cached_result_is_ready)`.
The controller checks `is_complete` when entering an unfinished step and advances
if it returns true. The application records successful completion before emitting
its signal; the callback reads that state, without blocking or querying a database.
`accept` validates incoming signal arguments; `is_complete` independently checks
the operation and result that the step requires.

`TutorialEvent.signal` also accepts a zero-argument resolver for signals belonging
to dialogs or controls that are recreated. It is resolved when entering the step.

The controller queues event validation to the UI thread, including signals emitted
by background workers. Validators must be fast and must not mutate the UI or start
another tutorial. Signal argument types must be supported by Qt's queued connections
(Python objects and the ordinary Qt types are suitable).

## Dynamic panels and multiple windows

`TutorialTarget.widget` is a `QWidget` or a zero-argument resolver returning one.
Optional `TutorialTarget.rect` resolves a rectangle in that widget's coordinates,
for example `rect=lambda: menu_bar.actionGeometry(help_action)` to highlight just
the Help menu item. It is recomputed as the layout changes; the widget is unchanged.
The controller resolves it again as the UI changes. `prepare`, when provided,
runs once on entering the step and should only reveal the needed UI, through its
existing public navigation API. Do not submit jobs or change scientific data there.
Navigation callbacks must also account for Back, for example hiding a modal dialog
when returning to its parent window; the controller does not close application dialogs.

An overlay belongs to the target's top-level window. On the next step the controller
can move to another window, a floating dock, or a modal dialog, without application
slots knowing about it. It follows resizing, moving, and ancestor viewport clipping.
Use `prepare` to scroll offscreen controls into view; the component does not scroll
the application automatically. Hidden targets temporarily hide the overlay; an
initial hidden target without an existing overlay fails with a diagnostic. Missing
or deleted targets and callback failures stop the tour and emit `failed`.

Call the public `controller.refresh()` after an application UI change when the
spotlight should update immediately. Normal tracking continues automatically.
Accepting a host `QDialog` preserves the tutorial so its target can move back to
the parent window; closing or rejecting the host still cancels the tutorial.

For tutorials where every step advances through an application event,
`TutorialController(close_only=True)` replaces the Back, Next and Exit buttons
with a compact close button in the callout header. Escape still cancels. Every
step must provide `advance_on`; starting a close-only tutorial with an
informational step raises `ValueError`, since there would be no way to advance.
The default controls remain available for informative tours.
Set `click_only_close=True` to keep the close control out of keyboard focus,
disable its keyboard activation, and prevent Escape from cancelling the tutorial.
Closing or rejecting a host dialog still cancels as described above.
Set `block_tab=True` to suppress Tab and Shift+Tab throughout the active tour,
including in dialogs. The default is false, and normal behavior returns when the
tour ends.

`TutorialController(dim_background=False)` preserves the application's background
colors and draws only the target outline. Input gating remains the same.
`instruction_provider=lambda step: current_instruction` supplies dynamic plain-text
instructions. They are measured again only when their text changes, without
resetting the reader's scroll position on every tracking tick. These options do not
depend on any application or project package.

Lifecycle signals:

| Signal | Arguments |
| --- | --- |
| `started` | tutorial ID |
| `step_changed` | step ID, zero-based index |
| `finished` | tutorial ID |
| `cancelled` | tutorial ID |
| `failed` | tutorial ID, diagnostic message |

Call `start(tutorial)`, `next()`, `back()`, or `stop()` on the UI thread. Keep the
controller alive, normally as an attribute of the main window, and give it a Qt
parent. Escape/Exit cancel by default; closing the current host also cancels. Stopping a tour
removes its signal connection and event filter and restores the earlier focus
when that widget is still visible. Switching tutorials cancels the previous one.
Invalid target/event registry keys are rejected before cancelling an active tour.
The component never creates `QApplication` or changes the application's theme.

## Demo and checks

From the source checkout, in `MSDD_312`:

```bash
PYTHONPATH=src python examples/tutorial_demo.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q tests/test_tutorial.py
```

The demo has two buttons: an informative tour defined in Python, and a mixed
interactive/informative tour loaded from `examples/tutorial_demo.toml`. Its
application slot has no tutorial calls. Add the sibling `ms_flow/src` and
`ms_env/src` to `PYTHONPATH` if those packages are not installed in the environment.

## Scope

This component guides an existing UI within one process. Continuing in a new process,
saving progress, translation catalogs, and the application's Help menu remain the
application's responsibility. A spotlight over native platform dialogs or embedded
OpenGL renderers is platform-dependent; use a Qt Widgets practice view if needed.
On a host almost entirely occupied by the target, the callout may overlap part of
the spotlight. Expose a smaller target in the binding to leave room for the callout.
