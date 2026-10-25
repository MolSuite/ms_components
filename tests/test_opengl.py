from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pydantic.fields  # noqa: F401 - load before PySide6's feature importer
import pytest
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from ms_components import opengl


def _context(*, es=False, version=(4, 6), profile=QSurfaceFormat.CompatibilityProfile, valid=True):
    fmt = QSurfaceFormat()
    fmt.setVersion(*version)
    fmt.setProfile(profile)
    return SimpleNamespace(isValid=lambda: valid, isOpenGLES=lambda: es, format=lambda: fmt)


def test_pymol_format_preserves_stereo_and_samples_but_requests_desktop_gl():
    base = QSurfaceFormat()
    base.setRenderableType(QSurfaceFormat.OpenGLES)
    base.setVersion(3, 3)
    base.setProfile(QSurfaceFormat.CoreProfile)
    base.setSamples(4)
    base.setStereo(True)
    fmt = opengl.pymol_surface_format(base)
    assert fmt.renderableType() == QSurfaceFormat.OpenGL
    assert fmt.version() == (2, 1)
    assert fmt.profile() == QSurfaceFormat.NoProfile
    assert (fmt.depthBufferSize(), fmt.stencilBufferSize()) == (24, 8)
    assert fmt.samples() == 4 and fmt.stereo()
    assert base.renderableType() == QSurfaceFormat.OpenGLES


@pytest.mark.parametrize("context, expected", [
    (None, "valid OpenGL"),
    (_context(valid=False), "valid OpenGL"),
    (_context(es=True), "OpenGL ES"),
    (_context(version=(2, 0)), "2.1"),
    (_context(profile=QSurfaceFormat.CoreProfile), "OpenGL Core"),
    (_context(profile=QSurfaceFormat.NoProfile), "OpenGL Core"),
    (_context(version=(2, 1), profile=QSurfaceFormat.NoProfile), None),
    (_context(), None),
])
def test_checks_actual_context(context, expected):
    error = opengl.pymol_context_error(context)
    assert error is None if expected is None else expected in error


@pytest.fixture
def startup(monkeypatch):
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    monkeypatch.setattr(opengl, "configure_pymol_opengl", lambda: None)
    monkeypatch.setattr(opengl.sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    calls = []

    def probe(platform=None):
        calls.append(platform)
        return platform == "xcb", "test context"

    monkeypatch.setattr(opengl, "_probe", probe)
    return calls


def test_keeps_working_native_backend(monkeypatch, startup):
    monkeypatch.setattr(opengl, "_probe", lambda platform=None: (True, "wayland: compatible"))
    opengl.prepare_pymol_opengl()
    assert "QT_QPA_PLATFORM" not in opengl.os.environ


def test_uses_x11_only_after_native_failure_and_successful_x11_probe(startup):
    opengl.prepare_pymol_opengl()
    assert startup == [None, "xcb"]
    assert opengl.os.environ["QT_QPA_PLATFORM"] == "xcb"


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_other_operating_systems_never_try_xcb(monkeypatch, startup, platform):
    monkeypatch.setattr(opengl.sys, "platform", platform)
    with pytest.raises(RuntimeError, match="No compatible OpenGL"):
        opengl.prepare_pymol_opengl()
    assert startup == [None]
    assert "QT_QPA_PLATFORM" not in opengl.os.environ


def test_explicit_qt_platform_is_respected(monkeypatch, startup):
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
    with pytest.raises(RuntimeError, match="No compatible OpenGL"):
        opengl.prepare_pymol_opengl()
    assert startup == [None]
    assert opengl.os.environ["QT_QPA_PLATFORM"] == "wayland"


def test_no_x11_fallback_without_a_display(monkeypatch, startup):
    monkeypatch.delenv("DISPLAY")
    with pytest.raises(RuntimeError, match="No compatible OpenGL"):
        opengl.prepare_pymol_opengl()
    assert startup == [None]


def test_failed_x11_probe_does_not_change_platform(monkeypatch, startup):
    monkeypatch.setattr(opengl, "_probe", lambda platform=None: (False, "driver failed"))
    with pytest.raises(RuntimeError, match="X11 fallback: driver failed"):
        opengl.prepare_pymol_opengl()
    assert "QT_QPA_PLATFORM" not in opengl.os.environ


@pytest.mark.parametrize("returncode", [-11, 1])
def test_probe_contains_driver_failures(monkeypatch, returncode):
    monkeypatch.setattr(opengl.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], returncode, "", "driver/plugin failure",
    ))
    supported, detail = opengl._probe()
    assert not supported
    assert str(returncode) in detail and "driver/plugin failure" in detail


def test_probe_has_a_timeout(monkeypatch):
    def run(*args, **kwargs):
        assert kwargs["timeout"] == 10
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(opengl.subprocess, "run", run)
    assert opengl._probe()[0] is False


def test_cannot_change_backend_after_qapplication_exists(monkeypatch):
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: object()))
    with pytest.raises(RuntimeError, match="before QApplication"):
        opengl.prepare_pymol_opengl()


def test_viewer_blocks_pymol_drawing_on_es_and_recovers_on_a_compatible_context(monkeypatch):
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
    from shiboken6 import delete
    from ms_components.ms_pymol.widget import PyMOLGLWidget, _PymolGLWidget

    app = QApplication.instance() or QApplication(["pymol-context-test"])
    # Construct only the Qt widget: these callbacks must reject ES before entering PyMOL.
    widget = _PymolGLWidget.__new__(_PymolGLWidget)
    QOpenGLWidget.__init__(widget)
    widget._opengl_error = None
    widget._opengl_error_label = None
    callbacks = []
    widget.before_render.connect(lambda: callbacks.append("before_render"))
    for name in ("initializeGL", "paintGL", "resizeGL"):
        monkeypatch.setattr(PyMOLGLWidget, name, lambda *args, name=name: callbacks.append(name))
    monkeypatch.setattr(_PymolGLWidget, "context", lambda self: _context(es=True))
    try:
        widget.initializeGL()
        widget.resizeGL(100, 100)
        widget.paintGL()
        assert not callbacks
        assert "OpenGL ES" in widget._opengl_error_label.text()

        monkeypatch.setattr(_PymolGLWidget, "context", lambda self: _context())
        widget.initializeGL()
        widget.resizeGL(100, 100)
        widget.paintGL()
        assert callbacks == ["initializeGL", "resizeGL", "before_render", "paintGL"]
        assert widget._opengl_error_label.isHidden()
    finally:
        delete(widget)
