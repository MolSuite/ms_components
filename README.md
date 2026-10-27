# ms_components

PySide6 UI components for MolSuite: smart table, project browser, job monitor,
PyMOL dock, steppers and the shared theming (`themes/` + `base.qss`).

[`ms_tutorial`](docs/ms_tutorial.md) provides informative and interactive tours:
Python binds existing widgets/signals, while content can be defined in Python or
TOML. Try `PYTHONPATH=src python examples/tutorial_demo.py` from a source checkout.

Part of the [MolSuite](https://molsuite.github.io/) stack. The project catalog integrates
with [`ms_flow`](https://github.com/MolSuite/ms_flow) when that backend is needed.

## Install

The base installation provides Qt widgets and themes:

```bash
pip install ms_components
```

Choose the integrations your application uses, or install all of them:

```bash
pip install "ms_components[table,pymol]"
pip install "ms_components[all]"
```

| Extra | Dependency / use |
| --- | --- |
| `table` | SQLModel tables |
| `monitor` | Pydantic monitor configuration |
| `projects` | `ms_flow` project catalog and standalone project browser |
| `pymol` | `pymol-open-source` alpha wheels (`>=3.2.0a0`) |
| `steps` | `ms_env` provisioning steps |
| `dev` | All integrations and pytest |

Extras select dependencies; all component source files remain in the package.
Project widgets accept a supplied backend without importing `ms_flow`. When no backend is
supplied, they use the optional MolSuite catalog, which creates its database on first use.
Run the standalone browser with `python -m ms_components.ms_projects.app` after installing
`ms_components[projects]`.

## Documentation

<https://molsuite.github.io/ms_components/>: a guide to each component, examples,
and the API reference.

## License

MIT — see [LICENSE](LICENSE). Third-party icon/asset licenses live in `licenses/`.
