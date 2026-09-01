from PySide6.QtGui import QPalette

from ms_components.theme import THEMES, base_qss, build_palette, contrast_ratio, resolve


def test_remaining_themes_keep_tables_and_selections_legible():
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    assert "atom_one" not in THEMES
    assert "blender" not in THEMES
    assert resolve("atom_one") == "one_dark_two"
    assert resolve("blender") == "catppuccin_mocha"
    assert "QHeaderView::section" in base_qss()
    assert "background: palette(dark)" in base_qss()

    for name, theme in THEMES.items():
        palette = build_palette(theme)
        row_backgrounds = (
            palette.color(group.Active, role.Base),
            palette.color(group.Active, role.AlternateBase),
        )
        header = palette.color(group.Active, role.Dark)
        assert contrast_ratio(palette.color(group.Active, role.Text), header) >= 4.5, name
        assert min(contrast_ratio(header, bg) for bg in row_backgrounds) >= 1.45, name

        for state in (group.Active, group.Inactive):
            highlight = palette.color(state, role.Highlight)
            highlighted_text = palette.color(state, role.HighlightedText)
            assert contrast_ratio(highlighted_text, highlight) >= 4.5, (name, state)
            assert min(contrast_ratio(highlight, bg) for bg in row_backgrounds) >= 3.0, (name, state)
