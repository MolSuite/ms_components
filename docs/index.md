# ms_components

`ms_components` is a set of reusable PySide6 widgets for MolSuite applications:
SQLModel tables, a job monitor, a project browser, settings panels, a PyMOL
dock, steppers, tool panels, and the shared theme.

## Install

`ms_components` requires Python 3.12. PyMOL comes from the
`pymol-open-source` alpha wheels on PyPI and is installed automatically as a
dependency, together with `ms_flow`; no conda environment is needed:

```bash
pip install ms_components
```

## Components

| Module | Responsibility |
| --- | --- |
| `ms_components.ms_table` | Declarative, paginated table over SQLModel |
| `ms_components.ms_monitor` | Job, executor, and event monitor for a MolSuite runtime |
| `ms_components.ms_projects` | Project browser and project menu |
| `ms_components.ms_settings` | Typed editor for application settings |
| `ms_components.ms_pymol` | PyMOL dock and control bar |
| `ms_components.ms_stepper` | Step-by-step wizard widget |
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
