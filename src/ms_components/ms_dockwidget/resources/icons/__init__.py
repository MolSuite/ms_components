from importlib.resources import files

from PySide6.QtGui import QIcon


def icon(name: str) -> QIcon:
    return QIcon(str(files(__package__) / name))


__all__ = ["icon"]
