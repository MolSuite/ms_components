from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from ms_components.ms_monitor.formatting import (
    format_chunks,
    format_progress,
    format_queue_wait,
    format_relative_time,
    format_status,
    format_throughput,
)
from ms_components.ms_monitor.models import JobMonitorState


class JobTreeModel(QAbstractTableModel):
    HEADERS = [
        "Job",
        "Status",
        "Executor",
        "Progress",
        "Chunks",
        "Queue",
        "Throughput",
        "Updated",
    ]

    def __init__(self, *, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[JobMonitorState] = []

    def set_jobs(self, jobs: list[JobMonitorState]) -> None:
        new_rows = list(jobs)
        current_ids = [row.job_id for row in self._rows]
        new_ids = [row.job_id for row in new_rows]
        if current_ids == new_ids:
            self._rows = new_rows
            if self._rows:
                top_left = self.index(0, 0)
                bottom_right = self.index(len(self._rows) - 1, len(self.HEADERS) - 1)
                self.dataChanged.emit(top_left, bottom_right)
            return
        self.beginResetModel()
        self._rows = new_rows
        self.endResetModel()

    def clear(self) -> None:
        self.set_jobs([])

    def jobs(self) -> list[JobMonitorState]:
        return list(self._rows)

    def executors(self) -> list[str]:
        return sorted({row.executor_name for row in self._rows if row.executor_name})

    def statuses(self) -> list[str]:
        return sorted({row.status for row in self._rows if row.status})

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return row.task_type or row.job_id[:8]
            if column == 1:
                return format_status(row.status, row.cancel_requested)
            if column == 2:
                return row.executor_name or "-"
            if column == 3:
                return format_progress(row.progress)
            if column == 4:
                return format_chunks(row.chunks_done, row.chunks_total)
            if column == 5:
                return format_queue_wait(row.job_queue_wait_s)
            if column == 6:
                return format_throughput(row.throughput_eps)
            if column == 7:
                return format_relative_time(row.updated_at)
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 0:
                return row.job_id
            if column == 1:
                return (
                    f"status={row.status}\n"
                    f"pending={row.chunks_pending} staging={row.chunks_staging} "
                    f"running={row.chunks_running} failed={row.chunks_failed + row.chunks_stage_failed}"
                )
        return row if role == Qt.ItemDataRole.UserRole else None
