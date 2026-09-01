from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt

from ms_components.ms_monitor.models import JobMonitorState


class JobFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, *, parent=None) -> None:
        super().__init__(parent)
        self._search_text = ""
        self._status_filter = "all"
        self._executor_filter = "all"
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search_text(self, text: str) -> None:
        self._search_text = str(text or "").strip().lower()
        self.invalidateFilter()

    def set_status_filter(self, status: str) -> None:
        self._status_filter = str(status or "all").strip().lower() or "all"
        self.invalidateFilter()

    def set_executor_filter(self, executor_name: str) -> None:
        self._executor_filter = str(executor_name or "all").strip().lower() or "all"
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        index = model.index(source_row, 0, source_parent)
        job = model.data(index, Qt.ItemDataRole.UserRole)
        if not isinstance(job, JobMonitorState):
            return True

        if self._status_filter != "all" and job.status.lower() != self._status_filter:
            return False
        if self._executor_filter != "all" and job.executor_name.lower() != self._executor_filter:
            return False
        if self._search_text:
            haystack = " ".join(
                [job.job_id, job.task_type, job.origin_id, job.executor_name, job.status]
            ).lower()
            if self._search_text not in haystack:
                return False
        return True
