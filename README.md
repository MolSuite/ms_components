# ms_components

PySide6 UI components for MolSuite: smart table, project browser, job monitor,
PyMOL dock, steppers and the shared theming (`themes/` + `base.qss`).

[`ms_tutorial`](docs/ms_tutorial.md) provides informative and interactive tours:
Python binds existing widgets/signals, while content can be defined in Python or
TOML. Try `PYTHONPATH=src python examples/tutorial_demo.py` from a source checkout.

Part of the [MolSuite](https://molsuite.github.io/) stack. Built on top of
[`ms_flow`](https://github.com/MolSuite/ms_flow).

## Install

PyMOL is installed automatically from the `pymol-open-source` alpha wheels on
PyPI (`>=3.2.0a0`):

```bash
pip install ms_components
```

## Documentation

<https://molsuite.github.io/ms_components/>: a guide to each component, examples,
and the API reference.

## License

MIT — see [LICENSE](LICENSE). Third-party icon/asset licenses live in `licenses/`.
