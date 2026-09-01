from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ms_components.ms_monitor.formatting import format_progress, format_status
from ms_components.ms_monitor.models import ChunkMonitorState
from ms_components.ms_monitor.palette import P


class ChunkPanel(QFrame):
    MAX_VISIBLE_ROWS = 100

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chunkPanel")
        self.setStyleSheet(
            f"""
            QFrame#chunkPanel {{
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 10px;
            }}
            QTreeWidget {{
                background: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 8px;
                color: palette(text);
            }}
            QHeaderView::section {{
                background: palette(base);
                color: palette(placeholder-text);
                border: none;
                padding: 6px;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._title = QLabel("Live Chunks", self)
        self._tree = QTreeWidget(self)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(False)
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Chunk", "Job", "Status", "Progress"])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)

        layout.addWidget(self._title)
        layout.addWidget(self._tree, 1)

    def is_user_interacting(self) -> bool:
        if self._tree.hasFocus():
            return True
        return (
            self._tree.verticalScrollBar().isSliderDown()
            or self._tree.horizontalScrollBar().isSliderDown()
        )

    def set_chunks(self, chunks: list[ChunkMonitorState], *, job_id: str | None = None) -> None:
        relevant = [chunk for chunk in chunks if job_id is None or chunk.job_id == job_id]
        visible = relevant[: self.MAX_VISIBLE_ROWS]
        if job_id:
            self._title.setText(
                f"Job Chunks ({len(visible)}/{len(relevant)}) for {job_id[:8]}"
            )
        else:
            self._title.setText(f"Live Chunks ({len(visible)}/{len(relevant)})")
        self._tree.clear()
        for chunk in visible:
            item = QTreeWidgetItem(
                [
                    chunk.short_id,
                    chunk.job_id[:8],
                    format_status(chunk.status),
                    format_progress(chunk.progress),
                ]
            )
            item.setToolTip(0, chunk.chunk_id)
            item.setToolTip(1, chunk.job_id)
            self._tree.addTopLevelItem(item)
