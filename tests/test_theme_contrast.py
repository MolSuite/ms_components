from PySide6.QtGui import QColor, QPalette

from ms_components.theme import HUES, TONES, THEMES, base_qss, build_palette, contrast_ratio, resolve

def _floor(theme, key, minimum, *against):
    against = against or ("window", "base", "alternate_base")
    for surface in against:
        ratio = contrast_ratio(QColor(theme[key]), QColor(theme[surface]))
        assert ratio >= minimum, f"{key} on {surface}: {ratio:.2f} < {minimum}"

def test_removed_themes_fall_back():
    assert "atom_one" not in THEMES
    assert "blender" not in THEMES
    assert resolve("atom_one") == "one_dark_two"
    assert resolve("blender") == "catppuccin_mocha"
    assert "QHeaderView::section" in base_qss()
    assert "background: palette(dark)" in base_qss()

def test_every_theme_meets_the_contrast_floors():
    for name, theme in THEMES.items():
        try:
            _floor(theme, "text", 4.5)
            _floor(theme, "window_text", 4.5)
            _floor(theme, "button_text", 4.5, "button")
            _floor(theme, "text", 4.5, "dark")  # table header
            _floor(theme, "dark", 1.4, "base", "alternate_base")  # header band: decorative, just visible
            _floor(theme, "highlighted_text", 4.5, "highlight")
            _floor(theme, "highlight", 3.0)  # selection, focus ring, tab underline
            _floor(theme, "shadow", 3.0)  # control edges (WCAG 1.4.11)
            _floor(theme, "placeholder_text", 4.5)
            _floor(theme, "tooltip_text", 4.5, "tooltip_base")
            for key in ("link", "link_visited", "accent", *HUES):
                _floor(theme, key, 4.5)
        except AssertionError as error:
            raise AssertionError(f"{name}: {error}") from None

def test_muted_and_disabled_text_read_as_different_levels():
    for name, theme in THEMES.items():
        window = QColor(theme["window"])
        body = contrast_ratio(QColor(theme["text"]), window)
        hint = contrast_ratio(QColor(theme["placeholder_text"]), window)
        off = contrast_ratio(QColor(theme["disabled_text"]), window)
        assert off < hint < body, (name, off, hint, body)

def test_the_palette_carries_every_role_and_the_disabled_text():
    role, group = QPalette.ColorRole, QPalette.ColorGroup
    theme = THEMES["dracula"]
    palette = build_palette(theme)
    assert palette.color(role.Shadow).name() == theme["shadow"]
    assert palette.color(group.Inactive, role.Link).name() == theme["link"]  # no greyed links
    assert palette.color(group.Disabled, role.Text).name() == theme["disabled_text"]
    assert set(TONES) <= set(theme)


def test_checkbox_and_radio_edges_reach_three_to_one():
    from PySide6.QtWidgets import QApplication, QCheckBox, QRadioButton

    from ms_components.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme("catppuccin_mocha", app)  # Fusion alone draws these near 1.5:1
    window = app.palette().window().color()
    for box in (QCheckBox(), QRadioButton()):
        box.resize(box.sizeHint())
        image = box.grab().toImage()
        edge = max(contrast_ratio(image.pixelColor(x, y), window)
                   for x in range(min(image.width(), 24)) for y in range(image.height()))
        assert edge >= 3.0, (type(box).__name__, edge)
