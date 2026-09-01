"""Card-based job list for the monitor.

Visual widgets ported from ms_taskmanager (glow bars, status dots, executor
badges) adapted to consume JobMonitorState and to plug into the monitor widget:
filtering by visibility, click-to-select, and a job_selected signal that drives
the detail panels. Per-chunk detail lives only in the bottom ChunkPanel — the
card shows the job-level rollup, never the individual chunks.
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

from ms_components.ms_monitor.models import ChunkMonitorState, JobMonitorState
from ms_components.ms_monitor.palette import P

def status_color(status: str, default: str | None = None) -> str:
    """Resolve a job status to a live palette/semantic color."""
    return {
        "running": P["accent"],
        "pending": P["text_muted"],
        "staging": P["warn"],
        "completed": P["ok"],
        "failed": P["error"],
        "canceled": P["text_muted"],
    }.get(status, default if default is not None else P["text_muted"])


# Executor-type badges: fixed identity colors (like status), not theme chrome.
EXECUTOR_BADGE = {
    "thread": ("#1a3a2a", "#2ed573", "THR"),
    "process": ("#1a2a3a", "#4f8cff", "PRC"),
    "ray": ("#2a1a3a", "#a78bfa", "RAY"),
    "dask": ("#2a2a1a", "#fbbf24", "DSK"),
    "hpc": ("#3a1a1a", "#f87171", "HPC"),
}


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
        self.setFixedHeight(6)
        self.setMinimumWidth(60)

    def set_value(self, v, status=None):
        self._value = max(0.0, min(100.0, v))
        if status:
            self._status = status
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setBrush(QBrush(QColor(P['bg'])))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, 3, 3)
        if self._value <= 0:
            return
        fw = max(6, int(w * self._value / 100))
        color = QColor(status_color(self._status, P['accent']))
        grad = QLinearGradient(0, 0, fw, 0)
        dim = QColor(color)
        dim.setAlphaF(0.4)
        grad.setColorAt(0, dim)
        grad.setColorAt(1, color)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(0, 0, fw, h, 3, 3)


class ExecutorBadge(QLabel):
    def __init__(self, executor_name: str, parent=None):
        super().__init__(parent)
        key = (executor_name or "").lower().split("-")[0].split("_")[0]
        bg, fg, text = EXECUTOR_BADGE.get(
            key, (P['panel_alt'], P["text_muted"], (executor_name or "?")[:3].upper())
        )
        self.setText(text)
        self.setFixedHeight(18)
        self.setAlignment(Qt.AlignCenter)
        self.setContentsMargins(6, 0, 6, 0)
        self.setStyleSheet(
            f"""QLabel {{
                background: {bg}; color: {fg};
                border: 1px solid {fg}; border-radius: 3px;
                font-size: 10px; font-weight: bold;
                letter-spacing: 0.5px; padding: 0 4px;
            }}"""
        )


class ChunkRow(QWidget):
    """One live chunk inside an expanded job card: short_id · bar · %."""

    def __init__(self, chunk: ChunkMonitorState, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(8)
        self._id = QLabel(chunk.short_id)
        self._id.setFixedWidth(76)
        self._id.setStyleSheet(
            f"color:palette(placeholder-text); font-size:10px; font-family:monospace; background:transparent;"
        )
        lay.addWidget(self._id)
        self._bar = GlowBar(chunk.progress, chunk.status or "running")
        self._bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self._bar)
        self._pct = QLabel()
        self._pct.setFixedWidth(38)
        self._pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pct.setStyleSheet("color:palette(highlight); font-size:10px; background:transparent;")
        lay.addWidget(self._pct)
        self.update_chunk(chunk)

    def update_chunk(self, chunk: ChunkMonitorState) -> None:
        self._bar.set_value(chunk.progress, chunk.status or "running")
        self._pct.setText(f"{chunk.progress:.0f}%")


class JobCard(QWidget):
    """Job rollup card. Updated in-place via set_job(). Emits clicked(job_id).

    Header shows the job-level rollup (status, executor, ETA, progress, chunk
    counters). Expanding the card (▶) reveals its live per-chunk rows, sourced
    from job.chunks which the snapshot already populates.
    """

    clicked = Signal(str)

    def __init__(self, job: JobMonitorState, parent=None):
        super().__init__(parent)
        self._job = job
        self._selected = False
        self._expanded = False
        self._chunk_rows: dict[str, ChunkRow] = {}
        self._chunks_overflow: QLabel | None = None
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

        # Chunk counters live between the name and the executor/ETA indicators (compact,
        # one line) instead of on a separate row below the bar.
        self._counters_lbl = QLabel()
        self._counters_lbl.setTextFormat(Qt.RichText)
        self._counters_lbl.setStyleSheet(
            f"color:palette(placeholder-text); font-size:11px; background:transparent;"
        )
        top.addWidget(self._counters_lbl)

        self._badge = ExecutorBadge(self._job.executor_name)
        top.addWidget(self._badge)

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
        self._toggle.setFixedSize(20, 20)
        self._toggle.setCursor(QCursor(Qt.PointingHandCursor))
        self._toggle.setToolTip("Show live chunks")
        self._toggle.setStyleSheet(
            f"""QPushButton {{ background:transparent; color:palette(placeholder-text);
                border:1px solid palette(mid); border-radius:4px; font-size:9px; }}
            QPushButton:hover {{ color:palette(highlight); border-color:palette(highlight); }}"""
        )
        self._toggle.clicked.connect(self._toggle_chunks)
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

        # Collapsible live-chunk list (hidden until the card is expanded).
        self._chunks_wrap = QWidget(self)
        self._chunks_wrap.setVisible(False)
        self._chunks_wrap.setStyleSheet("background:transparent;")
        self._chunks_layout = QVBoxLayout(self._chunks_wrap)
        self._chunks_layout.setContentsMargins(18, 2, 4, 2)
        self._chunks_layout.setSpacing(2)
        self._chunks_empty = QLabel("No active chunks")
        self._chunks_empty.setStyleSheet("color:palette(placeholder-text); font-size:10px; background:transparent;")
        self._chunks_layout.addWidget(self._chunks_empty)
        hdr_lay.addWidget(self._chunks_wrap)

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
        label = job.task_type or job.origin_id or job.job_id[:12]
        sc = status_color(job.status)
        status = job.status + (" (canceling)" if job.cancel_requested and not job.is_terminal else "")
        self._title.setText(
            f"{label} <span style='color:{sc}; font-size:10px; "
            f"font-weight:normal;'>[{status.upper()}]</span>"
        )
        self._title.setToolTip(f"{job.error}\n\n{job.job_id}" if job.error else job.job_id)
        self._dot.set_status(job.status)
        self._eta_lbl.setText(eta_label(job))
        self._bar.set_value(job.progress, job.status)
        self._pct_lbl.setStyleSheet(
            f"color:{sc}; font-weight:bold; font-size:12px; background:transparent;"
        )
        self._pct_lbl.setText(f"{job.progress:.1f}%")

        failed = job.chunks_failed + job.chunks_stage_failed
        parts = []
        if job.chunks_done:
            parts.append(f"<span style='color:{P['ok']}'>{job.chunks_done:,} ✓</span>")
        if job.chunks_running:
            parts.append(f"<span style='color:{P['accent']}'>{job.chunks_running} ⚙</span>")
        if job.chunks_pending:
            parts.append(f"<span style='color:{P['text_muted']}'>{job.chunks_pending:,} ⏳</span>")
        if failed:
            parts.append(f"<span style='color:{P['error']}'>{failed} ✗</span>")
        total = f"  / {job.chunks_total:,}" if job.chunks_total else ""
        self._counters_lbl.setText("  ·  ".join(parts) + total)

        if self._expanded:
            self._refresh_chunk_rows()

    def _toggle_chunks(self):
        self._expanded = not self._expanded
        self._chunks_wrap.setVisible(self._expanded)
        self._toggle.setText("▼" if self._expanded else "▶")
        if self._expanded:
            self._refresh_chunk_rows()

    def _refresh_chunk_rows(self):
        # Incremental update (like ms_taskmanager) so in-flight bars don't flicker
        # or reset scroll on every poll. Cap the visible rows; count the rest.
        MAX = 12
        chunks = list(self._job.chunks or [])
        visible = chunks[:MAX]
        visible_ids = {c.chunk_id for c in visible}
        for cid in list(self._chunk_rows):
            if cid not in visible_ids:
                row = self._chunk_rows.pop(cid)
                row.setParent(None)
                row.deleteLater()
        for chunk in visible:
            row = self._chunk_rows.get(chunk.chunk_id)
            if row is None:
                row = ChunkRow(chunk)
                self._chunk_rows[chunk.chunk_id] = row
                insert_at = self._chunks_layout.count()
                if self._chunks_overflow is not None:
                    insert_at -= 1
                self._chunks_layout.insertWidget(insert_at, row)
            else:
                row.update_chunk(chunk)
        self._chunks_empty.setVisible(not visible)
        overflow = len(chunks) - MAX
        if self._chunks_overflow is None:
            self._chunks_overflow = QLabel()
            self._chunks_overflow.setStyleSheet(
                f"color:palette(placeholder-text); font-size:10px; background:transparent;"
            )
            self._chunks_layout.addWidget(self._chunks_overflow)
        self._chunks_overflow.setVisible(overflow > 0)
        if overflow > 0:
            self._chunks_overflow.setText(f"  +{overflow} more chunks…")

    def _show_info_tooltip(self):
        j = self._job
        failed = j.chunks_failed + j.chunks_stage_failed
        tip = (
            f"<b style='color:{P['accent']}'>{j.task_type or j.job_id[:16]}</b>"
            f"<hr style='border-color:{P['border']}'>"
            f"<b>Job ID:</b> {j.job_id}<br>"
            f"<b>Origin:</b> {j.origin_id or '—'}<br>"
            f"<b>Executor:</b> {j.executor_name or '—'}<br>"
            f"<b>Priority:</b> {j.priority}<br>"
            f"<b>Chunks:</b> {j.chunks_done:,} ✓ / {j.chunks_total:,} total<br>"
            f"<b>Running:</b> {j.chunks_running}  "
            f"<b>Pending:</b> {j.chunks_pending:,}  "
            f"<b>Failed:</b> {failed}<br>"
            f"<b>Throughput:</b> {j.throughput_eps:.2f} eps  ·  <b>ETA:</b> {eta_label(j)}"
        )
        QToolTip.showText(
            self._info_btn.mapToGlobal(QPoint(self._info_btn.width() + 4, 0)),
            tip,
            self._info_btn,
        )


class JobCardList(QScrollArea):
    """Scrollable list of JobCards. Drop-in replacement for the job QTreeView."""

    job_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, JobCard] = {}
        self._selected_id: str | None = None
        self._search = ""
        self._status_filter = "all"
        self._executor_filter = "all"

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
        # insert/update in snapshot order; stretch is the last item.
        for pos, job in enumerate(jobs):
            card = self._cards.get(job.job_id)
            if card is None:
                card = JobCard(job)
                card.clicked.connect(self._on_card_clicked)
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

    def set_executor_filter(self, executor_name: str) -> None:
        self._executor_filter = str(executor_name or "all").strip().lower() or "all"
        self._apply_filters()

    def _apply_filters(self) -> None:
        for card in self._cards.values():
            card.setVisible(self._accepts(card.job))

    def _accepts(self, job: JobMonitorState) -> bool:
        if self._status_filter != "all" and job.status.lower() != self._status_filter:
            return False
        if self._executor_filter != "all" and job.executor_name.lower() != self._executor_filter:
            return False
        if self._search:
            haystack = " ".join(
                [job.job_id, job.task_type, job.origin_id, job.executor_name, job.status]
            ).lower()
            if self._search not in haystack:
                return False
        return True
