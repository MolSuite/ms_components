"""Card-based job list for the monitor.

Visual widgets ported from ms_taskmanager (glow bars, status dots) adapted to
consume JobMonitorState and to plug into the monitor widget: filtering by
visibility, click-to-select, and a job_selected signal that drives the detail
panel. The card shows the job-level rollup; unfolded, the tasks in flight under it.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, Property, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ms_components.ms_monitor.formatting import format_duration
from ms_components.ms_monitor.models import JobMonitorState, TaskMonitorState
from ms_components.ms_monitor.palette import P

def status_color(status: str, default: str | None = None) -> str:
    """Resolve a job status to a live palette/semantic color."""
    return {
        "running": P["accent"],
        "waiting": P["text_muted"],
        "completed": P["ok"],
        "completed_with_errors": P["warn"],
        "failed": P["error"],
        "canceled": P["text_muted"],
        "interrupted": P["text_muted"],
    }.get(status, default if default is not None else P["text_muted"])


def eta_label(job: JobMonitorState) -> str:
    if job.is_terminal:
        return "done"
    remaining = job.chunks_total - job.chunks_done - job.chunks_failed
    if job.throughput_eps <= 0 or remaining <= 0:
        return "calculating…"
    secs = remaining / job.throughput_eps
    if secs < 60:
        return f"~{int(secs)}s"
    if secs < 3600:
        return f"~{int(secs / 60)}min"
    return f"~{secs / 3600:.1f}h"


class StatusDot(QWidget):
    def __init__(self, status="running", parent=None):
        super().__init__(parent)
        self.status = status
        self._opacity = 1.0
        self._anim: QPropertyAnimation | None = None
        self.setFixedSize(10, 10)
        self._set_animation()

    def _set_animation(self):
        if self._anim:
            self._anim.stop()
            self._anim = None
        if self.status == "running":
            self._anim = QPropertyAnimation(self, b"opacity_val")
            self._anim.setDuration(900)
            self._anim.setStartValue(1.0)
            self._anim.setEndValue(0.2)
            self._anim.setEasingCurve(QEasingCurve.SineCurve)
            self._anim.setLoopCount(-1)
            self._anim.start()

    def set_status(self, status: str):
        if status == self.status:
            return
        self.status = status
        self._set_animation()
        self.update()

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, v):
        self._opacity = v
        self.update()

    # Qt Property (not plain python property) so QPropertyAnimation can drive it.
    opacity_val = Property(float, get_opacity, set_opacity)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(status_color(self.status))
        color.setAlphaF(self._opacity)
        p.setBrush(QBrush(color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(1, 1, 8, 8)


class GlowBar(QWidget):
    def __init__(self, value=0.0, status="running", parent=None):
        super().__init__(parent)
        self._value = value
        self._status = status
        self._busy: QPropertyAnimation | None = None  # runs while how far it is is not known
        self._phase = 0.0
        self.setFixedHeight(6)
        self.setMinimumWidth(60)

    def set_value(self, v, status=None):
        """`None`: how far it is is not known, and a segment comes and goes instead."""
        if (v is None) != (self._busy is not None):
            if v is None:
                self._busy = QPropertyAnimation(self, b"phase")
                self._busy.setDuration(1600)
                self._busy.setStartValue(0.0)
                self._busy.setEndValue(1.0)
                self._busy.setEasingCurve(QEasingCurve.SineCurve)
                self._busy.setLoopCount(-1)
                self._busy.start()
            else:
                self._busy.stop()
                self._busy = None
        self._value = max(0.0, min(100.0, v or 0.0))
        if status:
            self._status = status
        self.update()

    def get_phase(self):
        return self._phase

    def set_phase(self, v):
        self._phase = v
        self.update()

    phase = Property(float, get_phase, set_phase)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setBrush(QBrush(QColor(P['bg'])))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, 3, 3)
        color = QColor(status_color(self._status, P['accent']))
        if self._busy is not None:
            color.setAlphaF(0.7)
            p.setBrush(QBrush(color))
            segment = w // 4
            p.drawRoundedRect(int((w - segment) * self._phase), 0, segment, h, 3, 3)
            return
        if self._value <= 0:
            return
        fw = max(6, int(w * self._value / 100))
        grad = QLinearGradient(0, 0, fw, 0)
        dim = QColor(color)
        dim.setAlphaF(0.4)
        grad.setColorAt(0, dim)
        grad.setColorAt(1, color)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(0, 0, fw, h, 3, 3)


_TASKS_SHOWN = 12  # rows under an unfolded job; the rest are counted


class TaskRow(QWidget):
    """One task in flight inside an unfolded job card: what it runs · bar · how far."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(8)
        self._what = QLabel()
        self._what.setFixedWidth(220)
        self._what.setStyleSheet(
            "color:palette(placeholder-text); font-size:10px; font-family:monospace; background:transparent;"
        )
        lay.addWidget(self._what)
        self._bar = GlowBar(0.0, "running")
        self._bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self._bar)
        self._far = QLabel()
        self._far.setFixedWidth(38)
        self._far.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._far.setStyleSheet("color:palette(highlight); font-size:10px; background:transparent;")
        lay.addWidget(self._far)

    def set_task(self, task: TaskMonitorState) -> None:
        what = task.input if task.chunks == 1 else f"×{task.chunks} {task.input}"
        self._what.setText(self._what.fontMetrics().elidedText(what, Qt.ElideMiddle, self._what.width()))
        took = format_duration(task.seconds)
        self._bar.set_value(task.progress, "running")  # None: not watched, so the bar only says it runs
        self._far.setText(took if task.progress is None else f"{task.progress:.0f}%")
        self.setToolTip(f"{what}\nattempt {task.attempt} · running for {took}")


class JobCard(QWidget):
    """Job rollup card. Updated in-place via set_job(). Emits clicked(job_id).

    Shows the job-level rollup: status, ETA, progress and chunk counters. Its ▶ unfolds the
    tasks in flight, which the monitor asks for only while a card is unfolded.
    """

    clicked = Signal(str)
    unfolded = Signal(str, bool)

    def __init__(self, job: JobMonitorState, parent=None):
        super().__init__(parent)
        self._job = job
        self._selected = False
        self._task_rows: list[TaskRow] = []
        self._setup_ui()
        self.set_job(job)

    @property
    def job(self) -> JobMonitorState:
        return self._job

    def mousePressEvent(self, event):
        self.clicked.emit(self._job.job_id)
        super().mousePressEvent(event)

    def _setup_ui(self):
        self.setObjectName("JobCard")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._apply_card_style()
        hdr_lay = QVBoxLayout(self)
        hdr_lay.setContentsMargins(12, 7, 12, 7)
        hdr_lay.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._dot = StatusDot(self._job.status)
        top.addWidget(self._dot, 0, Qt.AlignVCenter)

        self._title = QLabel()
        self._title.setTextFormat(Qt.RichText)
        self._title.setStyleSheet(
            f"color:palette(text); font-size:13px; font-weight:bold; background:transparent;"
        )
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(self._title)

        # Chunk counters live between the name and the ETA indicator (compact,
        # one line) instead of on a separate row below the bar.
        self._counters_lbl = QLabel()
        self._counters_lbl.setTextFormat(Qt.RichText)
        self._counters_lbl.setStyleSheet(
            f"color:palette(placeholder-text); font-size:11px; background:transparent;"
        )
        top.addWidget(self._counters_lbl)

        self._eta_lbl = QLabel()
        self._eta_lbl.setStyleSheet(
            f"color:palette(placeholder-text); font-size:11px; background:transparent;"
        )
        top.addWidget(self._eta_lbl)

        self._info_btn = QPushButton("ⓘ")
        self._info_btn.setFixedSize(20, 20)
        self._info_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._info_btn.setStyleSheet(
            f"""QPushButton {{ background:transparent; color:palette(placeholder-text);
                border:1px solid palette(mid); border-radius:10px; font-size:11px; }}
            QPushButton:hover {{ color:palette(highlight); border-color:palette(highlight);
                background:palette(alternate-base); }}"""
        )
        self._info_btn.clicked.connect(self._show_info_tooltip)
        top.addWidget(self._info_btn)

        self._toggle = QPushButton("▶")
        self._toggle.setCheckable(True)
        self._toggle.setFixedSize(20, 20)
        self._toggle.setCursor(QCursor(Qt.PointingHandCursor))
        self._toggle.setToolTip("Show the tasks in flight")
        self._toggle.setStyleSheet(
            f"""QPushButton {{ background:transparent; color:palette(placeholder-text);
                border:1px solid palette(mid); border-radius:4px; font-size:9px; }}
            QPushButton:hover {{ color:palette(highlight); border-color:palette(highlight); }}"""
        )
        self._toggle.toggled.connect(self._on_toggled)
        top.addWidget(self._toggle)

        hdr_lay.addLayout(top)

        prog = QHBoxLayout()
        prog.setSpacing(10)
        self._bar = GlowBar(0.0, "running")
        self._bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        prog.addWidget(self._bar)
        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setFixedWidth(46)
        self._pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        prog.addWidget(self._pct_lbl)
        hdr_lay.addLayout(prog)

        self._tasks_wrap = QWidget(self)
        self._tasks_wrap.setVisible(False)
        self._tasks_wrap.setStyleSheet("background:transparent;")
        self._tasks_layout = QVBoxLayout(self._tasks_wrap)
        self._tasks_layout.setContentsMargins(18, 2, 4, 2)
        self._tasks_layout.setSpacing(2)
        self._tasks_note = QLabel()  # nothing in flight, or how many more than the rows shown
        self._tasks_note.setStyleSheet("color:palette(placeholder-text); font-size:10px; background:transparent;")
        self._tasks_layout.addWidget(self._tasks_note)
        hdr_lay.addWidget(self._tasks_wrap)

    def _on_toggled(self, unfolded: bool):
        self._tasks_wrap.setVisible(unfolded)
        self._toggle.setText("▼" if unfolded else "▶")
        self._refresh_tasks()
        self.unfolded.emit(self._job.job_id, unfolded)

    def _refresh_tasks(self):
        # Rows are reused in place, so the bars neither flicker nor restart at every poll.
        tasks = self._job.tasks
        shown = tasks[:_TASKS_SHOWN]
        while len(self._task_rows) > len(shown):
            row = self._task_rows.pop()
            row.setParent(None)
            row.deleteLater()
        for index, task in enumerate(shown):
            if index == len(self._task_rows):
                self._task_rows.append(TaskRow())
                self._tasks_layout.insertWidget(index, self._task_rows[-1])
            self._task_rows[index].set_task(task)
        more = len(tasks) - len(shown)
        self._tasks_note.setText(f"+{more} more tasks…" if more else "No tasks in flight")
        self._tasks_note.setVisible(bool(more) or not shown)

    def _apply_card_style(self):
        border = P["accent"] if self._selected else P["border"]
        self.setStyleSheet(
            f"""#JobCard {{ background:palette(base); border:1px solid {border};
                border-radius:8px; }}
            #JobCard:hover {{ border-color:palette(mid); }}"""
        )

    def set_selected(self, selected: bool):
        if selected == self._selected:
            return
        self._selected = selected
        self._apply_card_style()

    def set_job(self, job: JobMonitorState):
        self._job = job
        label = job.name or job.job_id[:12]
        sc = status_color(job.status)
        status = job.status.replace("_", " ").upper()
        self._title.setText(
            f"{label} <span style='color:{sc}; font-size:10px; "
            f"font-weight:normal;'>[{status}]</span>"
        )
        self._title.setToolTip(f"{job.error}\n\n{job.job_id}" if job.error else job.job_id)
        self._dot.set_status(job.status)
        self._eta_lbl.setText(eta_label(job))
        self._bar.set_value(job.progress, job.status)
        self._pct_lbl.setStyleSheet(
            f"color:{sc}; font-weight:bold; font-size:12px; background:transparent;"
        )
        self._pct_lbl.setText(f"{job.progress:.1f}%")

        parts = []
        if job.chunks_done:
            parts.append(f"<span style='color:{P['ok']}'>{job.chunks_done:,} ✓</span>")
        if job.chunks_running:
            parts.append(f"<span style='color:{P['accent']}'>{job.chunks_running} ⚙</span>")
        if job.chunks_failed:
            parts.append(f"<span style='color:{P['error']}'>{job.chunks_failed:,} ✗</span>")
        total = f"  / {job.chunks_total:,}" if job.chunks_total else ""
        self._counters_lbl.setText("  ·  ".join(parts) + total)
        if self._toggle.isChecked():
            self._refresh_tasks()

    def _show_info_tooltip(self):
        j = self._job
        total = f"{j.chunks_total:,}" if j.chunks_total else "?"
        tip = (
            f"<b style='color:{P['accent']}'>{j.name or j.job_id[:16]}</b>"
            f"<hr style='border-color:{P['border']}'>"
            f"<b>Key:</b> {j.job_id}<br>"
            f"<b>Chunks:</b> {j.chunks_done:,} ✓ / {total} total<br>"
            f"<b>Running:</b> {j.chunks_running}  "
            f"<b>Failed:</b> {j.chunks_failed:,}  "
            f"<b>Retried:</b> {j.chunks_retried:,}<br>"
            f"<b>Peak memory:</b> {j.peak_mem_mb or '—'} MB<br>"
            f"<b>Throughput:</b> {j.throughput_eps:.2f} chunks/s  ·  <b>ETA:</b> {eta_label(j)}"
        )
        QToolTip.showText(
            self._info_btn.mapToGlobal(QPoint(self._info_btn.width() + 4, 0)),
            tip,
            self._info_btn,
        )


class JobCardList(QScrollArea):
    """Scrollable list of JobCards. Drop-in replacement for the job QTreeView."""

    job_selected = Signal(str)
    unfolded_changed = Signal(object)  # the ids of the jobs whose tasks are shown

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, JobCard] = {}
        self._unfolded: set[str] = set()
        self._selected_id: str | None = None
        self._search = ""
        self._status_filter = "all"

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        container.setStyleSheet("background:palette(window);")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(8)
        self._empty_lbl = QLabel("No jobs")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet("color:palette(placeholder-text); font-size:13px; padding:40px;")
        self._layout.addWidget(self._empty_lbl)
        self._layout.addStretch()
        self.setWidget(container)

    # -- data --------------------------------------------------------------
    def set_jobs(self, jobs: list[JobMonitorState]) -> None:
        new_ids = [j.job_id for j in jobs]
        for jid in list(self._cards):
            if jid not in new_ids:
                card = self._cards.pop(jid)
                card.setParent(None)
                card.deleteLater()
                if jid == self._selected_id:
                    self._selected_id = None
                if jid in self._unfolded:
                    self._on_card_unfolded(jid, False)
        # insert/update in snapshot order; stretch is the last item.
        for pos, job in enumerate(jobs):
            card = self._cards.get(job.job_id)
            if card is None:
                card = JobCard(job)
                card.clicked.connect(self._on_card_clicked)
                card.unfolded.connect(self._on_card_unfolded)
                self._cards[job.job_id] = card
            else:
                card.set_job(job)
            self._layout.insertWidget(pos, card)
        self._empty_lbl.setVisible(not jobs)
        self._apply_filters()

    def clear(self) -> None:
        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._selected_id = None
        self._empty_lbl.setVisible(True)
        if self._unfolded:
            self._unfolded.clear()
            self.unfolded_changed.emit(frozenset())

    def _on_card_unfolded(self, job_id: str, unfolded: bool) -> None:
        (self._unfolded.add if unfolded else self._unfolded.discard)(job_id)
        self.unfolded_changed.emit(frozenset(self._unfolded))

    # -- selection ---------------------------------------------------------
    def selected_job(self) -> JobMonitorState | None:
        card = self._cards.get(self._selected_id or "")
        return card.job if card else None

    def selected_job_id(self) -> str | None:
        return self._selected_id

    def select_job(self, job_id: str) -> None:
        if job_id not in self._cards or job_id == self._selected_id:
            return
        self._set_selected(job_id)

    def _on_card_clicked(self, job_id: str) -> None:
        self._set_selected(job_id)
        self.job_selected.emit(job_id)

    def _set_selected(self, job_id: str | None) -> None:
        if self._selected_id and self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(False)
        self._selected_id = job_id
        if job_id and job_id in self._cards:
            self._cards[job_id].set_selected(True)

    # -- filtering ---------------------------------------------------------
    def set_search_text(self, text: str) -> None:
        self._search = str(text or "").strip().lower()
        self._apply_filters()

    def set_status_filter(self, status: str) -> None:
        self._status_filter = str(status or "all").strip().lower() or "all"
        self._apply_filters()

    def _apply_filters(self) -> None:
        for card in self._cards.values():
            card.setVisible(self._accepts(card.job))

    def _accepts(self, job: JobMonitorState) -> bool:
        if self._status_filter != "all" and job.status.lower() != self._status_filter:
            return False
        return self._search in f"{job.job_id} {job.name} {job.status}".lower()
