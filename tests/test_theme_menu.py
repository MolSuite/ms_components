from types import SimpleNamespace

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QWidget

from ms_components.ms_settings import AppSettingsPanel
from ms_components.theme import THEMES, SPECTRUM_THEMES, ThemeComboBox, build_theme_menu


def _leaves(menu):
    return [leaf for action in menu.actions()
            for leaf in (_leaves(action.menu()) if action.menu() else [action])]


def test_spectrum_menu_groups_modes_and_keeps_one_exclusive_selection():
    app = QApplication.instance() or QApplication([])
    menu = build_theme_menu("zensical_teal")
    try:
        root = menu.actions()
        assert [action.data() for action in root if not action.menu()] == [
            "auto", *(name for name in THEMES if not name.startswith("spectrum_")),
        ]
        spectrum = root[-1].menu()
        assert spectrum.title() == "Spectrum themes"
        assert "Zensical" in spectrum.menuAction().toolTip()
        assert menu.toolTipsVisible()
        assert [action.text() for action in spectrum.actions()] == ["Light", "Dark"]
        for mode_action, colors in zip(spectrum.actions(), SPECTRUM_THEMES.values()):
            assert [action.data() for action in mode_action.menu().actions()] == list(colors.values())
        leaves = _leaves(menu)
        assert [action.data() for action in leaves if action.isChecked()] == ["spectrum_dark_teal"]
        picked = []
        menu.triggered.connect(lambda action: picked.append(action.data()))
        next(action for action in leaves if action.data() == "spectrum_light_purple").trigger()
        assert picked == ["spectrum_light_purple"]
        assert [action.data() for action in leaves if action.isChecked()] == picked
        app.processEvents()
    finally:
        menu.deleteLater()


def test_settings_theme_combo_uses_the_menu_and_preserves_the_value_api():
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    entry = SimpleNamespace(annotation=str, choices=("auto", *THEMES), nullable=False)
    combo = AppSettingsPanel._create_editor(entry, parent)
    assert isinstance(combo, ThemeComboBox)
    combo.setCurrentIndex(combo.findData("spectrum_dark_teal"))
    changed = []
    combo.currentIndexChanged.connect(lambda _: changed.append(combo.currentData()))

    def choose():
        menu = app.activePopupWidget()
        try:
            next(action for action in _leaves(menu) if action.data() == "spectrum_dark_blue").trigger()
        finally:
            menu.close()

    QTimer.singleShot(0, choose)
    try:
        combo.showPopup()
        assert changed == ["spectrum_dark_blue"]
        assert combo.currentData() == "spectrum_dark_blue"
        for choices in (("one", "two"), (["one"], ["two"])):
            ordinary = AppSettingsPanel._create_editor(
                SimpleNamespace(annotation=str, choices=choices, nullable=False), parent,
            )
            assert type(ordinary) is QComboBox
            assert ordinary.itemData(0) == choices[0]
        app.processEvents()
    finally:
        parent.deleteLater()
