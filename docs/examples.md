# Examples

## Tool panel with a simulated run

A themed tool panel whose action bar reports the progress of a fake run driven
by a timer. In an application, the same calls are driven by job events.

```python
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QSpinBox

from ms_components.theme import apply_theme
from ms_components.tool_panel import ToolPanel

app = QApplication([])
apply_theme("auto", app)

panel = ToolPanel()
options = panel.add_section("Options")
engine = QComboBox()
engine.addItems(["vina", "vinardo"])
options.add_row("Scoring function", engine)
options.add_row("Exhaustiveness", QSpinBox(value=8))
panel.advanced.add_row("Seed", QSpinBox())

total = 50
state = {"done": 0}
bar = panel.action_bar
bar.set_summary(f"{total} ligands selected")
run_button = QPushButton("Run")
bar.add_action(run_button)

timer = QTimer(interval=50)


def tick():
    state["done"] += 1
    bar.set_progress(state["done"], total, unit="ligands")
    if state["done"] == total:
        timer.stop()
        bar.finish("Done", f"{total} ligands docked")


def start():
    state["done"] = 0
    bar.start("Docking…")
    timer.start()


timer.timeout.connect(tick)
run_button.clicked.connect(start)

panel.resize(420, 360)
panel.show()
app.exec()
```

## Three-step wizard

```python
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit

from ms_components.ms_stepper import QStepper
from ms_components.theme import apply_theme

app = QApplication([])
apply_theme("auto", app)

stepper = QStepper()

name_step = stepper.add_step("Project", "Name the project")
name = QLineEdit()
name_step.add_widget(name)

files_step = stepper.add_step("Input", "Choose the files")
files_step.add_widget(QLabel("Ligands: ligands.sdf\nReceptor: receptor.pdb"))

review_step = stepper.add_step("Review", "Check and finish")
review_step.add_widget(QLabel("Press Finish to create the project."))

stepper.finished.connect(lambda: print("create project", name.text()))
stepper.finished.connect(app.quit)

stepper.resize(640, 320)
stepper.show()
app.exec()
```

## Job monitor for a running job

Attach the monitor to a `MolSuite` runtime and watch a job advance. The worker
must live in an importable module:

```python
# workers.py
import time


def slow_square(payload: dict) -> dict:
    time.sleep(0.1)
    value = int(payload["value"])
    return {"value": value, "square": value * value}
```

```python
from PySide6.QtWidgets import QApplication

from ms_components.ms_monitor import MolSuiteMonitorBridge, MolSuiteMonitorWidget
from ms_components.theme import apply_theme
from ms_flow.api import MolSuite
from workers import slow_square

app = QApplication([])
apply_theme("auto", app)

ms = MolSuite(app_id="monitor-demo")
ms.create_or_open_project(name="monitor-demo", folder="./monitor-demo", activate=True)

bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=500)
monitor = MolSuiteMonitorWidget(bridge=bridge)
bridge.start()
app.aboutToQuit.connect(bridge.stop)   # stop polling before the runtime shuts down

ms.run(
    name="slow-squares",
    input=[{"value": value} for value in range(100)],
    process=slow_square,
    executor="thread",
)

monitor.resize(1100, 650)
monitor.show()
try:
    app.exec()
finally:
    ms.shutdown()
```
