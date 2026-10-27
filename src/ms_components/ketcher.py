"""Draw or edit a small molecule in Ketcher (EPAM's web editor), embedded in a QWebEngineView.

`folder` is an unpacked Ketcher standalone build (the folder holding its index.html); the
application installs it. Ketcher's JS API answers with Promises, which runJavaScript cannot
await: the settled value is parked in a window variable and polled from here.

`run_editor` opens the dialog in its own process (`python -m ms_components.ketcher`): in an
application's process, PySide 6.10 segfaults as soon as the pointer hovers a QWebEngineView
while any Python application-wide event filter is installed. It also keeps Chromium's memory
and GPU use away from the rest of the application (an embedded PyMOL, for one)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QTimer, QUrl, QUrlQuery
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QMessageBox, QVBoxLayout

# Resolves once Ketcher has built `window.ketcher`, some time after the page itself loads.
_READY = "new Promise(r => { const t = setInterval(() => { if (window.ketcher) { clearInterval(t); r(true); } }, 100); })"

# Ketcher 3.18 standalone's URL options configure the editor before it mounts.
_HIDDEN_CONTROLS = (
    "open", "save", "arrows", "reaction-plus", "reaction-mapping-tools", "reaction-map", "reaction-unmap",
    "rgroup", "rgroup-label", "rgroup-fragment", "rgroup-attpoints", "sgroup", "create-monomer",
    "shapes", "shape-ellipse", "shape-rectangle", "shape-line", "text", "images",
    "recognize", "analyse", "miew", "settings", "help", "about", "fullscreen",
)


class KetcherDialog(QDialog):
    """Ketcher opened on `molblock`; after exec() == Accepted, `molblock` holds the drawing.
    `note` is shown under the editor (e.g. what Apply will do)."""

    def __init__(self, folder: Path, molblock: str, *, title: str, note: str = "", parent=None):
        from PySide6.QtWebEngineWidgets import QWebEngineView  # heavy: only when someone edits

        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1100, 750)
        self.molblock = molblock
        self._done: Callable[[dict], None] | None = None
        self._poll = QTimer(self, interval=100)
        # As JSON: a JS object comes back to Python empty, a string intact.
        self._poll.timeout.connect(
            lambda: self._view.page().runJavaScript("JSON.stringify(window.__ketcher ?? null)", 0, self._polled)
        )

        self._view = QWebEngineView(self)
        self._view.loadFinished.connect(self._loaded)
        url = QUrl.fromLocalFile(str(Path(folder) / "index.html"))
        query = QUrlQuery()
        query.addQueryItem("hiddenControls", ",".join(_HIDDEN_CONTROLS))
        query.addQueryItem("disableMacromoleculesEditor", "true")  # initialize without waiting for macromolecules
        url.setQuery(query)
        self._view.load(url)
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel, self)
        self._buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        self._buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(False)
        self._buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self._view, 1)
        if note:
            label = QLabel(note, self)
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addWidget(self._buttons)

    def _call(self, promise: str, done: Callable[[dict], None]) -> None:
        """Evaluate a JS Promise; `done({"ok": value} | {"error": text})` once it settles."""
        self._done = done
        self._view.page().runJavaScript(
            "window.__ketcher = undefined;"
            f"Promise.resolve({promise}).then(v => window.__ketcher = {{ok: v ?? ''}},"
            " e => window.__ketcher = {error: String(e)});"
        )
        self._poll.start()

    def _polled(self, value) -> None:
        result = json.loads(value or "null")
        if not result or self._done is None:
            return
        self._poll.stop()
        done, self._done = self._done, None
        done(result)

    def _loaded(self, ok: bool) -> None:
        if not ok:
            QMessageBox.critical(self, "Ketcher", "Ketcher could not be loaded.")
            return
        self._call(f"{_READY}.then(() => window.ketcher.setMolecule({json.dumps(self.molblock)}))", self._ready)

    def _ready(self, result: dict) -> None:
        if "error" in result:
            QMessageBox.warning(self, "Ketcher", f"Ketcher could not open the molecule:\n{result['error']}")
            return
        self._buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(True)

    def _apply(self) -> None:
        self._buttons.setEnabled(False)
        self._call("window.ketcher.getMolfile()", self._got)

    def _got(self, result: dict) -> None:
        self._buttons.setEnabled(True)
        if "error" in result:
            QMessageBox.critical(self, "Ketcher", f"Could not read the drawing:\n{result['error']}")
            return
        self.molblock = str(result.get("ok") or "")
        self.accept()


def run_editor(
    folder: Path,
    molblock: str,
    title: str,
    *,
    note: str = "",
    theme: str = "auto",
    base_font_pt: float | None = None,
) -> str | None:
    """Open a KetcherDialog in a child process and wait; the drawing after Apply, None on Cancel.
    Blocking: call it off the GUI thread. `theme`/`base_font_pt` go to ms_components.theme."""
    options = {"folder": str(folder), "title": title, "note": note, "theme": theme, "base_font_pt": base_font_pt}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "edited.mol"
        proc = subprocess.run(
            [sys.executable, "-m", __name__, json.dumps(options), str(out)],
            input=molblock, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"The editor stopped (exit code {proc.returncode}):\n{proc.stderr[-2000:]}")
        return out.read_text() if out.exists() else None


def _main(options: str, out: str) -> int:
    """The child process: molblock on stdin; the drawing is written to `out` only on Apply."""
    from ms_components.theme import apply_theme

    opts = json.loads(options)
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)  # QtWebEngine wants it before the app
    app = QApplication(["ms-ketcher"])
    apply_theme(opts.get("theme") or "auto", app, base_font_pt=opts.get("base_font_pt"))
    dialog = KetcherDialog(Path(opts["folder"]), sys.stdin.read(), title=opts["title"], note=opts.get("note", ""))
    if dialog.exec() == QDialog.DialogCode.Accepted:
        Path(out).write_text(dialog.molblock)
    return 0


__all__ = ["KetcherDialog", "run_editor"]

if __name__ == "__main__":
    sys.exit(_main(*sys.argv[1:3]))
