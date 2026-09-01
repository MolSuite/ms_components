from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ms_flow.core.apps import AppManifest
from ms_flow.core.settings.manager import SettingsManager
from ms_components.ms_projects.browser import (
    AvailableToolsTab,
    MolSuiteSettingsPanel,
    ProjectBrowserPanel,
    ProjectItem,
    ProjectTableModel,
    ProjectTreeWidget,
    ProjectBrowserWindow,
)


class _FakeBackend:
    def __init__(self):
        self._manifests = [
            AppManifest(
                app_id="amdockvs",
                scope_id="docking",
                name="AMDock",
                version="0.1.0",
                description="Docking workflows",
            ),
            AppManifest(
                app_id="molsuite_demo",
                scope_id="demo",
                name="Demo",
                version="0.1.0",
                description="General demo workflows",
            ),
        ]
        now = datetime.now()
        self._projects = [
            SimpleNamespace(
                id="p1",
                name="Docking One",
                description="",
                path="/tmp/p1",
                updated_at=now,
                favorite=False,
                app_id="amdockvs",
                tags="alpha,beta",
                scope="docking",
            ),
            SimpleNamespace(
                id="p2",
                name="Docking Two",
                description="",
                path="/tmp/p2",
                updated_at=now,
                favorite=True,
                app_id="amdockvs",
                tags="",
                scope="docking",
            ),
            SimpleNamespace(
                id="p3",
                name="Demo Project",
                description="",
                path="/tmp/p3",
                updated_at=now,
                favorite=False,
                app_id="molsuite_demo",
                tags="demo",
                scope="demo",
            ),
        ]
        self.catalog = SimpleNamespace(settings_manager=None)

    def list_projects(self, page: int = 1, items_per_page: int = 20):
        start = max(0, (page - 1) * items_per_page)
        stop = start + items_per_page
        return list(self._projects[start:stop])

    def get_total_projects(self) -> int:
        return len(self._projects)

    def set_sort_mode(self, sort_mode: str):
        del sort_mode

    def set_filter_mode(self, filter_mode: str):
        del filter_mode

    def set_search(self, field: str, query: str):
        del field, query

    def get_project(self, project_id):
        for project in self._projects:
            if project.id == project_id:
                return project
        raise KeyError(project_id)

    @staticmethod
    def parse_tags(raw_tags: str | None) -> list[str]:
        return [item.strip() for item in str(raw_tags or "").split(",") if item.strip()]

    def get_app_manifest(self, app_id: str):
        for manifest in self._manifests:
            if manifest.app_id == app_id:
                return manifest
        return None

    def list_apps(self):
        return list(self._manifests)

    def create_project(self, **kwargs):
        return SimpleNamespace(id="created")

    def update_project(self, **kwargs):
        del kwargs

    def toggle_favorite(self, project_ids):
        del project_ids

    def delete_projects(self, project_ids, delete_files: bool = True):
        del project_ids, delete_files

    def launch_project(self, project_id):
        del project_id

        class _Proc:
            @staticmethod
            def poll():
                return None

        return _Proc()

    def shutdown(self):
        return None


def _patch_fake_home(monkeypatch, fake_home: Path):
    monkeypatch.setattr("ms_flow.core.settings.manager.Path.home", lambda: fake_home)
    monkeypatch.setattr("ms_flow.core.settings.models.Path.home", lambda: fake_home)


def _release_info_for_tests(app_id: str):
    if app_id == "amdockvs":
        return {
            "latest_version": "0.2.0",
            "headline": "Docking summaries and monitor flow",
            "status": "Update available",
            "summary": "A new build is available with a tighter project monitor flow and better docking result summaries.",
            "notes": [
                "New Jobs page handoff from the compact dock monitor.",
                "Improved docking hit summaries grouped by receptor.",
                "Safer project resource resolution for domain apps.",
            ],
        }
    return {
        "latest_version": "",
        "headline": "No release information",
        "status": "Up to date",
        "summary": "This tool does not expose update metadata in the current workspace.",
        "notes": ["No release notes available."],
    }


def test_project_browser_panel_filters_projects_by_selected_tool():
    app = QApplication.instance() or QApplication([])
    del app
    backend = _FakeBackend()

    panel = ProjectBrowserPanel(
        app_id=None,
        header_title="Projects",
        hint_text="Browse projects",
        _backend=backend,
    )
    try:
        assert panel.get_total_projects() == 3

        panel.set_tool_scope("amdockvs")
        assert panel.get_total_projects() == 2
        assert panel.hint_label.text() == (
            "Browse and open projects for 'AMDock'. "
            "Project creation will be scoped to this tool."
        )
        names = [item.name for item in panel.get_projects_paginated(1, 10)]
        assert names == ["Docking One", "Docking Two"]

        panel.set_tool_scope("molsuite_demo")
        assert panel.get_total_projects() == 1
        assert panel.get_projects_paginated(1, 10)[0].name == "Demo Project"
    finally:
        panel.deleteLater()


def test_project_table_model_separates_id_from_description_and_exposes_tooltips():
    model = ProjectTableModel()
    model.load(
        [
            ProjectItem(
                id="proj-001",
                name="Docking One",
                description="Long project description for tooltip and wrapped rendering.",
                path="/tmp/project/with/a/very/long/path",
                last_modified="09/04/2026 12:00",
                app_id="amdockvs",
                tags=["alpha", "beta"],
            )
        ]
    )

    assert model.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "Description"
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Docking One"
    assert model.data(model.index(0, 1), Qt.DisplayRole) == "Long project description for tooltip and wrapped rendering."
    assert "ID: proj-001" in model.data(model.index(0, 0), Qt.ToolTipRole)
    assert model.data(model.index(0, 1), Qt.ToolTipRole) == "Long project description for tooltip and wrapped rendering."


def test_project_tree_widget_rebalances_columns_on_resize():
    app = QApplication.instance() or QApplication([])
    del app

    widget = ProjectTreeWidget()
    try:
        widget.load(
            [
                ProjectItem(
                    id="proj-001",
                    name="Docking One",
                    description="Long project description for wrapped rendering.",
                    path="/tmp/project/with/a/reasonably/long/path",
                    last_modified="09/04/2026 12:00",
                    app_id="amdockvs",
                )
            ]
        )
        widget.resize(1400, 600)
        widget.show()
        QApplication.processEvents()

        header = widget.view.header()
        assert header.sectionSize(0) >= 300
        assert header.sectionSize(1) >= 240
        assert header.sectionSize(2) >= 118
        assert header.sectionSize(3) >= 100
        assert header.sectionSize(4) <= 38
        assert header.sectionSize(5) <= 38
    finally:
        widget.close()


def test_project_browser_window_disables_other_tools_for_scoped_app(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    del app
    _patch_fake_home(monkeypatch, tmp_path)
    backend = _FakeBackend()
    backend.catalog.settings_manager = SettingsManager()

    window = ProjectBrowserWindow(
        app_id="amdockvs",
        close_on_launch=False,
        _backend=backend,
    )
    try:
        tree = window.tools_tab.tools_tree
        demo_item = window.tools_tab._tool_items["molsuite_demo"]
        scoped_item = window.tools_tab._tool_items["amdockvs"]

        assert scoped_item.isDisabled() is False
        assert demo_item.isDisabled() is True
        assert tree.currentItem() is scoped_item
        assert window.panel.get_total_projects() == 2
        assert window.panel.scope_badge.text() == "AMDock"
    finally:
        window.close()


def test_project_browser_window_marks_all_tools_as_normal_selectable_item(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    del app
    _patch_fake_home(monkeypatch, tmp_path)
    backend = _FakeBackend()
    backend.catalog.settings_manager = SettingsManager()

    window = ProjectBrowserWindow(
        app_id=None,
        close_on_launch=False,
        _backend=backend,
    )
    try:
        tree = window.tools_tab.tools_tree
        all_item = window.tools_tab._tool_items[None]

        assert tree.currentItem() is all_item
        assert all_item.isDisabled() is False
        assert all_item.data(0, Qt.UserRole + 2) == 3
        assert window.panel.scope_badge.text() == "All tools"
        assert window.panel.get_total_projects() == 3
    finally:
        window.close()


def test_project_browser_window_shows_update_indicators(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    del app
    _patch_fake_home(monkeypatch, tmp_path)
    monkeypatch.setattr("ms_components.ms_projects.browser._tool_update_demo", _release_info_for_tests)
    backend = _FakeBackend()
    backend.catalog.settings_manager = SettingsManager()

    window = ProjectBrowserWindow(
        app_id=None,
        close_on_launch=False,
        _backend=backend,
    )
    try:
        amdock_item = window.tools_tab._tool_items["amdockvs"]
        demo_item = window.tools_tab._tool_items["molsuite_demo"]
        all_item = window.tools_tab._tool_items[None]

        assert amdock_item.data(0, Qt.UserRole + 3) is True
        assert demo_item.data(0, Qt.UserRole + 3) is False
        assert all_item.data(0, Qt.UserRole + 3) is True
        assert window.tabs.tabText(1) == "Available Tools (1)"
    finally:
        window.close()


def test_molsuite_settings_panel_updates_global_settings(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    del app
    _patch_fake_home(monkeypatch, tmp_path)

    manager = SettingsManager()
    panel = MolSuiteSettingsPanel(settings_manager=manager)
    try:
        panel.poll_interval_spin.setValue(1.75)
        panel.general_log_level_combo.setCurrentText("DEBUG")
        panel.executor_log_level_combo.setCurrentText("ERROR")
        panel.cpus_spin.setValue(3)
        panel.max_processes_spin.setValue(2)
        panel.save_settings()

        assert manager.settings.general.poll_interval == 1.75
        assert manager.settings.general.log_level == "DEBUG"
        assert manager.settings.logging.executor_level == "ERROR"
        assert manager.settings.resources.local.cpus == 3
        assert manager.settings.resources.local.max_processes == 2
    finally:
        panel.deleteLater()


def test_available_tools_tab_shows_demo_update_notes_for_selected_tool(monkeypatch):
    app = QApplication.instance() or QApplication([])
    del app
    monkeypatch.setattr("ms_components.ms_projects.browser._tool_update_demo", _release_info_for_tests)
    backend = _FakeBackend()

    panel = AvailableToolsTab(backend=backend, current_app_id=None)
    try:
        panel.tools_table.selectRow(0)
        panel._sync_detail_from_selection()

        assert panel.detail_title.text() == "AMDock"
        assert panel.detail_status.text() == "Update available"
        assert "0.1.0 installed" in panel.detail_versions.text()
        assert "0.2.0 latest" in panel.detail_versions.text()
        assert "Docking summaries and monitor flow" in panel.detail_notes.toPlainText()
    finally:
        panel.deleteLater()
