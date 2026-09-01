from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ms_components.ms_monitor.models import JobDetailState
from ms_components.ms_monitor.palette import P


def _first_line(text: str) -> str:
    """The semantic message: the first non-empty line of a possibly-multi-line error."""
    return next(
        (
            line.strip()
            for line in str(text or "").splitlines()
            if line.strip()
        ),
        "",
    )


class EventsPanel(QFrame):
    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("eventsPanel")
        self.setStyleSheet(
            f"""
            QPlainTextEdit, QTabWidget::pane {{
                background: palette(alternate-base);
                color: palette(text);
                
            }}
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
        self._events = QPlainTextEdit(self)
        self._events.setReadOnly(True)
        self._outputs = QPlainTextEdit(self)
        self._outputs.setReadOnly(True)
        self._logs = QPlainTextEdit(self)
        self._logs.setReadOnly(True)

        self._tabs.addTab(self._summary, "Summary")
        self._errors_tab_index = self._tabs.addTab(self._errors, "Errors")
        self._tabs.addTab(self._events, "Events")
        self._tabs.addTab(self._outputs, "Outputs")
        self._tabs.addTab(self._logs, "Logs")

        layout.addWidget(self._title)
        layout.addWidget(self._tabs, 1)

    def is_user_interacting(self) -> bool:
        editors = (self._summary, self._errors, self._events, self._outputs, self._logs)
        if any(editor.hasFocus() for editor in editors):
            return True
        return any(
            editor.verticalScrollBar().isSliderDown()
            or editor.horizontalScrollBar().isSliderDown()
            for editor in editors
        )

    def clear(self) -> None:
        self._title.setText("Job Detail")
        self._summary.setPlainText("")
        self._errors.setPlainText("")
        self._tabs.setTabText(self._errors_tab_index, "Errors")
        self._events.setPlainText("")
        self._outputs.setPlainText("")
        self._logs.setPlainText("")

    def set_job_detail(self, detail: JobDetailState | None) -> None:
        if detail is None or not detail.job_id:
            self.clear()
            return

        self._title.setText(f"Job Detail: {detail.job_id[:8]}")
        job = detail.job
        if job is None:
            self._summary.setPlainText("No summary available.")
        else:
            lines = [
                f"job_id: {job.job_id}",
                f"status: {job.status}",
                f"executor: {job.executor_name or '-'}",
                f"task_type: {job.task_type or '-'}",
                f"priority: {job.priority}",
                f"queue_policy: {job.queue_policy}",
                f"progress: {job.progress:.2f}",
                f"chunks: done={job.chunks_done} total={job.chunks_total} "
                f"running={job.chunks_running} staging={job.chunks_staging} pending={job.chunks_pending}",
                f"feed: exhausted={job.feed_exhausted} cursor={job.feed_cursor_position} acked={job.feed_items_acked}",
                f"throughput_eps: {job.throughput_eps:.3f}",
                f"job_queue_wait_s: {job.job_queue_wait_s if job.job_queue_wait_s is not None else '-'}",
                f"chunk_queue_wait_avg_s: {job.chunk_queue_wait_avg_s:.3f}",
                f"chunk_queue_wait_max_s: {job.chunk_queue_wait_max_s:.3f}",
                f"output_sink: {job.output_sink if job.output_sink is not None else '-'}",
            ]
            # Failure reason: the job-level error is often empty even when the job
            # failed — the real cause lives on the failed chunk(s). The Summary shows the
            # one-line semantic reason + which input failed; the Errors tab has full tracebacks.
            failed_chunks = [
                c for c in detail.chunks
                if (c.status or "").lower() in ("failed", "stage_failed")
            ]
            failure_lines: list[str] = []
            if job.error:
                failure_lines.append(f"job: {_first_line(job.error)}")
            for chunk in failed_chunks:
                where = f" [{chunk.input_summary}]" if chunk.input_summary else ""
                reason = _first_line(chunk.error) or "failed (no message recorded)"
                failure_lines.append(f"chunk {chunk.short_id}{where}: {reason}")
            if failure_lines:
                lines.append("")
                lines.append("--- FAILURE (see Errors tab for full traceback) ---")
                lines.extend(failure_lines)
            self._summary.setPlainText("\n".join(lines))

        self._populate_errors(detail)

        event_lines = []
        for item in detail.events:
            when = item.created_at.isoformat(timespec="seconds") if item.created_at is not None else "-"
            event_lines.append(f"[{when}] {item.level or '-'} {item.event_type}: {item.message}")
        self._events.setPlainText("\n".join(event_lines) if event_lines else "No recent events.")

        output_lines = []
        for item in detail.outputs:
            try:
                output_lines.append(json.dumps(item.payload, ensure_ascii=True, indent=2, sort_keys=True))
            except TypeError:
                output_lines.append(repr(item.payload))
        self._outputs.setPlainText("\n\n".join(output_lines) if output_lines else "No recent outputs.")

        log_lines = [item.line for item in detail.logs]
        self._logs.setPlainText("\n".join(log_lines) if log_lines else "No recent logs.")

    def _populate_errors(self, detail: JobDetailState) -> None:
        """Dedicated Errors tab: one block per failed chunk with the failing input and the
        full traceback. This is the 'what actually happened' view the semantic one-liner isn't."""
        failed = [
            c for c in detail.chunks
            if (c.status or "").lower() in ("failed", "stage_failed")
        ]
        job_error = detail.job.error if detail.job is not None else ""
        if not failed and not job_error:
            self._errors.setPlainText("No errors for this job.")
            self._tabs.setTabText(self._errors_tab_index, "Errors")
            return

        blocks: list[str] = []
        if job_error:
            blocks.append(f"JOB ERROR\n{job_error}")
        for chunk in failed:
            header = f"CHUNK {chunk.short_id}"
            if chunk.input_summary:
                header += f"  —  input: {chunk.input_summary}"
            body = chunk.error or "(no error message recorded for this chunk)"
            blocks.append(f"{header}\n{body}")
        self._errors.setPlainText(f'\n\n{"=" * 60}\n\n'.join(blocks))
        self._tabs.setTabText(self._errors_tab_index, f"Errors ({len(failed)})")
