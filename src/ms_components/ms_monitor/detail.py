"""The selected job: a header, four numbers (ETA, progress, throughput, failures), a cell per
chunk, and its tasks in flight, failures and summary.

The grid shows at most `GRID_MAX` chunks of `JobMonitorState.chunk_states`, a cell each,
column by column. Past that it is a window: when the furthest chunk that began reaches the
window's end, the window moves `GRID_STEP` on, and what it left behind (and what is still ahead)
is said as counts above it, so the cells keep moving while the counts stay exact.
"""
from __future__ import annotations

import statistics
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
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
from ms_components.theme import font

SLOW = 2.5  # a task that has run this many times the median of its job's tasks reads as slow
GRID_MAX = 1000  # cells at most
GRID_STEP = 500  # how far the window moves when the work reaches its end

# ms_flow's chunk byte: 0 pending, 1 running, 2 done, 3 failed
_STATES = ("pending", "running", "done", "failed")
_LEGEND = (2, 1, 3, 0)  # the order they are said in


def reason(text: str) -> str:
    """The semantic message: the last non-empty line of a traceback, the first of anything else."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1] if any(line.startswith("Traceback") for line in lines) else lines[0]


def _pal() -> QPalette:
    app = QApplication.instance()
    return app.palette() if app else QPalette()


def _colors() -> list[QColor]:
    """By chunk byte: pending, running, done, failed."""
    pal = _pal()
    return [pal.color(QPalette.ColorRole.Mid), pal.color(QPalette.ColorRole.Highlight), QColor(P["ok"]), QColor(P["error"])]


def _swatch(color: QColor | str, text: str) -> str:
    return f"<span style='color:{QColor(color).name()}'>■</span>&nbsp;{text}"


def grid_window(states: bytes, start: int) -> int:
    """The first chunk the grid shows, from the one it showed: it only moves on, `GRID_STEP` at
    a time, once the furthest chunk that began reaches the end of `GRID_MAX` cells."""
    n = len(states)
    if n <= GRID_MAX:
        return 0
    head = len(states.rstrip(b"\x00"))  # past the furthest chunk that is not pending
    while head >= start + GRID_MAX and start + GRID_MAX < n:
        start += GRID_STEP
    return min(start, n - GRID_MAX)


def counts(states: bytes) -> list[int]:
    """How many chunks are in each state, by chunk byte."""
    return [states.count(value) for value in range(4)]


def layout_cells(n: int, width: int, height: int) -> tuple[int, int, int]:
    """`(cell px, gap px, rows)`: the biggest cells, 22 px down to 4, that fit `n` column by column."""
    for size in range(22, 3, -1):
        gap = 2 if size >= 10 else 1
        pitch = size + gap
        rows, cols = max(1, (height + gap) // pitch), max(1, (width + gap) // pitch)
        if rows * cols >= n:
            return size, gap, rows
    return 4, 1, max(1, (height + 1) // 5)


class ChunkGrid(QWidget):
    """A rounded cell per chunk of the window, filled column by column."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setMouseTracking(True)
        self.cells, self.first = b"", 0  # the window's bytes, and the chunk number of its first

    def set_cells(self, cells: bytes, first: int) -> None:
        if (cells, first) != (self.cells, self.first):
            self.cells, self.first = cells, first
            self.update()

    def paintEvent(self, _):
        if not self.cells:
            return
        size, gap, rows = layout_cells(len(self.cells), self.width(), self.height())
        pitch, radius = size + gap, 2.0 if size >= 8 else 0.5
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        colors = _colors()
        for value in range(4):  # one brush per state
            p.setBrush(colors[value])
            for at, state in enumerate(self.cells):
                if state == value:
                    p.drawRoundedRect(QRectF(at // rows * pitch, at % rows * pitch, size, size), radius, radius)

    def mouseMoveEvent(self, event):
        if not self.cells:
            return
        size, gap, rows = layout_cells(len(self.cells), self.width(), self.height())
        pitch = size + gap
        x, y = int(event.position().x()) // pitch, int(event.position().y()) // pitch
        at = x * rows + y
        if y >= rows or not 0 <= at < len(self.cells):
            QToolTip.hideText()
            return
        QToolTip.showText(event.globalPosition().toPoint(), f"chunk {self.first + at + 1:,}: {_STATES[self.cells[at]]}", self)


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
        colors = _colors()
        p.fillRect(r, colors[0])
        total, x = sum(self.parts), 0.0
        if not total:
            return
        for part, hue in zip(self.parts, (colors[2], colors[1], colors[3])):
            w = r.width() * part / total
            p.fillRect(QRectF(x, 0, w, r.height()), hue)
            x += w


class _Trend(QWidget):
    """The speed over the last minutes, its own scale: an area and its line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(84, 30)
        self.values: list[float] = []

    def paintEvent(self, _):
        if len(self.values) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h, top = self.width(), self.height() - 1, max(self.values) or 1.0
        step = w / (len(self.values) - 1)
        points = [QPointF(i * step, h - (h - 2) * v / top) for i, v in enumerate(self.values)]
        accent = _pal().color(QPalette.ColorRole.Highlight)
        area = QPainterPath(QPointF(0, h))
        for point in points:
            area.lineTo(point)
        area.lineTo(QPointF(w, h))
        fill = QColor(accent)
        fill.setAlphaF(0.18)
        p.fillPath(area, fill)
        p.setPen(QPen(accent, 1.4))
        p.drawPolyline(points)


def _muted(text: str = "", px: float = 11.5) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color:palette(placeholder-text); font-size:{px}px;")
    return label


class _Kpi(QFrame):
    """A card: a title (and something at its right), a big value (and something at its right),
    a line under it. A bar of the accent color runs down its left edge."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.accent: str | None = None
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(15, 8, 13, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(2)
        self.head = QLabel(title.upper(), self)
        head_font = QFont(self.head.font())
        head_font.setLetterSpacing(QFont.PercentageSpacing, 108)
        self.head.setFont(head_font)
        self.head.setStyleSheet("color:palette(placeholder-text); font-size:10.5px; font-weight:600;")
        self.value = QLabel("—", self)
        self.unit = _muted("", 12.5)
        self.sub = _muted()
        value_row = QHBoxLayout()
        value_row.setSpacing(5)
        value_row.addWidget(self.value, 0, Qt.AlignBaseline)
        value_row.addWidget(self.unit, 0, Qt.AlignBaseline)
        value_row.addStretch(1)
        self.grid.addWidget(self.head, 0, 0)
        self.grid.addLayout(value_row, 1, 0)
        self.grid.addWidget(self.sub, 2, 0, 1, 2)
        self.grid.setColumnStretch(0, 1)
        self.set("—")

    def set(self, value: str, sub: str = "", accent: str | None = None, *, color: str | None = None, unit: str = "") -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"font-size:22px; font-weight:600;{f' color:{color};' if color else ''}")
        self.unit.setText(unit)
        self.sub.setText(sub)
        if accent != self.accent:
            self.accent = accent
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = _pal()
        p.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 1))
        p.setBrush(pal.color(QPalette.ColorRole.Base))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        if self.accent:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(self.accent))
            p.drawRoundedRect(QRectF(1, 9, 3, self.height() - 18), 1.5, 1.5)


class _ErrorBox(QStyledItemDelegate):
    """A group of failures: how many and the message, then its share of the failures."""

    def sizeHint(self, option, index) -> QSize:
        return QSize(200, 50 if index.data(Qt.UserRole + 1) else 30)

    def paint(self, p: QPainter, option, index) -> None:
        many, share = index.data(Qt.UserRole + 1), index.data(Qt.UserRole + 2)
        pal = _pal()
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(1, 3, -1, -3)
        selected = bool(option.state & QStyle.State_Selected)
        p.setPen(QPen(pal.color(QPalette.ColorRole.Highlight) if selected else pal.color(QPalette.ColorRole.Mid), 1))
        p.setBrush(pal.color(QPalette.ColorRole.AlternateBase))
        p.drawRoundedRect(r, 6, 6)
        x, line = r.left() + 10, QRectF(r.left() + 10, r.top() + 4, r.width() - 20, 20)
        if many:
            bold = QFont(option.font)
            bold.setBold(True)
            p.setFont(bold)
            p.setPen(QColor(P["error"]))
            said = f"×{many:,}"
            p.drawText(line, Qt.AlignLeft | Qt.AlignVCenter, said)
            x += p.fontMetrics().horizontalAdvance(said) + 8
        mono = font(mono=True)
        p.setFont(mono)
        p.setPen(pal.color(QPalette.ColorRole.Text) if many else pal.color(QPalette.ColorRole.PlaceholderText))
        room = QRectF(x, line.top(), r.right() - 10 - x, 20)
        p.drawText(room, Qt.AlignLeft | Qt.AlignVCenter, p.fontMetrics().elidedText(index.data(Qt.DisplayRole), Qt.ElideRight, int(room.width())))
        if many:
            p.setFont(option.font)
            p.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
            p.drawText(QRectF(r.left() + 10, r.top() + 24, r.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, share)
        p.restore()


def _clock(seconds_from_now: float) -> str:
    return datetime.fromtimestamp(datetime.now().timestamp() + seconds_from_now).strftime("%H:%M")


def _panel(parent=None) -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName("panel")
    return frame


class JobDetail(QWidget):
    """The selected job. `set_job` each poll; `set_failures` when its failures change.
    `executor_clicked` says the executor chip was clicked."""

    executor_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        self._job: JobMonitorState | None = None
        self._start: tuple[str | None, int] = (None, 0)  # the grid's window, by job
        self._error_types = 0

        head = _panel(self)
        head.setFixedHeight(44)
        row = QHBoxLayout(head)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(8)
        self._swatch = QLabel(head)
        self._swatch.setFixedSize(11, 11)
        self._name = QLabel("Select a job", head)
        self._name.setStyleSheet("font-size:14px; font-weight:650;")
        self._badge = QLabel(head)
        self._on = _muted("on", 12)
        self._chip = QPushButton(head)
        self._chip.setObjectName("xchip")
        self._chip.setCursor(Qt.PointingHandCursor)
        self._chip.setToolTip("Only the jobs of this executor")
        self._chip.clicked.connect(lambda: self.executor_clicked.emit(self._chip.text()))
        self._meta = _muted("", 11.5)
        for widget in (self._swatch, self._name, self._badge, self._on, self._chip):
            row.addWidget(widget, 0, Qt.AlignVCenter)
        row.addStretch(1)
        row.addWidget(self._meta)
        box.addWidget(head)

        kpis = QHBoxLayout()
        kpis.setSpacing(10)
        self._left = _Kpi("ETA", self)
        self._progress = _Kpi("Progress", self)
        self._pct = QLabel(self._progress)
        self._progress.grid.addWidget(self._pct, 0, 1, Qt.AlignRight)
        self._legend = _muted("", 11.5)
        self._progress.grid.addWidget(self._legend, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
        self._bar = _StackBar(self._progress)
        self._progress.grid.addWidget(self._bar, 3, 0, 1, 2)
        self._speed = _Kpi("Throughput", self)
        self._trend = _Trend(self._speed)
        self._speed.grid.addWidget(self._trend, 0, 1, 2, 1, Qt.AlignRight | Qt.AlignTop)
        self._failed = _Kpi("Failures", self)
        for kpi, stretch in ((self._left, 9), (self._progress, 27), (self._speed, 12), (self._failed, 9)):
            kpi.setFixedHeight(80)
            kpis.addWidget(kpi, stretch)
        box.addLayout(kpis)

        work = QSplitter(Qt.Horizontal, self)
        work.setHandleWidth(10)
        grid_panel = _panel(work)
        grid_box = QVBoxLayout(grid_panel)
        grid_box.setContentsMargins(14, 10, 14, 10)
        grid_box.setSpacing(8)
        grid_head = QHBoxLayout()
        title = QLabel("Chunks", grid_panel)
        title.setStyleSheet("font-weight:600; font-size:13px;")
        self._grid_meta = _muted()
        grid_head.addWidget(title)
        grid_head.addStretch(1)
        grid_head.addWidget(self._grid_meta)
        grid_box.addLayout(grid_head)
        self._before = _muted("", 11.5)
        self._before.setTextFormat(Qt.RichText)
        grid_box.addWidget(self._before)
        self._grid = ChunkGrid(grid_panel)
        grid_box.addWidget(self._grid, 1)
        self._grid_note = _muted("", 11.5)
        self._grid_note.setWordWrap(True)
        grid_box.addWidget(self._grid_note, 1)
        foot = QHBoxLayout()
        self._after = _muted("", 11.5)
        self._grid_legend = _muted("", 11.5)
        foot.addWidget(self._after)
        foot.addStretch(1)
        foot.addWidget(self._grid_legend)
        grid_box.addLayout(foot)

        side = _panel(work)
        side_box = QVBoxLayout(side)
        side_box.setContentsMargins(10, 10, 10, 10)
        self._tabs = QTabWidget(side)
        self._tabs.setObjectName("pills")
        self._tabs.setDocumentMode(True)
        self._tabs.setUsesScrollButtons(False)
        self._tabs.tabBar().setElideMode(Qt.ElideNone)
        self._tabs.tabBar().setExpanding(False)
        self._tab_meta = _muted("", 11.5)
        self._tab_meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._tab_meta.setContentsMargins(0, 0, 4, 2)
        self._tabs.setCornerWidget(self._tab_meta, Qt.TopRightCorner)
        side_box.addWidget(self._tabs)

        self._tasks = QTreeWidget(side)
        self._tasks.setHeaderLabels(["Input", "Host", "Attempt", "Elapsed", "Progress"])
        self._tasks.setRootIsDecorated(False)
        self._tasks.setUniformRowHeights(True)
        self._tasks.setFrameShape(QFrame.NoFrame)
        self._tasks.header().setStretchLastSection(False)
        self._tasks.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._tasks.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._errors = QListWidget(side)
        self._errors.setItemDelegate(_ErrorBox(self._errors))
        self._errors.setFrameShape(QFrame.NoFrame)
        self._errors.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._errors.setStyleSheet("QListWidget { background: transparent; }")
        self._traceback = QPlainTextEdit(side)
        self._traceback.setReadOnly(True)
        self._traceback.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._traceback.setFont(font(mono=True))
        errors = QSplitter(Qt.Vertical, side)
        errors.addWidget(self._errors)
        errors.addWidget(self._traceback)
        errors.setSizes([260, 140])
        self._summary = QWidget(side)
        self._facts = QGridLayout(self._summary)
        self._facts.setContentsMargins(6, 8, 6, 8)
        self._facts.setVerticalSpacing(7)
        self._facts.setColumnStretch(1, 1)
        self._facts.setRowStretch(len(self._FACTS), 1)
        self._build_summary()
        self._tabs.addTab(self._tasks, "Running")
        self._tabs.addTab(errors, "Errors")
        self._tabs.addTab(self._summary, "Summary")
        self._errors.currentItemChanged.connect(self._show_traceback)

        work.addWidget(grid_panel)
        work.addWidget(side)
        work.setStretchFactor(0, 1)
        work.setSizes([640, 450])
        box.addWidget(work, 1)
        self.set_job(None)

    def set_job(self, job: JobMonitorState | None) -> None:
        self._job = job
        for widget in (self._swatch, self._badge, self._on, self._chip, self._meta):
            widget.setVisible(job is not None)
        if job is None:
            self._name.setText("Select a job")
            for kpi in (self._left, self._progress, self._speed, self._failed):
                kpi.set("—")
            self._pct.setText("")
            self._legend.setText("")
            self._bar.parts, self._trend.values = (0, 0, 0, 0), []
            self._show_grid(None)
            self._tasks.clear()
            self._tabs.setTabText(0, "Running")
            self._tab_meta.setText("")
            self.set_failures([], 0)
            self._set_summary(None)
            return
        hue = status_color(job.status)
        self._name.setText(job.name or job.job_id[:8])
        self._badge.setText(job.status.replace("_", " ").upper())
        back = QColor(hue)
        self._badge.setStyleSheet(f"color:{hue}; background:rgba({back.red()},{back.green()},{back.blue()},30);"
                                  " border-radius:4px; padding:1px 6px; font-size:10.5px; font-weight:650;")
        self._chip.setText(job.executor or "")
        self._chip.setVisible(bool(job.executor))
        self._on.setVisible(bool(job.executor))
        self._meta.setText(self._meta_text(job))

        total = job.chunks_total
        pending = max(0, total - job.chunks_settled - job.chunks_running)
        left = job.seconds_left
        if job.is_terminal:
            self._left.set("—", "ended " + job.finished_at.strftime("%H:%M") if job.finished_at else "ended", hue)
        elif left is None:
            self._left.set("…", "calculating", hue)
        else:
            self._left.set(format_duration(left), f"≈ {_clock(left)} · 5-min rate", hue)
        pct = 100.0 * job.chunks_settled / total if total else job.progress
        accent = _pal().color(QPalette.ColorRole.Highlight).name()
        self._progress.set(f"{job.chunks_done:,} / {total:,}" if total else f"{job.chunks_done:,}", "", accent)
        self._pct.setText(f"{pct:.1f}%" if pct < 10 else f"{pct:.0f}%")
        self._pct.setStyleSheet(f"color:{accent}; font-weight:650; font-size:12px;")
        colors = _colors()
        said = [(job.chunks_done, 2, "done"), (job.chunks_running, 1, "running"), (job.chunks_failed, 3, "failed"),
                (pending, 0, "pending")]
        self._legend.setText("&nbsp;&nbsp;&nbsp;".join(_swatch(colors[at], f"{many:,} {what}") for many, at, what in said if many))
        self._bar.parts = (job.chunks_done, job.chunks_running, job.chunks_failed, pending)
        self._bar.update()
        speed = format_speed(job.throughput_eps)
        number, _, unit = speed.partition("/")
        cpu = f" · {job.cpu_used:,} CPUs" if job.cpu_used else ""
        self._speed.set(number, f"{job.tasks_running:,} tasks{cpu}" if not job.is_terminal else "mean over the run",
                        accent, unit=f"chunks/{unit}" if unit else "")
        self._trend.values = job.throughput_history
        self._trend.update()
        self._set_failed_kpi()

        self._show_grid(job)
        self._set_tasks(job)
        self._set_summary(job)

    def set_color(self, color: str) -> None:
        """The job's own color, as the list paints it."""
        self._swatch.setStyleSheet(f"background:{color}; border-radius:3px;")

    def _meta_text(self, job: JobMonitorState) -> str:
        said = []
        if job.started_at is not None:
            end = job.finished_at or datetime.now()
            said.append(f"started {job.started_at:%H:%M} · elapsed {format_duration((end - job.started_at).total_seconds())}")
        if not job.is_terminal and job.tasks_running:
            said.append(f"{job.tasks_running:,} tasks" + (f" · {job.cpu_used:,} CPUs" if job.cpu_used else ""))
        if job.engine_id is None:
            said.append("not run by this session")
        return " · ".join(said)

    def _show_grid(self, job: JobMonitorState | None) -> None:
        states = None if job is None else job.chunk_states
        self._grid.setVisible(states is not None)
        self._grid_note.setVisible(states is None)
        colors = _colors()
        if states is None:
            self._grid.set_cells(b"", 0)
            self._grid_meta.setText("" if job is None else f"{job.chunks_total:,} chunks")
            self._grid_note.setText("" if job is None else "A cell per chunk is kept only while the job runs in this session.")
            self._before.setText("")
            self._after.setText("")
            self._grid_legend.setText("")
            return
        states = bytes(states) + bytes(max(0, job.chunks_total - len(states)))  # not given yet: pending
        held_for, start = self._start
        start = grid_window(states, start if held_for == job.job_id else 0)
        self._start = (job.job_id, start)
        end = min(len(states), start + GRID_MAX)
        self._grid.set_cells(states[start:end], start)
        self._grid_meta.setText(f"{len(states):,} chunks · 1 cell = 1 chunk"
                                + (f" · showing {start + 1:,}–{end:,}" if len(states) > GRID_MAX else ""))
        self._before.setText(self._said(states[:start], f"before {start + 1:,}", colors))
        self._before.setVisible(start > 0)
        self._after.setText(self._said(states[end:], "after", colors))
        self._grid_legend.setText("&nbsp;&nbsp;&nbsp;".join(_swatch(colors[at], _STATES[at]) for at in (0, 2, 1, 3)))

    @staticmethod
    def _said(states: bytes, where: str, colors: list[QColor]) -> str:
        """`+1,000 done · +200 failed` of the chunks out of the window."""
        if not states:
            return ""
        many = counts(states)
        return f"{where}: " + "&nbsp;&nbsp;".join(
            f"<span style='color:{colors[at].name() if at else 'palette(placeholder-text)'}'>+{many[at]:,} {_STATES[at]}</span>"
            for at in _LEGEND if many[at])

    def _set_tasks(self, job: JobMonitorState) -> None:
        tasks = job.tasks
        median = statistics.median(task.seconds for task in tasks) if len(tasks) >= 3 else None
        warn = QColor(P["warn"])
        while self._tasks.topLevelItemCount() > len(tasks):
            self._tasks.takeTopLevelItem(self._tasks.topLevelItemCount() - 1)
        while self._tasks.topLevelItemCount() < len(tasks):
            self._tasks.addTopLevelItem(QTreeWidgetItem())
        slow = 0
        for at, task in enumerate(tasks):
            item = self._tasks.topLevelItem(at)
            what = task.input + (f" +{task.chunks - 1}" if task.chunks > 1 else "")
            for column, text in enumerate((what, task.host or "", str(task.attempt), format_duration(task.seconds),
                                           "—" if task.progress is None else f"{task.progress:.0f}%")):
                item.setText(column, text)
            late = median is not None and median > 0 and task.seconds > SLOW * median
            slow += late
            for column in range(5):
                item.setForeground(column, warn if late else self._tasks.palette().color(QPalette.ColorRole.Text))
            item.setToolTip(0, f"slow: {task.seconds / median:.1f}× the median" if late else task.input)
        self._tabs.setTabText(0, f"Running  {len(tasks)}" if tasks else "Running")
        said = [f"{len(tasks)} running"] if tasks else []
        if median is not None:
            said.append(f"median {format_duration(median)}")
        if slow:
            said.append(f"<span style='color:{warn.name()}'>⚠ {slow} slow</span>")
        self._tab_meta.setText(" · ".join(said))

    def _set_failed_kpi(self) -> None:
        job = self._job
        if job is None:
            return
        failed = job.chunks_failed
        types = f"{self._error_types:,} error type{'s' * (self._error_types != 1)}" if self._error_types else ""
        retried = f"{job.chunks_retried:,} retried" if job.chunks_retried else ""
        self._failed.set(f"{failed:,}", " · ".join(x for x in (types, retried) if x) or ("no errors" if not failed else ""),
                         P["error"] if failed else P["ok"], color=P["error"] if failed else None)

    def set_failures(self, failures: list[FailureState], failed: int, job_error: str = "") -> None:
        """The failed chunks read from the journal, grouped by their message; `failed` is how many there are."""
        self._errors.clear()
        self._traceback.setPlainText("")
        groups: dict[str, list[FailureState]] = {}
        if job_error:
            groups[f"job: {reason(job_error)}"] = [FailureState(0, job_error, "the job")]
        for failure in failures:
            groups.setdefault(reason(failure.error) or "failed (no message recorded)", []).append(failure)
        read = max(1, sum(len(members) for members in groups.values()))
        for said, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            item = QListWidgetItem(said)
            item.setData(Qt.UserRole, members[0].error)
            item.setData(Qt.UserRole + 1, len(members))
            item.setData(Qt.UserRole + 2, f"{100 * len(members) / read:.0f}% of the failures read")
            shown = ", ".join(f"{m.input or 'chunk'} (attempt {m.attempt})" for m in members[:12])
            item.setToolTip(f"{said}\n{shown}" + (f", … {len(members) - 12:,} more" if len(members) > 12 else ""))
            self._errors.addItem(item)
        self._error_types = len(groups)
        if failed > len(failures):
            self._errors.addItem(QListWidgetItem(f"… {failed - len(failures):,} more failed chunks not read"))
        if self._errors.count():
            self._errors.setCurrentRow(0)
        count = failed + bool(job_error)
        self._tabs.setTabText(1, f"Errors  {count:,}" if count else "Errors")
        self._tabs.tabBar().setTabTextColor(1, QColor(P["error"]) if count else _pal().color(QPalette.ColorRole.Text))
        self._set_failed_kpi()

    def _show_traceback(self, item, _previous=None) -> None:
        self._traceback.setPlainText("" if item is None else str(item.data(Qt.UserRole) or ""))

    _FACTS = ("key", "status", "executor", "started", "finished", "elapsed", "chunks", "retried", "throughput",
              "peak memory", "CPU", "GPU", "in flight", "errors")

    def _build_summary(self) -> None:
        self._fact: dict[str, QLabel] = {}
        for row, key in enumerate(self._FACTS):
            self._facts.addWidget(_muted(key, 12), row, 0, Qt.AlignTop)
            self._fact[key] = label = QLabel(self._summary)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)
            self._facts.addWidget(label, row, 1)
        self._fact["key"].setFont(font(mono=True))
        copy = QPushButton("copy", self._summary)
        copy.setObjectName("xchip")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._fact["key"].text()))
        self._facts.addWidget(copy, 0, 2)

    def _set_summary(self, job: JobMonitorState | None) -> None:
        if job is None:
            for label in self._fact.values():
                label.setText("")
            return
        end = job.finished_at or datetime.now()
        values = (
            job.job_id,
            job.status.replace("_", " "),
            job.executor or "—",
            f"{job.started_at:%Y-%m-%d %H:%M:%S}" if job.started_at else "—",
            f"{job.finished_at:%Y-%m-%d %H:%M:%S}" if job.finished_at else "—",
            format_duration((end - job.started_at).total_seconds()) if job.started_at else "—",
            f"{job.chunks_done:,} done · {job.chunks_failed:,} failed · {job.chunks_total:,} in all",
            f"{job.chunks_retried:,}",
            format_speed(job.throughput_eps) + ("" if job.is_terminal else " · last 5 min"),
            f"{job.peak_mem_mb:,} MB" if job.peak_mem_mb else "—",
            *_used(job, (end - job.started_at).total_seconds() if job.started_at else 0.0),
            f"{job.tasks_running:,} tasks · {job.cpu_used:,} CPUs" if not job.is_terminal else "—",
            f"{self._error_types:,} types" if self._error_types else "none",
        )
        for key, value in zip(self._FACTS, values):
            self._fact[key].setText(value)


def _used(job: JobMonitorState, seconds: float) -> tuple[str, str]:
    """The CPU and GPU lines of a job's summary: what it held, and what its cards did."""
    usage = job.usage
    if not usage:
        return "—", "—"
    cpu = (f"{usage['cpu_s'] / 3600:,.2f} CPU·h · {usage['cpu_s'] / seconds:,.1f} held on average"
           f" · {usage['peak_cpu']:g} at most") if usage.get("peak_cpu") and seconds > 0 else "—"
    gpu = "—"
    if usage.get("peak_gpu"):
        gpu = f"{usage['gpu_s'] / 3600:,.2f} GPU·h · {usage['peak_gpu']:g} at most"
        if usage.get("vram_mb") is not None:
            gpu += f" · {usage['vram_mb']:,} MB VRAM at most · {usage['gpu_util']:.0f} % busy on average (whole machine)"
    return cpu, gpu


__all__ = ["ChunkGrid", "GRID_MAX", "GRID_STEP", "JobDetail", "counts", "grid_window", "layout_cells", "reason"]
