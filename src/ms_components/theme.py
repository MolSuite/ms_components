"""Color themes for every MolSuite Qt app (QPalette-based).

Palette data is derived from **qt-themes** by Beat Reichenbach, MIT-licensed:

    https://github.com/beatreichenbach/qt-themes
    Copyright (c) 2024 Beat Reichenbach

The color values are vendored here (they are data, not code) so no extra runtime
dependency is needed. Full MIT text: `licenses/qt-themes-LICENSE.txt`; keep this
attribution if you redistribute.

Widgets should not hardcode colors. Two mechanisms cover everything:

* `palette(role)` in QSS / `QApplication.palette()` in paint code — resolved live,
  so a theme switch repaints without touching a single widget.
* `color("red"/"green"/...)` for semantic accents (status dots, warnings) that
  have no QPalette role.

Same idea for type: `font(role)` derives from the *app* font instead of hardcoding
sizes, so the OS/user font and DPI carry through. Roles are data (`FONT_ROLES`), not
classes -- a title is a scale factor and a weight, nothing worth an object.
"""
from __future__ import annotations

from importlib.resources import files

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette, QPen
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

from ms_components.palettes import DEFAULT_DARK, DEFAULT_LIGHT, THEMES

_current: dict[str, str] = THEMES[DEFAULT_DARK]

#: theme key -> QPalette role (the keys are the roles in snake_case).
_ROLES = {
    "window": QPalette.ColorRole.Window,
    "window_text": QPalette.ColorRole.WindowText,
    "base": QPalette.ColorRole.Base,
    "alternate_base": QPalette.ColorRole.AlternateBase,
    "tooltip_base": QPalette.ColorRole.ToolTipBase,
    "tooltip_text": QPalette.ColorRole.ToolTipText,
    "placeholder_text": QPalette.ColorRole.PlaceholderText,
    "text": QPalette.ColorRole.Text,
    "button": QPalette.ColorRole.Button,
    "button_text": QPalette.ColorRole.ButtonText,
    "bright_text": QPalette.ColorRole.BrightText,
    "light": QPalette.ColorRole.Light,
    "midlight": QPalette.ColorRole.Midlight,
    "mid": QPalette.ColorRole.Mid,
    "dark": QPalette.ColorRole.Dark,
    "shadow": QPalette.ColorRole.Shadow,
    "highlight": QPalette.ColorRole.Highlight,
    "highlighted_text": QPalette.ColorRole.HighlightedText,
    "link": QPalette.ColorRole.Link,
    "link_visited": QPalette.ColorRole.LinkVisited,
    "accent": QPalette.ColorRole.Accent,
}

_REMOVED_THEME_FALLBACKS = {
    "atom_one": "one_dark_two",
    "blender": DEFAULT_DARK,
}


def is_dark(theme: dict[str, str] | None = None) -> bool:
    """A theme is dark when its text is brighter than its window."""
    theme = theme or _current
    return QColor(theme["window_text"]).value() > QColor(theme["window"]).value()


def current_theme() -> dict[str, str]:
    """The theme dict currently applied (defaults before any `apply_theme`)."""
    return _current


def color(role: str) -> QColor:
    """A semantic accent from the live theme (`red`, `green`, `orange`, ...).

    For anything with a QPalette role (background, text, borders, highlight) use
    the palette instead — this is only for accents Qt has no role for.
    """
    return QColor(_current[role])


def _luminance(value: QColor) -> float:
    channels = (value.redF(), value.greenF(), value.blueF())
    linear = tuple(
        channel / 12.92 if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(left: QColor, right: QColor) -> float:
    """WCAG contrast ratio used to keep generated palette states readable."""
    lighter, darker = sorted((_luminance(left), _luminance(right)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


#: role -> (scale over the app font, bold). Relative on purpose: the base size is
#: whatever Qt resolved for this desktop, so a user with a 14pt system font gets a
#: proportional title instead of the 18px somebody typed into a stylesheet once.
FONT_ROLES: dict[str, tuple[float, bool]] = {
    "title": (1.35, True),
    "subtitle": (1.15, True),
    "body": (1.0, False),
    "strong": (1.0, True),
    "caption": (0.85, False),  # chips, hints, status lines
}


def font(role: str = "body", *, mono: bool = False) -> QFont:
    """A QFont for a named role, derived from the application font.

    `mono=True` swaps in the platform's fixed-width family (scores, ids, paths) and
    keeps the role's size/weight.
    """
    app = QApplication.instance()
    base = app.font() if app is not None else QFont()
    scale, bold = FONT_ROLES.get(role, FONT_ROLES["body"])
    result = QFontDatabase.systemFont(QFontDatabase.FixedFont) if mono else QFont(base)
    if base.pointSizeF() > 0:  # a font set in pixels reports -1 here
        result.setPointSizeF(base.pointSizeF() * scale)
    else:
        result.setPixelSize(max(1, round(base.pixelSize() * scale)))
    result.setBold(bold)
    return result


#: Base point size for apps that would rather not depend on the desktop. Qt takes its
#: font from the platform theme (gtk3/kde/win/mac) and, when that plugin fails to load
#: -- common under conda --, falls back to "Sans Serif" 9pt, smaller than the rest of
#: the system. In points, not pixels: points are already DPI-independent.
DEFAULT_FONT_PT = 10.0


def set_base_font(points: float = DEFAULT_FONT_PT, *, family: str | None = None,
                  app: QApplication | None = None) -> QFont:
    """Set the application base font: the root everything else inherits from.

    One place instead of sizes scattered through the QSS: `font(role)` scales off this
    one, widgets that do not override it inherit it, and the QSS can go without a single
    `font-size` rule (a stylesheet rule would override this).

    Call it before creating windows: widgets already built with their own font keep it.
    """
    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError("set_base_font requires a running QApplication")
    result = QFont(app.font())
    if family:  # by default the system family is kept and only the size is set
        result.setFamily(family)
    result.setPointSizeF(float(points))
    app.setFont(result)
    return result


def build_palette(theme: dict[str, str]) -> QPalette:
    """Build a QPalette from a theme dict: one key per role, plus the Disabled text."""
    Role = QPalette.ColorRole
    Group = QPalette.ColorGroup
    pal = QPalette()
    for key, role in _ROLES.items():
        pal.setColor(role, QColor(theme[key]))  # all groups; Disabled is overridden below
    disabled = QColor(theme["disabled_text"])
    for role in (Role.WindowText, Role.Text, Role.ButtonText, Role.PlaceholderText, Role.BrightText,
                 Role.HighlightedText, Role.Link, Role.LinkVisited, Role.Accent):
        pal.setColor(Group.Disabled, role, disabled)
    for role in (Role.Base, Role.AlternateBase, Role.Button):
        pal.setColor(Group.Disabled, role, QColor(theme["window"]))
    pal.setColor(Group.Disabled, Role.Highlight, QColor(theme["mid"]))
    return pal


def resolve(name: str) -> str:
    """Resolve auto, retired and invalid names to an available concrete theme."""
    if name != "auto":
        candidate = _REMOVED_THEME_FALLBACKS.get(name, name)
        return candidate if candidate in THEMES else DEFAULT_DARK
    from PySide6.QtCore import Qt

    hints = QApplication.styleHints()
    scheme = hints.colorScheme() if hints else Qt.ColorScheme.Unknown
    return DEFAULT_DARK if scheme == Qt.ColorScheme.Dark else DEFAULT_LIGHT


#: The accents a widget can wear through `setProperty("tone", name)`.
TONES = ("green", "red")
HUES = ("red", "orange", "yellow", "green", "cyan", "blue", "magenta")


def tone_qss(theme: dict[str, str] | None = None) -> str:
    """`QProgressBar[tone="green"]`, `QLabel[tone="blue"]` and siblings, from the live theme.

    QSS has no palette role for the accents, so these rules are written per theme.
    Bars are translucent, so their text stays readable on dark and light themes alike;
    labels take the hue as text (every hue is >= 4.5:1 on the theme's surfaces).
    """
    theme = theme or _current
    rules = []
    for tone in TONES:
        accent = QColor(theme[tone])
        rgba = f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, 150)"
        rules.append(f'QProgressBar[tone="{tone}"]::chunk {{ background: {rgba}; }}')
    rules += [f'QLabel[tone="{hue}"] {{ color: {theme[hue]}; }}' for hue in HUES]
    return "\n".join(rules) + "\n"


def base_qss() -> str:
    """The shared geometry stylesheet (colors resolved from the live palette)."""
    return files(__package__).joinpath("base.qss").read_text(encoding="utf-8")


class _EdgedFusion(QProxyStyle):
    """Fusion with checkbox/radio outlines in `shadow`.

    Fusion draws them as `window.darker(140)`, which no palette role reaches and which
    sits near 1.5:1 in most themes. A QSS `::indicator` rule would replace the check mark
    too, so the outline is redrawn on top of Fusion's own indicator instead.
    """

    def __init__(self):
        super().__init__("Fusion")

    def drawPrimitive(self, element, option, painter, widget=None):
        super().drawPrimitive(element, option, painter, widget)
        if element not in (QStyle.PrimitiveElement.PE_IndicatorCheckBox,
                           QStyle.PrimitiveElement.PE_IndicatorRadioButton):
            return
        if not option.state & QStyle.StateFlag.State_Enabled:
            return  # disabled keeps Fusion's faint edge: it should read as "off"
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        edge = option.palette.color(QPalette.ColorRole.Shadow)
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            painter.setPen(QPen(edge, 1))
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
        else:  # 1.5 px antialiased: a 1 px ring blurs to ~2.7:1
            painter.setRenderHint(painter.RenderHint.Antialiasing)
            painter.setPen(QPen(edge, 1.5))
            painter.drawEllipse(option.rect.toRectF().adjusted(1.5, 1.5, -1.5, -1.5))
        painter.restore()


def apply_theme(name: str, app: QApplication | None = None, *,
                base_font_pt: float | None = None) -> None:
    """Apply a theme (or "auto") to the QApplication.

    Re-applies live to every existing widget. Non-Qt "islands" (PyMOL, pyqtgraph)
    do not observe this and must be pushed separately.
    """
    global _current
    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError("apply_theme requires a running QApplication")
    _current = THEMES[resolve(name)]
    if base_font_pt is not None:  # optional: omit it and the system font stays
        set_base_font(base_font_pt, app=app)
    if not isinstance(app.style(), _EdgedFusion):
        app.setStyle(_EdgedFusion())  # Fusion honors QPalette ColorRoles most faithfully
    app.setPalette(build_palette(_current))
    app.setStyleSheet(base_qss() + tone_qss())


if __name__ == "__main__":
    # Self-check: every theme builds a palette; light/dark classification holds.
    for _name, _t in THEMES.items():
        assert set(_t) >= set(_ROLES) | {"disabled_text", *HUES}, _name
        assert build_palette(_t).color(QPalette.ColorRole.Window).isValid(), _name
    assert is_dark(THEMES["dracula"]) is True
    assert is_dark(THEMES["catppuccin_latte"]) is False
    assert resolve("dracula") == "dracula"
    assert "palette(mid)" in base_qss() and "${" not in base_qss()
    _app = QApplication.instance() or QApplication([])
    _base = _app.font().pointSizeF()
    assert font("body").pointSizeF() == _base
    assert font("title").pointSizeF() > _base and font("title").bold()
    assert font("caption").pointSizeF() < _base
    assert font("nonexistent").pointSizeF() == _base  # unknown role degrades to body
    assert font("caption", mono=True).family() != font("caption").family()
    set_base_font(12.0, app=_app)
    assert _app.font().pointSizeF() == 12.0
    assert font("body").pointSizeF() == 12.0 and font("title").pointSizeF() == 12.0 * 1.35
    set_base_font(_base, app=_app)  # the check must not leave the app on another font
    print(f"ok: {len(THEMES)} themes, palettes valid")
