# API guide

Every component is a plain PySide6 widget. Create a `QApplication` first, pass
dependencies through the constructor, and apply the theme once.

## Theme

`apply_theme()` sets the palette and the base stylesheet for the whole
application, and re-applies them live to existing widgets.

```python
from PySide6.QtWidgets import QApplication

from ms_components.theme import THEMES, apply_theme, color, font, set_base_font

app = QApplication([])
set_base_font(10.0, app=app)
apply_theme("auto", app)     # or a name from THEMES, e.g. "nord"

print(sorted(THEMES))
warning = color("orange")    # semantic accent from the live theme
title_font = font("title")
```

Widgets should read colours from the palette (`palette(window)`,
`palette(highlight)`, …) instead of hard-coded hex values, so they follow theme
changes. Non-Qt views such as PyMOL or pyqtgraph do not observe the palette and
must be updated separately.

## SmartTableView

Define a SQLModel model, describe the columns, and provide a session provider.
The table handles querying, filtering, sorting, and pagination.

```python
from PySide6.QtWidgets import QApplication
from sqlmodel import Field, Session, SQLModel, create_engine

from ms_components.ms_table import ColumnDef, SmartTableView, TableConfig


class Molecule(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    score: float | None = None


class Database:
    def __init__(self, engine):
        self.engine = engine

    def get_session(self) -> Session:
        return Session(self.engine)


app = QApplication([])
engine = create_engine("sqlite:///molecules.db")
SQLModel.metadata.create_all(engine)

table = SmartTableView(
    db=Database(engine),
    config=TableConfig(
        model_class=Molecule,
        columns=[
            ColumnDef("id", label="ID", width=70),
            ColumnDef("name", label="Molecule", filterable=True),
            ColumnDef("score", label="Score", sortable=True),
        ],
        page_size=50,
    ),
)
table.row_double_clicked.connect(lambda molecule: print(molecule.id))
table.resize(800, 500)
table.show()
app.exec()
```

Call `refresh()` or `refresh_preserving_view()` after external data changes.
Filters imposed by the application go through `set_external_filters()` or
`set_external_clause()`, which keeps them apart from the filters the user edits.

## ToolPanel

`ToolPanel` is the frame shared by configure-then-run tools: an optional top
bar, a scrolling body of sections, and an action bar. It knows nothing about
jobs; the host maps its job events onto the action bar.

```python
from PySide6.QtWidgets import QPushButton, QSpinBox

from ms_components.tool_panel import ToolPanel

panel = ToolPanel()

options = panel.add_section("Options", description="Docking parameters")
options.add_row("Exhaustiveness", QSpinBox())

panel.advanced.add_row("Seed", QSpinBox())   # collapsed section kept last

bar = panel.action_bar
bar.add_action(QPushButton("Run"))
bar.set_summary("120 ligands selected")

bar.start("Docking…")
bar.set_progress(40, 120, unit="ligands")
bar.finish("Done", "120 ligands docked")
```

`ToolSection.add_row()` accepts the `QFormLayout.addRow` overloads:
`(label, field)`, a single spanning widget, or a layout.

## QStepper

`QStepper` shows a sequence of steps. `add_step()` returns a `QStep`, which is
a widget you fill with content.

```python
from PySide6.QtWidgets import QLabel

from ms_components.ms_stepper import QStepper

stepper = QStepper()
first = stepper.add_step("Input", "Choose the files")
first.add_widget(QLabel("Select ligands and receptors."))
second = stepper.add_step("Run", "Start the job")
second.add_widget(QLabel("Review and run."))

stepper.current_changed.connect(lambda index: print("step", index))
stepper.finished.connect(lambda: print("finished"))
```

Pass a `validator` to `QStep` to block advancing until its content is valid.
Inside a stepper, put one `ToolPanel` per step so each step keeps its own
action bar state.

## Job monitor

The bridge polls a `MolSuite` runtime and translates its snapshots into Qt
signals and models; the widget only presents them. You can embed the whole
monitor or consume only the bridge signals.

```python
from ms_flow.api import MolSuite
from ms_components.ms_monitor import MolSuiteMonitorBridge, MolSuiteMonitorWidget

ms = MolSuite(app_id="demo")
ms.create_or_open_project(name="demo", folder="./demo-project", activate=True)

bridge = MolSuiteMonitorBridge(molsuite=ms, poll_ms=500)
monitor = MolSuiteMonitorWidget(bridge=bridge)
bridge.bridge_error.connect(print)
bridge.job_finished.connect(lambda *args: print("job finished", args))
bridge.start()
monitor.show()
```

When closing, call `bridge.stop()` first and `ms.shutdown()` afterwards. The
supported operator actions are refresh, cancel, and — when the job keeps a
re-buildable source — resubmit.

## Projects, settings, and PyMOL

- `ProjectsMenuWidget(app_id=...)` and `ProjectBrowserWindow(app_id=...)` list
  and create projects through the public `ms_flow` project catalog. Connect
  `project_requested` to open the chosen project; do not read the MolSuite
  databases from the UI.
- `AppSettingsDialog(runtime=...)` edits the layered configuration of a
  MolSuite runtime.
- `PymolDockWidget(title, manager)` needs the PyMOL `cmd`/manager object of the
  application's PyMOL integration.
