"""Monitor colors, resolved live from the QPalette and the active theme.

`P` is a lazy mapping: every `P["key"]` read returns a color from the *current*
app palette, so anything that paints (or rebuilds HTML) follows the theme.
Stylesheets should not use it — write `palette(role)` in QSS instead, which Qt
resolves live. `P` only exists for the two cases QSS can't cover: QPainter code
and rich-text spans.

Status colors (ok/warn/error) have no QPalette role, so they come from the
theme's semantic accents.
"""
from __future__ import annotations

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from ms_components.theme import color

_SEMANTIC = {"ok": "green", "warn": "yellow", "error": "red"}

_ROLES = {
    "bg": QPalette.ColorRole.Window,
    "panel": QPalette.ColorRole.Base,
    "panel_alt": QPalette.ColorRole.AlternateBase,
    "border": QPalette.ColorRole.Mid,
    "text": QPalette.ColorRole.Text,
    "text_muted": QPalette.ColorRole.PlaceholderText,
    "accent": QPalette.ColorRole.Highlight,
}


class _LivePalette:
    def __getitem__(self, key: str) -> str:
        if key in _SEMANTIC:
            return color(_SEMANTIC[key]).name()
        app = QApplication.instance()
        pal = app.palette() if app else QPalette()
        return pal.color(_ROLES[key]).name()


P = _LivePalette()
