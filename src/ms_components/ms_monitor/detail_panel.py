from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ms_components.ms_monitor.models import JobDetailState


def _reason(text: str) -> str:
    """The semantic message: the last non-empty line of a traceback, the first of anything else."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1] if any(line.startswith("Traceback") for line in lines) else lines[0]


def _when(value) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if value is not None else "-"


class JobDetailPanel(QFrame):
    """What the selected job is and why it failed: a summary and one block per failed chunk."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("jobDetailPanel")
        self.setStyleSheet(
            """
            QPlainTextEdit, QTabWidget::pane {
                background: palette(alternate-base);
                color: palette(text);
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 0, 0)
        layout.setSpacing(8)

        self._title = QLabel("Job Detail", self)
        self._tabs = QTabWidget(self)
        self._summary = QPlainTextEdit(self)
        self._summary.setReadOnly(True)
        self._errors = QPlainTextEdit(self)
        self._errors.setReadOnly(True)
        self._errors.setLineWrapMode(QPlainTextEdit.NoWrap)  # keep tracebacks readable

        self._tabs.addTab(self._summary, "Summary")
        self._errors_tab_index = self._tabs.addTab(self._errors, "Errors")

        layout.addWidget(self._title)
        layout.addWidget(self._tabs, 1)

    def clear(self) -> None:
        self._title.setText("Job Detail")
        self._summary.setPlainText("")
        self._errors.setPlainText("")
        self._tabs.setTabText(self._errors_tab_index, "Errors")

    def set_job_detail(self, detail: JobDetailState | None) -> None:
        if detail is None or not detail.job_id:
            self.clear()
            return

        job = detail.job
        self._title.setText(f"Job Detail: {job.name if job is not None and job.name else detail.job_id[:8]}")
        if job is None:
            self._summary.setPlainText("No summary available.")
        else:
            lines = [
                f"name: {job.name or '-'}",
                f"key: {job.job_id}",
                f"status: {job.status}",
                f"progress: {job.progress:.1f}%",
                f"chunks: done={job.chunks_done} failed={job.chunks_failed} running={job.chunks_running} "
                f"total={job.chunks_total or '?'} retried={job.chunks_retried}",
                f"throughput: {job.throughput_eps:.2f} chunks/s (mean)",
                f"peak memory: {job.peak_mem_mb} MB" if job.peak_mem_mb else "peak memory: -",
                f"started: {_when(job.started_at)}",
                f"finished: {_when(job.finished_at)}",
            ]
            if job.engine_id is None:
                lines.append("read from the project's journal: not run by this session")
            # The job-level error is often empty even when chunks failed. The Summary shows the
            # one-line reasons; the Errors tab has the full tracebacks.
            reasons = [f"job: {_reason(job.error)}"] if job.error else []
            reasons += [
                f"chunk (attempt {failure.attempt}): {_reason(failure.error) or 'failed (no message recorded)'}"
                for failure in detail.failures
            ]
            if reasons:
                lines += ["", "--- FAILURE (see Errors tab for full traceback) ---", *reasons]
            self._summary.setPlainText("\n".join(lines))
        self._populate_errors(detail)

    def _populate_errors(self, detail: JobDetailState) -> None:
        job = detail.job
        job_error = job.error if job is not None else ""
        if not detail.failures and not job_error:
            self._errors.setPlainText("No errors for this job.")
            self._tabs.setTabText(self._errors_tab_index, "Errors")
            return

        blocks = [f"JOB ERROR\n{job_error}"] if job_error else []
        blocks += [
            f"CHUNK {index}  —  attempt {failure.attempt}\n"
            f"{failure.error or '(no error message recorded for this chunk)'}"
            for index, failure in enumerate(detail.failures, start=1)
        ]
        failed = job.chunks_failed if job is not None else len(detail.failures)
        if failed > len(detail.failures):
            blocks.append(f"… {failed - len(detail.failures)} more failed chunks not shown")
        self._errors.setPlainText(f'\n\n{"=" * 60}\n\n'.join(blocks))
        self._tabs.setTabText(self._errors_tab_index, f"Errors ({failed})")
