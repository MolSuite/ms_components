"""The small Python boundary between tutorial content and a live Qt application."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QRect, SignalInstance
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class TutorialTarget:
    widget: QWidget | Callable[[], QWidget | None]
    prepare: Callable[[], None] | None = None
    rect: Callable[[], QRect] | None = None


@dataclass(frozen=True)
class TutorialEvent:
    signal: SignalInstance | Callable[[], SignalInstance]
    accept: Callable[..., bool] | None = None
    is_complete: Callable[[], bool] | None = None
