"""The monitor of MolSuite jobs. Its names are loaded when first asked for: `config` is read
by processes that never open a window, and they must not pay for Qt."""
from importlib import import_module

_LAZY = {
    "FailureState": "models",
    "JobDetailPanel": "detail_panel",
    "JobDetailState": "models",
    "JobMonitorState": "models",
    "MonitorConfig": "config",
    "MonitorSyncState": "models",
    "MolSuiteMonitorBridge": "bridge",
    "MolSuiteMonitorWidget": "widget",
    "ProjectMonitorState": "models",
}


def __getattr__(name: str):
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = globals()[name] = getattr(import_module(f"{__name__}.{_LAZY[name]}"), name)
    return value


__all__ = sorted(_LAZY)
