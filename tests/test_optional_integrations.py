"""Optional integrations must not be imported by unrelated widgets."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def _without_integrations(code: str) -> None:
    prelude = """
import importlib.abc
import sys

class WithoutIntegrations(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'ms_flow', 'ms_env', 'sqlmodel', 'sqlalchemy', 'pymol', 'pmg_qt', 'pydantic'}:
            raise ModuleNotFoundError('Optional integration blocked: ' + fullname, name=fullname)

sys.meta_path.insert(0, WithoutIntegrations())
"""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-c", prelude + textwrap.dedent(code)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_base_widgets_and_supplied_project_backend_need_no_integrations():
    _without_integrations("""
        from PySide6.QtWidgets import QApplication
        from ms_components.theme import apply_theme
        from ms_components.tool_panel import ToolPanel
        from ms_components.ms_projects import ProjectsMenuWidget, ProjectBrowserPanel
        from ms_components.ms_settings import AppSettingsPanel
        from ms_components.ms_executors import ExecutorsPanel
        from ms_components.ms_tutorial import TutorialController

        class Backend:
            def __bool__(self):
                return False
            def list_apps(self):
                return []
            def get_total_projects(self):
                return 0
            def list_projects(self, *args):
                return []

        app = QApplication([])
        backend = Backend()
        menu = ProjectsMenuWidget(backend=backend)
        panel = ProjectBrowserPanel(header_title='Projects', hint_text='', _backend=backend)
        settings = AppSettingsPanel()
        assert menu.backend is backend and panel.backend is backend
        assert menu.get_total_projects() == panel.get_total_projects() == 0
        assert not any(name == 'ms_flow' or name.startswith('ms_flow.') for name in sys.modules)
        menu.close()
        panel.close()
        settings.close()
    """)


def test_missing_default_backend_gives_installation_command():
    _without_integrations("""
        from ms_components.ms_projects.backend import create_catalog_backend
        try:
            create_catalog_backend()
        except ModuleNotFoundError as error:
            assert error.name == 'ms_flow'
            assert 'ms_components[projects]' in str(error)
        else:
            raise AssertionError('The default backend requires the projects extra')
    """)


def test_standalone_app_reports_missing_backend():
    _without_integrations("""
        from ms_components.ms_projects import app
        messages = []
        app.QMessageBox.critical = lambda *args: messages.append(args)
        assert app.main([]) == 1
        assert len(messages) == 1
        assert 'ms_components[projects]' in messages[0][2]
    """)


def test_default_catalog_creates_database_on_first_use(tmp_path, monkeypatch):
    from ms_flow.core.apps import AppRegistry

    from ms_components.ms_projects.backend import create_catalog_backend

    monkeypatch.setenv("MOLSUITE_HOME", str(tmp_path))
    monkeypatch.setattr(AppRegistry, "discover_prefixed_apps", lambda *_args: None)
    monkeypatch.setattr(AppRegistry, "discover_workspace_apps", lambda *_args: None)
    backend = create_catalog_backend()
    try:
        assert (tmp_path / "projects.db").is_file()
        assert backend.get_total_projects() == 0
    finally:
        backend.shutdown()
