"""The color values of every theme, as data: no Qt, so a settings model can list their names.

Palette data from **qt-themes** by Beat Reichenbach (MIT, see `ms_components.theme`), stored
here per QPalette role and nudged to the contrast floors that `tests/test_theme_contrast.py`
enforces. How the keys become a QPalette: `ms_components.theme.build_palette`.

Keys are the QPalette roles in snake_case, so a value is exactly what `palette(role)` returns
in a stylesheet. What MolSuite asks of the roles Qt leaves loosely defined:

* ``mid``: hairlines (separators, frames, table and group borders). Decorative.
* ``shadow``: the edge of a control (field, button, checkbox, radio); >= 3:1 on every surface.
* ``dark``: table header surface. ``midlight``: thin progress tracks.
* ``placeholder_text``: muted text (hints, meta lines); >= 4.5:1, below the body text.
* ``disabled_text``: the Disabled group's text; dimmer than a hint, so "off" reads as off.

The hues (red, orange, yellow, green, cyan, blue, magenta) have no QPalette role: read them
with `ms_components.theme.color`. Each is >= 4.5:1 on the theme's surfaces, since they are
used as text (errors, warnings) as well as fills.
"""
from __future__ import annotations

# Auto mode picks these based on the OS color scheme.
DEFAULT_LIGHT = "github_light"
DEFAULT_DARK = "catppuccin_mocha"

THEMES: dict[str, dict[str, str]] = {
    "catppuccin_frappe": {"window": "#303446", "window_text": "#c6d0f5", "base": "#292c3c", "alternate_base": "#303446", "tooltip_base": "#292c3c", "tooltip_text": "#949cbb", "placeholder_text": "#959dbb", "text": "#c6d0f5", "button": "#303446", "button_text": "#c6d0f5", "bright_text": "#08080a", "light": "#232634", "midlight": "#292c3c", "mid": "#626880", "dark": "#51576d", "shadow": "#777d97", "highlight": "#ca9ee6", "highlighted_text": "#232634", "link": "#8caaee", "link_visited": "#8caaee", "accent": "#8caaee", "disabled_text": "#6c728c", "red": "#e78284", "orange": "#ef9f76", "yellow": "#e5c890", "green": "#a6d189", "cyan": "#99d1db", "blue": "#8caaee", "magenta": "#ca9ee6"},
    "catppuccin_latte": {"window": "#ccd0da", "window_text": "#4c4f69", "base": "#ffffff", "alternate_base": "#e6e9ef", "tooltip_base": "#e6e9ef", "tooltip_text": "#666879", "placeholder_text": "#555871", "text": "#4c4f69", "button": "#ccd0da", "button_text": "#4c4f69", "bright_text": "#6d7196", "light": "#ffffff", "midlight": "#e6e9ef", "mid": "#9ca0b0", "dark": "#bfc3ce", "shadow": "#70737f", "highlight": "#8839ef", "highlighted_text": "#ffffff", "link": "#094cd2", "link_visited": "#094cd2", "accent": "#094cd2", "disabled_text": "#7a7d92", "red": "#b30d31", "orange": "#9b3901", "yellow": "#7c4f10", "green": "#29661b", "cyan": "#025f83", "blue": "#094cd2", "magenta": "#7113ec"},
    "catppuccin_macchiato": {"window": "#24273a", "window_text": "#cad3f5", "base": "#1e2030", "alternate_base": "#24273a", "tooltip_base": "#1e2030", "tooltip_text": "#939ab7", "placeholder_text": "#888eaa", "text": "#cad3f5", "button": "#24273a", "button_text": "#cad3f5", "bright_text": "#08090a", "light": "#181926", "midlight": "#1e2030", "mid": "#5b6078", "dark": "#494d64", "shadow": "#6e738d", "highlight": "#c6a0f6", "highlighted_text": "#181926", "link": "#8aadf4", "link_visited": "#8aadf4", "accent": "#8aadf4", "disabled_text": "#61677f", "red": "#ed8796", "orange": "#f5a97f", "yellow": "#eed49f", "green": "#a6da95", "cyan": "#91d7e3", "blue": "#8aadf4", "magenta": "#c6a0f6"},
    "catppuccin_mocha": {"window": "#1e1e2e", "window_text": "#cdd6f4", "base": "#181825", "alternate_base": "#1e1e2e", "tooltip_base": "#181825", "tooltip_text": "#9399b2", "placeholder_text": "#82879f", "text": "#cdd6f4", "button": "#1e1e2e", "button_text": "#cdd6f4", "bright_text": "#090a0b", "light": "#11111b", "midlight": "#181825", "mid": "#585b70", "dark": "#45475a", "shadow": "#6c7086", "highlight": "#cba6f7", "highlighted_text": "#11111b", "link": "#89b4fa", "link_visited": "#89b4fa", "accent": "#89b4fa", "disabled_text": "#5d6075", "red": "#f38ba8", "orange": "#fab387", "yellow": "#f9e2af", "green": "#a6e3a1", "cyan": "#89dceb", "blue": "#89b4fa", "magenta": "#cba6f7"},
    "dracula": {"window": "#2d2f3c", "window_text": "#f8f8f2", "base": "#282a36", "alternate_base": "#2d2f3c", "tooltip_base": "#282a36", "tooltip_text": "#9ea0a6", "placeholder_text": "#97989b", "text": "#f8f8f2", "button": "#2d2f3c", "button_text": "#f8f8f2", "bright_text": "#070707", "light": "#1d1b22", "midlight": "#282a36", "mid": "#44475a", "dark": "#474959", "shadow": "#767985", "highlight": "#bd93f9", "highlighted_text": "#1d1b22", "link": "#ff79c6", "link_visited": "#ff79c6", "accent": "#ff79c6", "disabled_text": "#6e6f76", "red": "#ff6262", "orange": "#ffb86c", "yellow": "#f1fa8c", "green": "#50fa7b", "cyan": "#8be9fd", "blue": "#8a96bb", "magenta": "#bd93f9"},
    "github_dark": {"window": "#262c36", "window_text": "#d1d7e0", "base": "#212830", "alternate_base": "#262c36", "tooltip_base": "#212830", "tooltip_text": "#989ea7", "placeholder_text": "#8d939c", "text": "#d1d7e0", "button": "#262c36", "button_text": "#d1d7e0", "bright_text": "#1d1e1f", "light": "#151b23", "midlight": "#212830", "mid": "#5f656f", "dark": "#4c525c", "shadow": "#727882", "highlight": "#79c0ff", "highlighted_text": "#151b23", "link": "#79c0ff", "link_visited": "#79c0ff", "accent": "#79c0ff", "disabled_text": "#656b75", "red": "#ffa198", "orange": "#ffa657", "yellow": "#e3b341", "green": "#56d364", "cyan": "#68cab2", "blue": "#79c0ff", "magenta": "#d2a8ff"},
    "github_light": {"window": "#f6f8fa", "window_text": "#1f2328", "base": "#ffffff", "alternate_base": "#fbfcfd", "tooltip_base": "#fbfcfd", "tooltip_text": "#444952", "placeholder_text": "#61666e", "text": "#1f2328", "button": "#f6f8fa", "button_text": "#1f2328", "bright_text": "#a7bcd7", "light": "#ffffff", "midlight": "#fbfcfd", "mid": "#9da1a6", "dark": "#bbbec2", "shadow": "#7f838a", "highlight": "#5a94c8", "highlighted_text": "#1f2328", "link": "#0071d5", "link_visited": "#0071d5", "accent": "#0071d5", "disabled_text": "#979a9e", "red": "#e21400", "orange": "#b85600", "yellow": "#8f6b15", "green": "#22822d", "cyan": "#2c7e6a", "blue": "#0071d5", "magenta": "#9838ff"},
    "modern_dark": {"window": "#2a2a2a", "window_text": "#c8c8c8", "base": "#1f1f1f", "alternate_base": "#2a2a2a", "tooltip_base": "#1f1f1f", "tooltip_text": "#868686", "placeholder_text": "#919191", "text": "#c8c8c8", "button": "#2a2a2a", "button_text": "#c8c8c8", "bright_text": "#373737", "light": "#141414", "midlight": "#1f1f1f", "mid": "#424242", "dark": "#444444", "shadow": "#737373", "highlight": "#2aa5da", "highlighted_text": "#141414", "link": "#2ad7da", "link_visited": "#2ad7da", "accent": "#2ad7da", "disabled_text": "#696969", "red": "#e16f53", "orange": "#da8a2a", "yellow": "#d7da2a", "green": "#2ada6f", "cyan": "#2ad7da", "blue": "#2aa5da", "magenta": "#c06fe4"},
    "modern_light": {"window": "#e6ebf0", "window_text": "#000000", "base": "#ffffff", "alternate_base": "#eef2f6", "tooltip_base": "#eef2f6", "tooltip_text": "#484b4d", "placeholder_text": "#626568", "text": "#000000", "button": "#e6ebf0", "button_text": "#000000", "bright_text": "#ffffff", "light": "#ffffff", "midlight": "#eef2f6", "mid": "#979b9f", "dark": "#b1b6ba", "shadow": "#7d8084", "highlight": "#2590be", "highlighted_text": "#000000", "link": "#157677", "link_visited": "#157677", "accent": "#157677", "disabled_text": "#8f9295", "red": "#bb3f20", "orange": "#945c1a", "yellow": "#6b6d13", "green": "#157a3d", "cyan": "#157677", "blue": "#1a7196", "magenta": "#a22ad7"},
    "monokai": {"window": "#2d2a2e", "window_text": "#fcfcfa", "base": "#221f22", "alternate_base": "#2d2a2e", "tooltip_base": "#221f22", "tooltip_text": "#939293", "placeholder_text": "#939293", "text": "#fcfcfa", "button": "#2d2a2e", "button_text": "#fcfcfa", "bright_text": "#030303", "light": "#19181a", "midlight": "#221f22", "mid": "#5b595c", "dark": "#4e4c4f", "shadow": "#757375", "highlight": "#ffd866", "highlighted_text": "#19181a", "link": "#ff6188", "link_visited": "#ff6188", "accent": "#ff6188", "disabled_text": "#6b696b", "red": "#ff6188", "orange": "#fc9867", "yellow": "#ffd866", "green": "#a9dc76", "cyan": "#91dcaf", "blue": "#78dce8", "magenta": "#ab9df2"},
    "nord": {"window": "#3b4252", "window_text": "#eceff4", "base": "#2e3440", "alternate_base": "#3b4252", "tooltip_base": "#2e3440", "tooltip_text": "#d8dee9", "placeholder_text": "#abafb8", "text": "#eceff4", "button": "#3b4252", "button_text": "#eceff4", "bright_text": "#0b0b0b", "light": "#2e3440", "midlight": "#2e3440", "mid": "#4c566a", "dark": "#525a6b", "shadow": "#878e9b", "highlight": "#81a1c1", "highlighted_text": "#2e3440", "link": "#88c0d0", "link_visited": "#88c0d0", "accent": "#88c0d0", "disabled_text": "#7c828e", "red": "#d89fa4", "orange": "#daa18f", "yellow": "#ebcb8b", "green": "#a3be8c", "cyan": "#88c0d0", "blue": "#97b2cc", "magenta": "#c3a5be"},
    "one_dark_two": {"window": "#282c34", "window_text": "#e6e6e6", "base": "#21252b", "alternate_base": "#282c34", "tooltip_base": "#21252b", "tooltip_text": "#969dab", "placeholder_text": "#919296", "text": "#e6e6e6", "button": "#282c34", "button_text": "#e6e6e6", "bright_text": "#191919", "light": "#1d1f23", "midlight": "#21252b", "mid": "#5b626d", "dark": "#4a505a", "shadow": "#6f7583", "highlight": "#62bac6", "highlighted_text": "#1d1f23", "link": "#eac786", "link_visited": "#eac786", "accent": "#eac786", "disabled_text": "#696b71", "red": "#e27881", "orange": "#e79c7e", "yellow": "#eac786", "green": "#98c379", "cyan": "#62bac6", "blue": "#71b9f4", "magenta": "#c88bda"},
}


GITHUB_LIGHT_FRAPPE = "github_light_frappe"
G_THEME = "g"


def _contrast_color(foreground: str, backgrounds: tuple[str, ...], minimum: float = 4.5) -> str:
    """Darken an accent toward black until it is legible on each light surface."""
    def luminance(value: str) -> float:
        channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                  for channel in channels]
        return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    rgb = [int(foreground[index:index + 2], 16) for index in (1, 3, 5)]
    background_luminances = [luminance(color) for color in backgrounds]
    for factor in range(255, -1, -1):
        color = "#" + "".join(f"{round(channel * factor / 255):02x}" for channel in rgb)
        lightness = luminance(color)
        if all((max(lightness, bg) + 0.05) / (min(lightness, bg) + 0.05) >= minimum
               for bg in background_luminances):
            return color
    return "#000000"


def _github_light_frappe_palette() -> dict[str, str]:
    github_light = THEMES["github_light"]
    frappe = THEMES["catppuccin_frappe"]
    palette = dict(github_light)
    # Retain Frappé's lavender while meeting the selection contrast floor.
    surfaces = tuple(github_light[key] for key in ("window", "base", "alternate_base"))
    palette["highlight"] = _contrast_color(frappe["highlight"], surfaces, 3.0)
    palette["highlighted_text"] = frappe["highlighted_text"]
    for role in ("red", "orange", "yellow", "green", "cyan", "blue", "magenta", "accent", "link", "link_visited"):
        palette[role] = _contrast_color(frappe[role], surfaces)
    return palette


def _github_light_dracula_palette() -> dict[str, str]:
    github_light = THEMES["github_light"]
    dracula = THEMES["dracula"]
    palette = dict(github_light)
    # Swap Dracula's secondary pink and primary purple for highlight and accent.
    surfaces = tuple(github_light[key] for key in ("window", "base", "alternate_base"))
    palette["highlight"] = _contrast_color(dracula["accent"], surfaces, 3.0)
    palette["highlighted_text"] = dracula["highlighted_text"]
    palette["accent"] = _contrast_color(dracula["highlight"], surfaces)
    for role in ("red", "orange", "yellow", "green", "cyan", "blue", "magenta"):
        palette[role] = _contrast_color(dracula[role], surfaces)
    # Links use Dracula's primary purple, darkened for text on light surfaces.
    palette["link"] = palette["link_visited"] = _contrast_color(dracula["highlight"], surfaces)
    return palette


# Shared hybrid palettes, available to every application using this registry.
THEMES[GITHUB_LIGHT_FRAPPE] = _github_light_frappe_palette()
THEMES[G_THEME] = _github_light_dracula_palette()
