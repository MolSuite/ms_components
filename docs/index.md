# ms_components

`ms_components` is a set of reusable PySide6 widgets for MolSuite applications:
SQLModel tables, a job monitor, a project browser, settings panels, a PyMOL
dock, steppers, tool panels, and the shared theme.

## Install

`ms_components` requires Python 3.12. The base installation requires Qt;
integrations are selected with extras:

```bash
pip install ms_components
pip install "ms_components[table,pymol]"
pip install "ms_components[all]"
```

The extras are `table` (SQLModel), `monitor` (Pydantic), `projects` (`ms_flow`),
`pymol` (`pymol-open-source` alpha wheels), and `steps` (`ms_env`). `dev` adds
all integrations and pytest. Extras change which dependencies are installed,
not which component files are shipped.

Project widgets can use a supplied backend without `ms_flow`. The default catalog
and `python -m ms_components.ms_projects.app` require the `projects` extra.
The catalog creates its database on first use; a missing backend is reported with
the installation command.

## Components

| Module | Responsibility |
| --- | --- |
| `ms_components.ms_table` | Declarative, paginated table over SQLModel |
| `ms_components.ms_monitor` | Job monitor for an `ms_flow` workspace: cancel, resume, move |
| `ms_components.ms_executors` | Hosts and executors: Settings pages and the panel that starts them |
| [`ms_components.ms_projects`](project_form_events.md) | Project browser, project menu, and form lifecycle events |
| `ms_components.ms_settings` | Typed editor for application settings |
| `ms_components.ms_pymol` | PyMOL dock and control bar |
| `ms_components.ketcher` | Ketcher molecule editor dialog |
| `ms_components.ms_stepper` | Step-by-step wizard widget |
| [`ms_components.ms_tutorial`](ms_tutorial.md) | Informative and interactive tours, with Python bindings and optional TOML content |
| `ms_components.tool_panel` | Configure-then-run frame shared by tools |
| `ms_components.step_dialog` | Dialog that runs provisioning steps off the GUI thread |
| `ms_components.theme` | Themes, palette roles, and fonts |

Every component receives its dependencies through the constructor. The package
keeps no UI singleton and never creates a Qt application implicitly.

## Quick look

```python
from PySide6.QtWidgets import QApplication, QLineEdit

from ms_components.theme import apply_theme
from ms_components.tool_panel import ToolPanel

app = QApplication([])
apply_theme("auto", app)

panel = ToolPanel()
section = panel.add_section("Input")
section.add_row("Name", QLineEdit())
panel.show()
app.exec()
```

Continue with the [API guide](usage.md), copy a complete
[example](examples.md), or browse the generated [API reference](api_reference.md).

## License

`ms_components` is released under the MIT License. Icon and asset licenses are
listed in the `licenses/` directory of the repository.
