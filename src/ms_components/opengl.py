"""Desktop OpenGL setup and an isolated compatibility check for embedded PyMOL."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QOpenGLContext, QSurfaceFormat

_log = logging.getLogger(__name__)


def pymol_surface_format(base: QSurfaceFormat | None = None) -> QSurfaceFormat:
    """Keep stereo/multisampling while requesting the desktop API used by PyMOL's shaders."""
    fmt = QSurfaceFormat(base) if base is not None else QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setVersion(2, 1)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.NoProfile)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    return fmt


def configure_pymol_opengl() -> None:
    """Call before QApplication so Qt's shared contexts use the same desktop API."""
    QSurfaceFormat.setDefaultFormat(pymol_surface_format())
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)


def pymol_context_error(context: QOpenGLContext | None) -> str | None:
    """Check the actual context, since drivers can ignore the requested format."""
    if context is None or not context.isValid():
        return "Qt could not create a valid OpenGL context."
    fmt = context.format()
    if context.isOpenGLES():
        return "PyMOL requires desktop OpenGL; Qt provided OpenGL ES."
    if fmt.version() < (2, 1):
        return "PyMOL requires an OpenGL 2.1 or newer compatibility context."
    if fmt.version() >= (3, 2) and fmt.profile() != QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile:
        return "PyMOL's legacy shaders require a compatibility context, not OpenGL Core."
    return None


def _probe(platform: str | None = None) -> tuple[bool, str]:
    env = os.environ.copy()
    if platform is not None:
        env["QT_QPA_PLATFORM"] = platform
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    detail = result.stdout.strip()
    if result.returncode:
        detail = f"OpenGL probe exited with {result.returncode}: {detail}\n{result.stderr[-2000:]}".strip()
    return result.returncode == 0, detail


def prepare_pymol_opengl() -> None:
    """Verify the native backend first; select X11 only after a successful fallback probe."""
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is not None:
        raise RuntimeError("PyMOL OpenGL must be prepared before QApplication is created.")
    configure_pymol_opengl()
    supported, detail = _probe()
    print(f"PyMOL OpenGL: {detail}", file=sys.stderr)
    if supported:
        return
    if sys.platform.startswith("linux") and os.environ.get("DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
        supported, fallback_detail = _probe("xcb")
        if supported:
            os.environ["QT_QPA_PLATFORM"] = "xcb"
            _log.warning("Native OpenGL check failed; using X11 for PyMOL: %s", fallback_detail)
            return
        detail += f"\nX11 fallback: {fallback_detail}"
    raise RuntimeError(f"No compatible OpenGL context is available for PyMOL.\n{detail}")


def _main() -> int:
    # The driver or Qt platform plugin may abort; only this short-lived process is at risk.
    from PySide6.QtGui import QOffscreenSurface
    from PySide6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram
    from PySide6.QtWidgets import QApplication

    configure_pymol_opengl()
    app = QApplication(["pymol-opengl-check"])
    context = QOpenGLContext()
    context.setFormat(QSurfaceFormat.defaultFormat())
    context.setShareContext(QOpenGLContext.globalShareContext())
    if not context.create():
        print(f"{app.platformName()}: context creation failed", flush=True)
        return 1
    surface = QOffscreenSurface()
    surface.setFormat(context.format())
    surface.create()
    if not surface.isValid() or not context.makeCurrent(surface):
        print(f"{app.platformName()}: could not activate the OpenGL context", flush=True)
        return 1
    try:
        error = pymol_context_error(context)
        if error is None:
            # Exercise the legacy GLSL built-ins rejected in an ES or core-only context.
            shader = QOpenGLShaderProgram()
            vertex_ok = shader.addShaderFromSourceCode(QOpenGLShader.Vertex, """
                #version 120
                void main() {
                    gl_Position = gl_Vertex;
                    gl_FrontColor = gl_Color;
                    gl_BackColor = gl_Color;
                }
            """)
            fragment_ok = shader.addShaderFromSourceCode(QOpenGLShader.Fragment, """
                #version 120
                void main() { gl_FragColor = gl_Color; }
            """)
            if not vertex_ok or not fragment_ok or not shader.link():
                error = f"PyMOL's required legacy GLSL features are unavailable: {shader.log()}"
            shader.removeAllShaders()
        fmt = context.format()
        functions = context.functions()
        print(
            f"{app.platformName()}: OpenGL {fmt.majorVersion()}.{fmt.minorVersion()} "
            f"{fmt.profile().name}; {functions.glGetString(0x1F00)}; "
            f"{functions.glGetString(0x1F01)}; {error or 'compatible'}",
            flush=True,
        )
        return int(error is not None)
    finally:
        context.doneCurrent()


if __name__ == "__main__":
    raise SystemExit(_main())
