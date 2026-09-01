# ms_components

PySide6 UI components for MolSuite: smart table, project browser, job monitor,
PyMOL dock, steppers and the shared theming (`themes/` + `base.qss`).

Part of the [MolSuite](https://molsuite.github.io/) stack. Built on top of
[`ms_flow`](https://github.com/MolSuite/ms_flow).

## Install

PyMOL is required and must be installed from conda-forge before the Python
packages (it is not distributed on PyPI):

```bash
conda install -c conda-forge pymol-open-source
pip install git+https://github.com/MolSuite/ms_flow
pip install git+https://github.com/MolSuite/ms_components
```

## License

MIT — see [LICENSE](LICENSE). Third-party icon/asset licenses live in `licenses/`.
