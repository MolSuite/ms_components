from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QDialog, QMessageBox

from ms_flow.core.apps import AppManifest
from ms_components.ms_projects import ProjectsMenuWidget
from ms_components.ms_projects import ProjectFormDialog


def test_folder_selection_emits_only_when_confirmed_including_the_same_folder(monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    backend = _FakeBackend()
    form = ProjectFormDialog(apps=backend.list_apps(), mode="create",
                             initial_data={"path": str(tmp_path)})
    selected, names = [], []
    form.path_selected.connect(selected.append)
    form.name_committed.connect(names.append)
    try:
        form.name_input.setText("Practice")
        form.name_input.editingFinished.emit()
        assert names == ["Practice"]
        monkeypatch.setattr("ms_components.ms_projects.browser.QFileDialog.getExistingDirectory", lambda *a: "")
        form.browse_button.click()
        assert selected == [] and form.path_input.text() == str(tmp_path)
        monkeypatch.setattr("ms_components.ms_projects.browser.QFileDialog.getExistingDirectory",
                            lambda *a: str(tmp_path))
        form.browse_button.click()
        assert selected == [str(tmp_path)]
        assert form.path_row.isAncestorOf(form.browse_button)
        assert form.save_button.text()
    finally:
        form.deleteLater()


def test_project_form_is_announced_before_its_modal_loop_and_cancel_does_not_create(monkeypatch):
    QApplication.instance() or QApplication([])
    widget = ProjectsMenuWidget(app_id="amdockvs", backend=_FakeBackend())
    opened, created = [], []
    widget.project_form_opened.connect(opened.append)
    widget.project_created.connect(created.append)

    def cancel(form):
        assert opened == [form] and form.mode == "create"
        return QDialog.Rejected

    monkeypatch.setattr(ProjectFormDialog, "exec", cancel)
    try:
        widget.on_create_project()
        assert len(opened) == 1 and created == []
    finally:
        widget.deleteLater()


class _FakeBackend:
    def __init__(self):
        now = datetime.now()
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
            ),
        ]

    def list_projects(self, page: int = 1, items_per_page: int = 20):
        start = max(0, (page - 1) * items_per_page)
        stop = start + items_per_page
        return list(self._projects[start:stop])

    def get_total_projects(self) -> int:
        return len(self._projects)

    def get_app_manifest(self, app_id: str):
        for manifest in self._manifests:
            if manifest.app_id == app_id:
                return manifest
        return None

    def list_apps(self):
        return list(self._manifests)

    @staticmethod
    def parse_tags(raw_tags: str | None) -> list[str]:
        return [item.strip() for item in str(raw_tags or "").split(",") if item.strip()]

    def create_project(self, **kwargs):
        return SimpleNamespace(id="created")

    def update_project(self, **kwargs):
        del kwargs

    def toggle_favorite(self, project_ids):
        del project_ids

    def delete_projects(self, project_ids, delete_files: bool = True):
        del project_ids, delete_files

    def shutdown(self):
        return None


def test_projects_menu_widget_scopes_to_selected_app():
    app = QApplication.instance() or QApplication([])
    del app

    widget = ProjectsMenuWidget(
        app_id="amdockvs",
        backend=_FakeBackend(),
        title="AMDock Projects",
        hint_text="Scoped projects.",
    )
    try:
        assert widget.get_total_projects() == 2
        assert widget.scope_badge.text() == "AMDock"
        assert widget.new_button.text() == "New project"
        assert widget.project_tree._search.placeholderText() == "Search..."
        assert widget.project_tree._filter_labels == {
            "all": "All",
            "favorites": "Favorites",
            "has_description": "Has description",
            "has_tags": "Has tags",
        }
    finally:
        widget.deleteLater()


def test_projects_menu_widget_opens_created_project_when_enabled(monkeypatch):
    app = QApplication.instance() or QApplication([])
    del app

    class _FakeDialog:
        Accepted = QDialog.Accepted

        def __init__(self, *args, **kwargs):
            del args, kwargs

        def exec(self):
            return QDialog.Accepted

        @staticmethod
        def get_data():
            return {
                "name": "created-project",
                "path": Path("/tmp/created-project"),
                "description": "demo",
                "tags": ["alpha"],
                "app_id": "amdockvs",
            }

    monkeypatch.setattr("ms_components.ms_projects.widget.ProjectFormDialog", _FakeDialog)
    backend = _FakeBackend()
    created: list[str] = []
    opened: list[str] = []

    widget = ProjectsMenuWidget(
        app_id="amdockvs",
        backend=backend,
        open_after_create=True,
    )
    try:
        widget.project_created.connect(created.append)
        widget.project_requested.connect(opened.append)
        widget.on_create_project()

        assert created == ["created"]
        assert opened == ["created"]
    finally:
        widget.deleteLater()


def test_the_host_open_project_is_handed_back_not_deleted(monkeypatch):
    QApplication.instance() or QApplication([])
    backend = _FakeBackend()
    deleted, handed = [], []
    backend.delete_projects = lambda ids, delete_files=True: deleted.extend(ids)
    monkeypatch.setattr("ms_components.ms_projects.widget.QMessageBox.question",
                        lambda *a, **k: QMessageBox.Yes)
    widget = ProjectsMenuWidget(app_id="amdockvs", backend=backend)
    widget.active_project_id = "p1"
    widget.active_project_delete_requested.connect(handed.append)
    try:
        items = [SimpleNamespace(id="p1", name="Docking One"), SimpleNamespace(id="p2", name="Docking Two")]
        widget._on_delete(items)
        assert handed == ["p1"] and deleted == ["p2"]
    finally:
        widget.deleteLater()
