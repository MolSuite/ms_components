from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ms_components.ms_projects.browser import ProjectBrowserWindow


def main(argv: list[str] | None = None) -> int:
    app = QApplication(list(sys.argv[1:] if argv is None else argv))
    window = ProjectBrowserWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
