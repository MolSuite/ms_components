from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ms_flow.core.project.catalog import ProjectCatalogBackend
from ms_components.ms_projects.browser import ProjectFormDialog, ProjectItem, ProjectTreeWidget

_PROJECT_MENU_COLORS = [
    "#4e95ff",
    "#a259ff",
    "#ff6b6b",
    "#43d9ad",
    "#ffb347",
    "#f7768e",
    "#9ece6a",
    "#7dcfff",
]


def _project_color(index: int) -> str:
    return _PROJECT_MENU_COLORS[index % len(_PROJECT_MENU_COLORS)]


class ProjectsMenuWidget(QFrame):
    project_requested = Signal(str)
    project_created = Signal(str)

    def __init__(
        self,
        *,
        app_id: str | None = None,
        backend: ProjectCatalogBackend | None = None,
        title: str = "Projects",
        hint_text: str = "Browse and manage projects.",
        allow_create: bool = True,
        open_after_create: bool = False,
        allow_app_selection: bool | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.app_id = (app_id or "").strip() or None
        self.backend = backend or ProjectCatalogBackend(app_id_filter=self.app_id)
        self.title = title
        self.hint_text = hint_text
        self.allow_create = allow_create
        self.open_after_create = open_after_create
        self.allow_app_selection = (
            bool(allow_app_selection) if allow_app_selection is not None else self.app_id is None
        )
        self._app_color_map: dict[str, str] = {}
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        self.setObjectName("ProjectsMenuWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QVBoxLayout()
        top = QHBoxLayout()
        self.title_label = QLabel(self.title, self)
        self.title_label.setStyleSheet("font-size:16px; font-weight:700; color: palette(text);")
        top.addWidget(self.title_label)
        top.addStretch(1)
        self.scope_badge = QLabel("", self)
        self.scope_badge.setStyleSheet(
            "padding:4px 10px; border-radius:999px; color: palette(highlighted-text);"
            "background: palette(highlight); border:1px solid palette(highlight);"
        )
        top.addWidget(self.scope_badge)
        header.addLayout(top)

        self.hint_label = QLabel(self.hint_text, self)
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: palette(placeholder-text); font-size:12px;")
        header.addWidget(self.hint_label)
        layout.addLayout(header)

        actions = QHBoxLayout()
        self.new_button = QPushButton("New project", self)
        self.new_button.clicked.connect(self.on_create_project)
        self.new_button.setEnabled(self.allow_create)
        actions.addWidget(self.new_button)
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.refresh)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.project_tree = ProjectTreeWidget(self)
        self.project_tree.project_opened.connect(self._on_project_opened)
        self.project_tree.favorite_toggled.connect(self._on_favorite_toggled)
        self.project_tree.edit_requested.connect(self._on_edit)
        self.project_tree.delete_requested.connect(self._on_delete)
        self.project_tree.export_requested.connect(
            lambda projects: QMessageBox.information(
                self,
                "Export",
                f"Export is not implemented yet. Selected: {len(projects)}",
            )
        )
        layout.addWidget(self.project_tree, 1)

    def _build_color_map(self) -> None:
        self._app_color_map = {manifest.app_id: _project_color(i) for i, manifest in enumerate(self.backend.list_apps())}

    def _color_for_app(self, app_id: str) -> str:
        return self._app_color_map.get(app_id, "#4e95ff")

    def _manifest_name(self, app_id: str) -> str:
        manifest = self.backend.get_app_manifest(app_id)
        return manifest.name if manifest else (app_id or "Unknown")

    def _load_all_from_db(self) -> list[ProjectItem]:
        total = max(1, int(self.backend.get_total_projects()))
        return [
            ProjectItem(
                id=str(project.id),
                name=project.name,
                description=project.description or "",
                path=str(project.path),
                last_modified=project.updated_at.strftime("%d/%m/%Y %H:%M"),
                app_id=(getattr(project, "app_id", "") or "").strip(),
                favorite=bool(project.favorite),
                language=self._manifest_name(project.app_id),
                color=self._color_for_app((getattr(project, "app_id", "") or "").strip()),
                tags=self.backend.parse_tags(project.tags),
            )
            for project in self.backend.list_projects(1, total)
        ]

    def refresh(self) -> None:
        self._build_color_map()
        self.project_tree.load(self._load_all_from_db())
        self.project_tree.set_scope(self.app_id)
        self.scope_badge.setText(self._manifest_name(self.app_id) if self.app_id else "All apps")

    def get_total_projects(self) -> int:
        return len(self.project_tree.model.all_visible())

    def on_create_project(self) -> None:
        apps = self._available_apps_for_dialog()
        if not apps:
            QMessageBox.critical(self, "New project", "No registered apps are available.")
            return
        dialog = ProjectFormDialog(
            apps=apps,
            mode="create",
            initial_data={
                "path": str(Path.home() / "molsuite_projects"),
                "app_id": self.app_id or apps[0].app_id,
            },
            allow_app_selection=self.allow_app_selection,
            parent=self,
        )
        if dialog.exec() != ProjectFormDialog.Accepted:
            return
        data = dialog.get_data()
        try:
            folder = data["path"].expanduser().resolve()
            name = data["name"].strip()
            if folder.name != name:
                folder = folder / name
            context = self.backend.create_project(
                name=name,
                folder=folder,
                description=data["description"],
                tags=data["tags"],
                app_id=data["app_id"],
            )
        except Exception as exc:
            QMessageBox.critical(self, "New project", f"Could not create project:\n{exc}")
            return
        self.refresh()
        self.project_created.emit(str(context.id))
        if self.open_after_create:
            self.project_requested.emit(str(context.id))

    def _available_apps_for_dialog(self) -> list:
        apps = self.backend.list_apps()
        if self.app_id:
            return [app for app in apps if app.app_id == self.app_id]
        return apps

    def _on_project_opened(self, project: ProjectItem) -> None:
        self.project_requested.emit(str(project.id))

    def _on_favorite_toggled(self, project: ProjectItem) -> None:
        self.backend.toggle_favorite([project.id])
        self.refresh()

    def _on_edit(self, project: ProjectItem) -> None:
        raw = self.backend.get_project(project.id)
        dialog = ProjectFormDialog(
            apps=self._available_apps_for_dialog(),
            mode="edit",
            initial_data={
                "name": raw.name,
                "path": str(raw.path),
                "description": raw.description,
                "tags": raw.tags,
                "app_id": raw.app_id,
            },
            allow_app_selection=False,
            parent=self,
        )
        if dialog.exec() != ProjectFormDialog.Accepted:
            return
        data = dialog.get_data()
        manifest = self.backend.get_app_manifest(data["app_id"])
        try:
            self.backend.update_project(
                project_id=raw.id,
                name=data["name"],
                folder=data["path"],
                description=data["description"],
                tags=data["tags"],
                app_id=data["app_id"],
                scope=manifest.scope_id if manifest else getattr(raw, "scope", "full"),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Edit project", f"Could not update project:\n{exc}")
            return
        self.refresh()

    def _on_delete(self, projects: list[ProjectItem]) -> None:
        if not projects:
            return
        reply = QMessageBox.question(
            self,
            "Delete projects",
            f"{len(projects)} project(s) will be deleted with their folders. This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        progress = QProgressDialog("Deleting projects...", None, 0, len(projects), self)
        progress.setWindowTitle("Delete projects")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setCancelButton(None)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        errors: list[tuple[str, Exception]] = []
        for index, project in enumerate(projects, start=1):
            progress.setLabelText(f"Deleting {index} of {len(projects)}: {project.name}")
            QApplication.processEvents()
            try:
                self.backend.delete_projects([project.id], delete_files=True)
            except Exception as exc:
                errors.append((project.name, exc))
            progress.setValue(index)
            QApplication.processEvents()

        progress.close()
        self.refresh()

        if errors:
            detail = "\n".join(f"- {name}: {exc}" for name, exc in errors)
            QMessageBox.critical(
                self,
                "Delete projects",
                f"Could not delete {len(errors)} of {len(projects)} project(s):\n{detail}",
            )
