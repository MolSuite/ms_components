from pathlib import Path

from ms_flow.api import PydanticConfiguration
from pydantic import BaseModel, Field
from PySide6.QtWidgets import QApplication, QCheckBox, QSpinBox

from ms_components.ms_settings import AppSettingsPanel


class _DisplaySettings(BaseModel):
    preview_limit: int = Field(
        default=50,
        ge=1,
        le=100,
        title="Preview limit",
        description="Maximum molecule size rendered in previews.",
    )
    enabled: bool = True


class _TestSettings(BaseModel):
    molecule_display: _DisplaySettings = _DisplaySettings()


def _configuration(tmp_path: Path, config_id: str = "testdock") -> PydanticConfiguration:
    package = tmp_path / f"{config_id}-default.toml"
    package.write_text(
        "[molecule_display]\npreview_limit = 50\nenabled = true\n",
        encoding="utf-8",
    )
    return PydanticConfiguration(
        config_id=config_id,
        display_name=config_id.title(),
        model_type=_TestSettings,
        default_path=package,
        global_path=tmp_path / "user" / f"{config_id}.toml",
        project_relative_path=Path(".molsuite/config") / f"{config_id}.toml",
        description="Test configuration provider.",
    )


def test_panel_adds_typed_configuration_tabs_and_saves_global_value(tmp_path):
    app = QApplication.instance() or QApplication([])
    del app
    configuration = _configuration(tmp_path)
    panel = AppSettingsPanel(configurations=[configuration], app_name="Test Dock")
    saved: list[bool] = []
    panel.settings_saved.connect(lambda: saved.append(True))

    try:
        limit = panel.editor("testdock", "molecule_display.preview_limit")
        enabled = panel.editor("testdock", "molecule_display.enabled")
        row = panel.parameter_row("testdock", "molecule_display.preview_limit")

        assert panel.tab_ids() == ("testdock",)
        assert isinstance(limit, QSpinBox)
        assert isinstance(enabled, QCheckBox)
        assert (limit.minimum(), limit.maximum(), limit.value()) == (1, 100, 50)
        assert row.source_label.text() == "DEFAULT"
        assert row.reset_target.currentData() == "default"

        limit.setValue(75)
        panel.save_settings()

        assert configuration.get_value("molecule_display.preview_limit") == 75
        assert configuration.get_source("molecule_display.preview_limit") == "global"
        assert "preview_limit = 75" in configuration.global_path.read_text(encoding="utf-8")
        assert row.source_label.text() == "GLOBAL"
        assert saved == [True]
    finally:
        panel.deleteLater()


def test_panel_resets_project_value_and_accepts_additional_config(tmp_path):
    app = QApplication.instance() or QApplication([])
    del app
    configuration = _configuration(tmp_path)
    configuration.set_value("molecule_display.preview_limit", 60)
    configuration.set_project_root(tmp_path / "project")
    configuration.set_value("molecule_display.preview_limit", 80)
    second = _configuration(tmp_path, "charts")
    panel = AppSettingsPanel(configurations=[configuration])

    try:
        panel.add_config(second)
        assert panel.tab_ids() == ("testdock", "charts")

        row = panel.parameter_row("testdock", "molecule_display.preview_limit")
        assert row.source_label.text() == "PROJECT"
        assert row.reset_target.itemData(0) == "global"
        assert row.reset_target.itemData(1) == "default"

        row.reset_target.setCurrentIndex(0)
        row.reset_button.click()
        assert configuration.get_value("molecule_display.preview_limit") == 60
        assert configuration.get_source("molecule_display.preview_limit") == "global"

        row.reset_target.setCurrentIndex(1)
        row.reset_button.click()
        assert configuration.get_value("molecule_display.preview_limit") == 50
        assert configuration.get_source("molecule_display.preview_limit") == "project"
    finally:
        panel.deleteLater()


class _ToolSettings(BaseModel):
    version: str = "3.1.1"


def test_tree_navigation_search_and_breadcrumb(tmp_path):
    app = QApplication.instance() or QApplication([])
    del app

    class _Deep(BaseModel):
        openbabel: _ToolSettings = _ToolSettings()

    class _Settings(BaseModel):
        molecule_display: _DisplaySettings = _DisplaySettings()
        protonation: _Deep = _Deep()

    package = tmp_path / "deep-default.toml"
    package.write_text(
        "[molecule_display]\npreview_limit = 50\nenabled = true\n"
        "[protonation.openbabel]\nversion = '3.1.1'\n",
        encoding="utf-8",
    )
    configuration = PydanticConfiguration(
        config_id="deep",
        display_name="Deep",
        model_type=_Settings,
        default_path=package,
        global_path=tmp_path / "user" / "deep.toml",
        project_relative_path=Path(".molsuite/config") / "deep.toml",
        description="Nested provider.",
    )
    panel = AppSettingsPanel(configurations=[configuration])
    try:
        # provider ▸ section ▸ subsection, one page each
        assert set(panel._nodes) == {
            "deep",
            "deep/molecule_display",
            "deep/protonation",
            "deep/protonation/openbabel",
        }
        # the root has no scalars of its own -> table of contents page
        assert panel._nodes["deep"].entries == []

        panel.select_node("deep/protonation/openbabel")
        assert "Deep" in panel.breadcrumb.text()
        assert "Openbabel" in panel.breadcrumb.text()
        assert panel.stack.currentWidget() is panel._pages["deep/protonation/openbabel"]

        panel.search_box.setText("preview")
        assert panel._items["deep/molecule_display"].isHidden() is False
        assert panel._items["deep/protonation/openbabel"].isHidden() is True
        row = panel.parameter_row("deep", "molecule_display.preview_limit")
        assert row.name_label.property("searchHit") == "true"

        panel._clear_highlight()  # what a click in the page area does
        assert row.name_label.property("searchHit") == "false"

        panel.search_box.setText("")
        assert panel._items["deep/protonation/openbabel"].isHidden() is False
    finally:
        panel.deleteLater()
