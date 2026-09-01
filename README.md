# ms_components

PySide6 UI components for MolSuite: smart table, project browser, job monitor,
PyMOL dock, steppers and the shared theming (`themes/` + `base.qss`).

Part of the [MolSuite](https://molsuite.github.io/) stack. Built on top of
[`ms_flow`](https://github.com/MolSuite/ms_flow).

## Install

```bash
pip install git+https://github.com/MolSuite/ms_flow
pip install git+https://github.com/MolSuite/ms_components
```

Optional PyMOL dock widget (heavy, imports degrade gracefully without it):

```bash
conda install -c conda-forge pymol-open-source
```

## License

MIT — see [LICENSE](LICENSE). Third-party icon/asset licenses live in `licenses/`.
