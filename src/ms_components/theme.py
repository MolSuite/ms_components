"""Color themes for every MolSuite Qt app (QPalette-based).

Palette data and the QPalette role mapping are derived from **qt-themes** by
Beat Reichenbach, MIT-licensed:

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

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# Auto mode picks these based on the OS color scheme. Catppuccin is the only
# family here with a light+dark pair designed together, so it's the coherent auto
# default; dracula and the rest stay selectable.
DEFAULT_LIGHT = "github_light"
DEFAULT_DARK = "catppuccin_mocha"

# name -> {role: "#hex"}. Roles: primary/secondary, accents (magenta/red/orange/
# yellow/green/cyan/blue), text/subtext1/subtext0, overlay2..0, surface2..0,
# base/mantle/crust.
THEMES: dict[str, dict[str, str]] = {
    "catppuccin_frappe": {"primary": "#ca9ee6", "secondary": "#8caaee", "magenta": "#ca9ee6", "red": "#e78284", "orange": "#ef9f76", "yellow": "#e5c890", "green": "#a6d189", "cyan": "#99d1db", "blue": "#8caaee", "text": "#c6d0f5", "subtext1": "#b5bfe2", "subtext0": "#a5adce", "overlay2": "#949cbb", "overlay1": "#838ba7", "overlay0": "#737994", "surface2": "#626880", "surface1": "#51576d", "surface0": "#414559", "base": "#303446", "mantle": "#292c3c", "crust": "#232634"},
    "catppuccin_latte": {"primary": "#8839ef", "secondary": "#1e66f5", "magenta": "#8839ef", "red": "#d20f39", "orange": "#fe640b", "yellow": "#df8e1d", "green": "#40a02b", "cyan": "#04a5e5", "blue": "#1e66f5", "text": "#4c4f69", "subtext1": "#5c5f77", "subtext0": "#6c6f85", "overlay2": "#7c7f93", "overlay1": "#8c8fa1", "overlay0": "#9ca0b0", "surface2": "#9ca0b0", "surface1": "#bcc0cc", "surface0": "#ccd0da", "base": "#ccd0da", "mantle": "#e6e9ef", "crust": "#ffffff"},
    "catppuccin_macchiato": {"primary": "#c6a0f6", "secondary": "#8aadf4", "magenta": "#c6a0f6", "red": "#ed8796", "orange": "#f5a97f", "yellow": "#eed49f", "green": "#a6da95", "cyan": "#91d7e3", "blue": "#8aadf4", "text": "#cad3f5", "subtext1": "#b8c0e0", "subtext0": "#a5adcb", "overlay2": "#939ab7", "overlay1": "#8087a2", "overlay0": "#6e738d", "surface2": "#5b6078", "surface1": "#494d64", "surface0": "#363a4f", "base": "#24273a", "mantle": "#1e2030", "crust": "#181926"},
    "catppuccin_mocha": {"primary": "#cba6f7", "secondary": "#89b4fa", "magenta": "#cba6f7", "red": "#f38ba8", "orange": "#fab387", "yellow": "#f9e2af", "green": "#a6e3a1", "cyan": "#89dceb", "blue": "#89b4fa", "text": "#cdd6f4", "subtext1": "#bac2de", "subtext0": "#a6adc8", "overlay2": "#9399b2", "overlay1": "#7f849c", "overlay0": "#6c7086", "surface2": "#585b70", "surface1": "#45475a", "surface0": "#313244", "base": "#1e1e2e", "mantle": "#181825", "crust": "#11111b"},
    "dracula": {"primary": "#bd93f9", "secondary": "#ff79c6", "magenta": "#bd93f9", "red": "#ff5555", "orange": "#ffb86c", "yellow": "#f1fa8c", "green": "#50fa7b", "cyan": "#8be9fd", "blue": "#6272a4", "text": "#f8f8f2", "subtext1": "#DADBD9", "subtext0": "#BCBDBF", "overlay2": "#9EA0A6", "overlay1": "#80828D", "overlay0": "#626573", "surface2": "#44475a", "surface1": "#3B3D4E", "surface0": "#313442", "base": "#2D2F3C", "mantle": "#282a36", "crust": "#1d1b22"},
    "github_dark": {"primary": "#79c0ff", "secondary": "#56d364", "magenta": "#d2a8ff", "red": "#ffa198", "orange": "#ffa657", "yellow": "#e3b341", "green": "#56d364", "cyan": "#68CAB2", "blue": "#79c0ff", "text": "#d1d7e0", "subtext1": "#BEC4CD", "subtext0": "#ABB1BA", "overlay2": "#989EA7", "overlay1": "#858B94", "overlay0": "#727882", "surface2": "#5F656F", "surface1": "#4C525C", "surface0": "#3E444E", "base": "#262c36", "mantle": "#212830", "crust": "#151b23"},
    "github_light": {"primary": "#79c0ff", "secondary": "#56d364", "magenta": "#d2a8ff", "red": "#ffa198", "orange": "#ffa657", "yellow": "#e3b341", "green": "#56d364", "cyan": "#68CAB2", "blue": "#79c0ff", "text": "#1f2328", "subtext1": "#212830", "subtext0": "#262c36", "overlay2": "#444952", "overlay1": "#61666E", "overlay0": "#7F838A", "surface2": "#9DA1A6", "surface1": "#BBBEC2", "surface0": "#D8DBDE", "base": "#f6f8fa", "mantle": "#FBFCFD", "crust": "#ffffff"},
    "modern_dark": {"primary": "#2aa5da", "secondary": "#2ad7da", "magenta": "#b351de", "red": "#da4d2a", "orange": "#da8a2a", "yellow": "#d7da2a", "green": "#2ada6f", "cyan": "#2ad7da", "blue": "#2aa5da", "text": "#c8c8c8", "subtext1": "#b2b2b2", "subtext0": "#9b9b9b", "overlay2": "#858585", "overlay1": "#6f6f6f", "overlay0": "#585858", "surface2": "#424242", "surface1": "#3c3c3c", "surface0": "#353535", "base": "#2a2a2a", "mantle": "#1f1f1f", "crust": "#141414"},
    "modern_light": {"primary": "#2aa5da", "secondary": "#2ad7da", "magenta": "#b351de", "red": "#da4d2a", "orange": "#da8a2a", "yellow": "#d7da2a", "green": "#2ada6f", "cyan": "#2ad7da", "blue": "#2aa5da", "text": "#000000", "subtext1": "#131517", "subtext0": "#2d3032", "overlay2": "#484b4d", "overlay1": "#626568", "overlay0": "#7d8084", "surface2": "#979b9f", "surface1": "#b1b6ba", "surface0": "#ccd0d5", "base": "#e6ebf0", "mantle": "#eef2f6", "crust": "#ffffff"},
    "monokai": {"primary": "#ffd866", "secondary": "#ff6188", "magenta": "#ab9df2", "red": "#ff6188", "orange": "#fc9867", "yellow": "#ffd866", "green": "#a9dc76", "cyan": "#91dcaf", "blue": "#78dce8", "text": "#fcfcfa", "subtext1": "#c1c0c0", "subtext0": "#c1c0c0", "overlay2": "#939293", "overlay1": "#939293", "overlay0": "#727072", "surface2": "#5b595c", "surface1": "#4e4c4f", "surface0": "#403e41", "base": "#2d2a2e", "mantle": "#221f22", "crust": "#19181a"},
    "nord": {"primary": "#81a1c1", "secondary": "#88c0d0", "magenta": "#b48ead", "red": "#bf616a", "orange": "#d08770", "yellow": "#ebcb8b", "green": "#a3be8c", "cyan": "#88c0d0", "blue": "#81a1c1", "text": "#eceff4", "subtext1": "#e5e9f0", "subtext0": "#d8dee9", "overlay2": "#d8dee9", "overlay1": "#d8dee9", "overlay0": "#4c566a", "surface2": "#4c566a", "surface1": "#434c5e", "surface0": "#3b4252", "base": "#3b4252", "mantle": "#2e3440", "crust": "#2e3440"},
    "one_dark_two": {"primary": "#62bac6", "secondary": "#eac786", "magenta": "#c88bda", "red": "#e27881", "orange": "#e79c7e", "yellow": "#eac786", "green": "#98c379", "cyan": "#62bac6", "blue": "#71b9f4", "text": "#e6e6e6", "subtext1": "#c9ccd3", "subtext0": "#abb2bf", "overlay2": "#969dab", "overlay1": "#818896", "overlay0": "#6c7280", "surface2": "#5b626d", "surface1": "#4a505a", "surface0": "#393e47", "base": "#282c34", "mantle": "#21252b", "crust": "#1d1f23"},
}


_current: dict[str, str] = THEMES[DEFAULT_DARK]

_REMOVED_THEME_FALLBACKS = {
    "atom_one": "one_dark_two",
    "blender": DEFAULT_DARK,
}


def is_dark(theme: dict[str, str] | None = None) -> bool:
    """A theme is dark when its text is brighter than its base background."""
    theme = theme or _current
    return QColor(theme["text"]).value() > QColor(theme["base"]).value()


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


def _mix(left: QColor, right: QColor, amount: float) -> QColor:
    return QColor.fromRgbF(*(
        a + (b - a) * amount
        for a, b in zip(left.getRgbF(), right.getRgbF())
    ))


def _surface_with_contrast(
    source: QColor,
    *,
    foreground: QColor,
    adjacent: QColor | tuple[QColor, ...],
    text_minimum: float,
    separation_minimum: float,
) -> QColor:
    """Closest tint/shade satisfying both readable text and visible separation."""
    adjacent_colors = adjacent if isinstance(adjacent, tuple) else (adjacent,)
    targets = (QColor("#000000"), QColor("#ffffff"))
    for step in range(101):
        amount = step / 100
        for target in targets:
            candidate = _mix(source, target, amount)
            if (contrast_ratio(foreground, candidate) >= text_minimum
                    and all(
                        contrast_ratio(candidate, background) >= separation_minimum
                        for background in adjacent_colors
                    )):
                return candidate
    return source


def _contrasting_text(background: QColor, theme: dict[str, str]) -> QColor:
    themed = [QColor(theme[key]) for key in ("text", "base", "mantle", "crust")]
    best = max(themed, key=lambda candidate: contrast_ratio(candidate, background))
    if contrast_ratio(best, background) >= 4.5:
        return best
    return max(
        (QColor("#000000"), QColor("#ffffff")),
        key=lambda candidate: contrast_ratio(candidate, background),
    )


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
    """Build a QPalette from a theme dict.

    Port of qt-themes' `update_palette` (MIT, Beat Reichenbach), adapted to read
    from a flat dict instead of a dataclass.
    """
    c = lambda role: QColor(theme[role])  # noqa: E731
    Role = QPalette.ColorRole
    Group = QPalette.ColorGroup
    pal = QPalette()

    dark_theme = is_dark(theme)
    table_base = c("mantle") if dark_theme else c("crust")
    table_alternate = c("base") if dark_theme else c("mantle")
    highlight = _surface_with_contrast(
        c("primary"),
        foreground=_contrasting_text(c("primary"), theme),
        adjacent=(table_base, table_alternate),
        text_minimum=4.5,
        separation_minimum=3.0,
    )
    highlight_text = _contrasting_text(highlight, theme)
    header = _surface_with_contrast(
        c("surface1"),
        foreground=c("text"),
        adjacent=(table_base, table_alternate),
        text_minimum=4.5,
        separation_minimum=1.45,
    )

    h, s, v, a = c("text").getHsvF()
    bright_text = QColor.fromHsvF(h, s, 1 - v, a)

    # Active/Normal group
    if is_dark(theme):
        pal.setColor(Role.Base, c("mantle"))
        pal.setColor(Role.AlternateBase, c("base"))
    else:
        pal.setColor(Role.Base, c("crust"))
        pal.setColor(Role.AlternateBase, c("mantle"))
    pal.setColor(Role.Window, c("base"))
    pal.setColor(Role.WindowText, c("text"))
    pal.setColor(Role.PlaceholderText, c("overlay1"))
    pal.setColor(Role.Text, c("text"))
    pal.setColor(Role.Button, c("base"))
    pal.setColor(Role.ButtonText, c("text"))
    pal.setColor(Role.BrightText, bright_text)
    pal.setColor(Role.ToolTipBase, c("mantle"))
    pal.setColor(Role.ToolTipText, c("overlay2"))

    pal.setColor(Role.Highlight, highlight)
    pal.setColor(Role.HighlightedText, highlight_text)
    pal.setColor(Role.Link, c("secondary"))
    pal.setColor(Role.LinkVisited, c("secondary"))

    pal.setColor(Role.Light, c("crust"))
    pal.setColor(Role.Midlight, c("mantle"))
    # Mid is *the* border tone: `palette(mid)` is what every stylesheet uses for
    # hairlines, so it must be the conventional Catppuccin-style separator.
    pal.setColor(Role.Mid, c("surface2"))
    pal.setColor(Role.Dark, header)
    pal.setColor(Role.Shadow, c("overlay0"))

    # Inactive group
    pal.setColor(Group.Inactive, Role.Highlight, highlight)
    pal.setColor(Group.Inactive, Role.HighlightedText, highlight_text)
    pal.setColor(Group.Inactive, Role.Link, c("surface1"))
    pal.setColor(Group.Inactive, Role.LinkVisited, c("surface1"))

    # Disabled group
    pal.setColor(Group.Disabled, Role.WindowText, c("overlay1"))
    pal.setColor(Group.Disabled, Role.Base, c("base"))
    pal.setColor(Group.Disabled, Role.AlternateBase, c("base"))
    pal.setColor(Group.Disabled, Role.Text, c("overlay1"))
    pal.setColor(Group.Disabled, Role.PlaceholderText, c("overlay1"))
    pal.setColor(Group.Disabled, Role.Button, c("base"))
    pal.setColor(Group.Disabled, Role.ButtonText, c("overlay1"))
    pal.setColor(Group.Disabled, Role.BrightText, c("mantle"))
    pal.setColor(Group.Disabled, Role.Highlight, c("surface2"))
    pal.setColor(Group.Disabled, Role.HighlightedText, _contrasting_text(c("surface2"), theme))
    pal.setColor(Group.Disabled, Role.Link, c("surface0"))
    pal.setColor(Group.Disabled, Role.LinkVisited, c("surface0"))

    pal.setColor(Role.Accent, c("secondary"))
    pal.setColor(Group.Inactive, Role.Accent, c("surface1"))
    pal.setColor(Group.Disabled, Role.Accent, c("surface2"))

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


def base_qss() -> str:
    """The shared geometry stylesheet (colors resolved from the live palette)."""
    return files(__package__).joinpath("base.qss").read_text(encoding="utf-8")


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
    app.setStyle("Fusion")  # Fusion honors QPalette ColorRoles most faithfully
    app.setPalette(build_palette(_current))
    app.setStyleSheet(base_qss())


if __name__ == "__main__":
    # Self-check: every theme builds a palette; light/dark classification holds.
    for _name, _t in THEMES.items():
        assert set(_t) >= {"text", "base", "primary", "mantle", "surface2"}, _name
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
