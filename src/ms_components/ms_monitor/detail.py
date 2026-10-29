"""The selected job: what it is, four numbers (time left, progress, speed, failures), a cell per
chunk, and its tasks in flight and failures.

The grid is one 8-bit indexed image of the job's chunk bytes (`JobMonitorState.chunk_states`):
a cell per chunk while they fit, else several chunks per pixel painted as the worst of them
(failed, then running, then done, then pending). Chunks the source has not given yet are pending.
"""
from __future__ import annotations

import statistics
from datetime import datetime

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QToolTip,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ms_components.ms_monitor.formatting import format_duration, format_speed
from ms_components.ms_monitor.jobs import status_color
from ms_components.ms_monitor.models import FailureState, JobMonitorState
from ms_components.ms_monitor.palette import P

SLOW = 2.5  # a task that has run this many times the median of its job's tasks reads as slow

# ms_flow's chunk byte (0 pending, 1 running, 2 done, 3 failed) → how bad it is, and back:
# the same table both ways, so a pixel of several chunks keeps the max.
_RANK = bytes([0, 2, 1, 3, 4] + [4] * 251)
_STATES = ("pending", "done", "running", "failed")  # by rank
_EMPTY = 4  # past the last chunk


def reason(text: str) -> str:
    """The semantic message: the last non-empty line of a traceback, the first of anything else."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1] if any(line.startswith("Traceback") for line in lines) else lines[0]


def _colors() -> list[QColor]:
    """By rank: pending, done, running, failed, and the background."""
    app = QApplication.instance()
    pal = app.palette() if app else QPalette()
    return [pal.color(QPalette.ColorRole.Mid), QColor(P["ok"]), pal.color(QPalette.ColorRole.Highlight),
            QColor(P["error"]), pal.color(QPalette.ColorRole.Base)]


def layout_cells(n: int, width: int, height: int) -> tuple[int, int, int]:
    """`(cell px, columns, chunks per cell)` to fit `n` chunks in `width` × `height`."""
    for size in range(12, 0, -1):
        cols = max(1, width // size)
        if -(-n // cols) <= max(1, height // size):
            return size, cols, 1
    per = -(-n // max(1, width * height))
    return 1, max(1, width), per


def ranks(states: bytes, n: int, per: int) -> bytes:
    """A rank per cell: `states` padded to `n` as pending, `per` chunks to a cell, the worst of them."""
    ranked = bytes(states[:n]).translate(_RANK) + bytes(max(0, n - len(states)))
    if per == 1:
        return ranked
    return bytes(max(ranked[i:i + per]) for i in range(0, n, per))


class ChunkGrid(QWidget):
    """A cell per chunk of the selected job, as one indexed image."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(60)
        self.setMouseTracking(True)
        self._states, self._n = b"", 0
        self._image: QImage | None = None
        self._layout = (1, 1, 1)
        self._cells = b""
        self._key = None

    def set_states(self, states: bytes | None, total: int) -> None:
        states = states or b""
        n = max(len(states), total)
        if (states, n) != (self._states, self._n):
            self._states, self._n = states, n
            self.update()

    def _build(self) -> None:
        key = (self._states, self._n, self.width(), self.height())
        if key == self._key:
            return
        self._key = key
        self._layout = size, cols, per = layout_cells(self._n, self.width(), self.height())
        self._cells = cells = ranks(self._states, self._n, per)
        rows = max(1, -(-len(cells) // cols))
        data = cells + bytes([_EMPTY]) * (rows * cols - len(cells))
        image = QImage(data, cols, rows, cols, QImage.Format_Indexed8)
        image.setColorTable([color.rgba() for color in _colors()])
        self._image = image.copy()  # its own pixels: `data` goes away

    def paintEvent(self, _):
        if not self._n:
            return
        self._build()
        size, cols, _ = self._layout
        p = QPainter(self)
        p.drawImage(QRect(0, 0, self._image.width() * size, self._image.height() * size), self._image)
        if size >= 5:  # a gap between cells that are big enough to see one
            p.setPen(QPen(self.palette().color(QPalette.ColorRole.Base), 1))
            w, h = self._image.width() * size, self._image.height() * size
            for x in range(size, w, size):
                p.drawLine(x, 0, x, h)
            for y in range(size, h, size):
                p.drawLine(0, y, w, y)

    def mouseMoveEvent(self, event):
        size, cols, per = self._layout
        x, y = int(event.position().x()) // size, int(event.position().y()) // size
        cell = y * cols + x
        if x >= cols or not 0 <= cell < len(self._cells):
            QToolTip.hideText()
            return
        first = cell * per
        what = _STATES[self._cells[cell]]
        said = (f"chunk {first + 1:,}: {what}" if per == 1
                else f"chunks {first + 1:,}–{min(self._n, first + per):,}: {what} at worst")
        QToolTip.showText(event.globalPosition().toPoint(), said, self)


class _StackBar(QWidget):
    """Done, running, failed and pending as one bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.parts = (0, 0, 0, 0)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, 3, 3)
        p.setClipPath(clip)
        p.fillRect(r, self.palette().color(QPalette.ColorRole.Mid))
        total, x = sum(self.parts), 0.0
        if not total:
            return
        hues = (QColor(P["ok"]), self.palette().color(QPalette.ColorRole.Highlight), QColor(P["error"]))
        for part, hue in zip(self.parts, hues):
            w = r.width() * part / total
            p.fillRect(QRectF(x, 0, w, r.height()), hue)
            x += w


class _Trend(QWidget):
    """A line of the speed over the last minutes, its own scale."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
        self.values: list[float] = []

    def paintEvent(self, _):
        if len(self.values) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h, top = self.width(), self.height() - 1, max(self.values) or 1.0
        step = w / (len(self.values) - 1)
        p.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), 1.5))
        p.drawPolyline([QPointF(i * step, h - (h - 1) * v / top) for i, v in enumerate(self.values)])


class _Kpi(QFrame):
    def __init__(self, title: str, extra: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("kpi")
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 6, 10, 6)
        box.setSpacing(2)
        head = QLabel(title, self)
        head.setStyleSheet("color:palette(placeholder-text); font-size:10px; font-weight:600;")
        self.value = QLabel("—", self)
        self.value.setStyleSheet("font-size:18px; font-weight:700;")
        self.sub = QLabel("", self)
        self.sub.setStyleSheet("color:palette(placeholder-text); font-size:10px;")
        box.addWidget(head)
        box.addWidget(self.value)
        if extra is not None:
            extra.setParent(self)
            box.addWidget(extra)
        box.addWidget(self.sub)

    def set(self, value: str, sub: str = "", accent: str | None = None) -> None:
        self.value.setText(value)
        self.sub.setText(sub)
        self.value.setStyleSheet(f"font-size:18px; font-weight:700;{f' color:{accent};' if accent else ''}")


def _clock(seconds_from_now: float) -> str:
    return datetime.fromtimestamp(datetime.now().timestamp() + seconds_from_now).strftime("%H:%M")


class JobDetail(QWidget):
    """The selected job. `set_job` each poll; `set_failures` when its failures change."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame#kpi { background:palette(base); border:1px solid palette(mid); border-radius:8px; }")
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        self._name = QLabel("Select a job", self)
        self._name.setStyleSheet("font-size:15px; font-weight:700;")
        self._badge = QLabel(self)
        self._chip = QLabel(self)
        self._chip.setStyleSheet("color:palette(placeholder-text); border:1px solid palette(mid); border-radius:4px; padding:0 4px;")
        head.addWidget(self._name)
        head.addWidget(self._badge)
        head.addWidget(self._chip)
        head.addStretch(1)
        box.addLayout(head)
        self._meta = QLabel(self)
        self._meta.setStyleSheet("color:palette(placeholder-text); font-size:10px;")
        self._meta.setWordWrap(True)
        box.addWidget(self._meta)

        kpis = QHBoxLayout()
        self._bar, self._trend = _StackBar(), _Trend()
        self._left = _Kpi("TIME LEFT", parent=self)
        self._progress = _Kpi("PROGRESS", self._bar, self)
        self._speed = _Kpi("SPEED · LAST 5 MIN", self._trend, self)
        self._failed = _Kpi("FAILURES", parent=self)
        for kpi in (self._left, self._progress, self._speed, self._failed):
            kpis.addWidget(kpi, 1)
        box.addLayout(kpis)

        self._grid = ChunkGrid(self)
        self._legend = QLabel(self)
        self._legend.setStyleSheet("font-size:10px; color:palette(placeholder-text);")

        self._tabs = QTabWidget(self)
        self._tasks = QTreeWidget(self)
        self._tasks.setHeaderLabels(["Input", "Host", "Attempt", "Elapsed", "Progress"])
        self._tasks.setRootIsDecorated(False)
        self._tasks.setUniformRowHeights(True)
        self._errors = QTreeWidget(self)
        self._errors.setHeaderLabels(["Error", "Count"])
        self._errors.setUniformRowHeights(True)
        self._traceback = QPlainTextEdit(self)
        self._traceback.setReadOnly(True)
        self._traceback.setLineWrapMode(QPlainTextEdit.NoWrap)
        errors = QSplitter(Qt.Vertical, self)
        errors.addWidget(self._errors)
        errors.addWidget(self._traceback)
        self._tabs.addTab(self._tasks, "Running")
        self._tabs.addTab(errors, "Errors")
        self._errors.currentItemChanged.connect(self._show_traceback)

        lower = QSplitter(Qt.Vertical, self)
        grid_box = QWidget(self)
        grid_layout = QVBoxLayout(grid_box)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self._legend)
        grid_layout.addWidget(self._grid, 1)
        lower.addWidget(grid_box)
        lower.addWidget(self._tabs)
        lower.setSizes([140, 260])
        box.addWidget(lower, 1)
        self.set_job(None)

    def set_job(self, job: JobMonitorState | None) -> None:
        for widget in (self._badge, self._chip, self._meta):
            widget.setVisible(job is not None)
        if job is None:
            self._name.setText("Select a job")
            for kpi in (self._left, self._progress, self._speed, self._failed):
                kpi.set("—")
            self._bar.parts, self._trend.values = (0, 0, 0, 0), []
            self._grid.set_states(None, 0)
            self._grid.setVisible(False)
            self._legend.setText("")
            self._tasks.clear()
            self._tabs.setTabText(0, "Running")
            self.set_failures([], 0)
            return
        self._name.setText(job.name or job.job_id[:8])
        hue = status_color(job.status)
        self._badge.setText(job.status.replace("_", " "))
        self._badge.setStyleSheet(f"color:{hue}; border:1px solid {hue}; border-radius:8px; padding:0 6px; font-size:10px;")
        self._chip.setText(job.executor or "")
        self._chip.setVisible(bool(job.executor))
        self._meta.setText(self._meta_text(job))

        total = job.chunks_total
        pending = max(0, total - job.chunks_settled - job.chunks_running)
        left = job.seconds_left
        if job.is_terminal:
            self._left.set("—", "ended " + job.finished_at.strftime("%H:%M") if job.finished_at else "ended")
        elif left is None:
            self._left.set("…", "calculating")
        else:
            self._left.set(format_duration(left), f"ends ~{_clock(left)}")
        pct = 100.0 * job.chunks_settled / total if total else job.progress
        self._progress.set(f"{pct:.0f}%", f"{job.chunks_done:,} done · {job.chunks_running:,} running · "
                                          f"{job.chunks_failed:,} failed · {pending:,} pending")
        self._bar.parts = (job.chunks_done, job.chunks_running, job.chunks_failed, pending)
        self._bar.update()
        cpu = f" · {job.cpu_used:,} CPU" if job.cpu_used else ""
        self._speed.set(format_speed(job.throughput_eps),
                        f"{job.tasks_running:,} tasks{cpu}" if not job.is_terminal else "mean over the run")
        self._trend.values = job.throughput_history
        self._trend.update()
        self._failed.set(f"{job.chunks_failed:,}", f"{job.chunks_retried:,} retried",
                         P["error"] if job.chunks_failed else None)

        self._grid.setVisible(job.chunk_states is not None)
        self._grid.set_states(job.chunk_states, total)
        if job.chunk_states is None:
            self._legend.setText("A cell per chunk is kept only while the job runs in this session.")
        else:
            c = _colors()
            self._legend.setText("  ".join(f"<span style='color:{c[rank].name()}'>■</span> {_STATES[rank]}"
                                           for rank in (1, 2, 3, 0)) + f"  ·  {max(len(job.chunk_states), total):,} chunks")
        self._set_tasks(job)

    def _meta_text(self, job: JobMonitorState) -> str:
        said = [job.job_id[:12]]
        if job.started_at is not None:
            end = job.finished_at or datetime.now()
            said.append(f"started {job.started_at:%Y-%m-%d %H:%M} · ran {format_duration((end - job.started_at).total_seconds())}")
        if job.peak_mem_mb:
            said.append(f"peak {job.peak_mem_mb:,} MB")
        if job.engine_id is None:
            said.append("read from the journal: not run by this session")
        return " · ".join(said)

    def _set_tasks(self, job: JobMonitorState) -> None:
        tasks = job.tasks
        median = statistics.median(task.seconds for task in tasks) if len(tasks) >= 3 else None
        warn = QColor(P["warn"])
        while self._tasks.topLevelItemCount() > len(tasks):
            self._tasks.takeTopLevelItem(self._tasks.topLevelItemCount() - 1)
        while self._tasks.topLevelItemCount() < len(tasks):
            self._tasks.addTopLevelItem(QTreeWidgetItem())
        for at, task in enumerate(tasks):
            item = self._tasks.topLevelItem(at)
            what = task.input + (f" +{task.chunks - 1}" if task.chunks > 1 else "")
            for column, text in enumerate((what, task.host or "", str(task.attempt), format_duration(task.seconds),
                                           "—" if task.progress is None else f"{task.progress:.0f}%")):
                item.setText(column, text)
            slow = median is not None and median > 0 and task.seconds > SLOW * median
            for column in range(5):
                item.setForeground(column, warn if slow else self._tasks.palette().color(QPalette.ColorRole.Text))
            item.setToolTip(0, f"slow: {task.seconds / median:.1f}× the median" if slow else task.input)
        self._tabs.setTabText(0, f"Running ({len(tasks)})" if tasks else "Running")

    def set_failures(self, failures: list[FailureState], failed: int, job_error: str = "") -> None:
        """The failed chunks read from the journal, grouped by their message; `failed` is how many there are."""
        self._errors.clear()
        self._traceback.setPlainText("")
        groups: dict[str, list[FailureState]] = {}
        if job_error:
            groups[f"job: {reason(job_error)}"] = [FailureState(0, job_error, "the job")]
        for failure in failures:
            groups.setdefault(reason(failure.error) or "failed (no message recorded)", []).append(failure)
        for said, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            group = QTreeWidgetItem([said, f"{len(members):,}"])
            group.setData(0, Qt.UserRole, members[0].error)
            group.setToolTip(0, said)
            for failure in members:
                child = QTreeWidgetItem([f"{failure.input or 'chunk'} · attempt {failure.attempt}", ""])
                child.setData(0, Qt.UserRole, failure.error)
                group.addChild(child)
            self._errors.addTopLevelItem(group)
        if failed > len(failures):
            self._errors.addTopLevelItem(QTreeWidgetItem([f"… {failed - len(failures):,} more failed chunks not read", ""]))
        if self._errors.topLevelItemCount():
            self._errors.setCurrentItem(self._errors.topLevelItem(0))
        self._errors.resizeColumnToContents(1)
        count = failed + bool(job_error)
        self._tabs.setTabText(1, f"Errors ({count:,})" if count else "Errors")

    def _show_traceback(self, item, _previous=None) -> None:
        self._traceback.setPlainText("" if item is None else str(item.data(0, Qt.UserRole) or ""))


__all__ = ["ChunkGrid", "JobDetail", "layout_cells", "ranks", "reason"]
