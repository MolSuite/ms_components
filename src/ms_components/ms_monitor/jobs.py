"""The job list of the monitor: one painted row per job, and the bar the rest of the app reuses.

A row says the name, the failures, the status, the executor, how far it is (done and failed
apart) and the time left at the speed of the last minutes. Active jobs come first.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPalette, QPen
from PySide6.QtWidgets import QAbstractItemView, QApplication, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate, QWidget

from ms_components.ms_monitor.formatting import format_duration
from ms_components.ms_monitor.models import JobMonitorState
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


def counts_label(job: JobMonitorState) -> str:
    """`done/total · time left`, as a row and the detail say it."""
    total = f"{job.chunks_total:,}" if job.chunks_total else "?"
    left = job.seconds_left
    tail = "" if job.is_terminal else " · calculating…" if left is None else f" · {format_duration(left)} left"
    return f"{job.chunks_done:,}/{total}{tail}"


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



_ROLE = Qt.UserRole


class _JobRow(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        return QSize(200, 50)

    def paint(self, p: QPainter, option, index) -> None:
        job: JobMonitorState = index.data(_ROLE)
        if job is None:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        pal = QApplication.palette()  # the list's own is bent by its transparent stylesheet
        r = QRectF(option.rect).adjusted(2, 2, -2, -2)
        if option.state & QStyle.State_Selected:
            fill = QColor(pal.color(QPalette.ColorRole.Highlight))
            fill.setAlphaF(0.16)
            p.setBrush(fill)
            p.setPen(QPen(pal.color(QPalette.ColorRole.Highlight), 1))
        else:
            p.setBrush(pal.color(QPalette.ColorRole.Base))
            p.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 1))
        p.drawRoundedRect(r, 6, 6)
        x, right, top = r.left() + 8, r.right() - 8, r.top() + 4
        muted, text = pal.color(QPalette.ColorRole.PlaceholderText), pal.color(QPalette.ColorRole.Text)
        font, small = QFont(option.font), QFont(option.font)
        small.setPointSizeF(max(6.0, font.pointSizeF() - 1.5))

        # the status, a badge on the right
        p.setFont(small)
        badge = job.status.replace("_", " ")
        bw = p.fontMetrics().horizontalAdvance(badge) + 12
        brect = QRectF(right - bw, top, bw, 18)
        hue = QColor(status_color(job.status))
        back = QColor(hue)
        back.setAlphaF(0.15)
        p.setPen(Qt.NoPen)
        p.setBrush(back)
        p.drawRoundedRect(brect, 9, 9)
        p.setPen(hue)
        p.drawText(brect, Qt.AlignCenter, badge)

        # the name, and its failures
        font.setBold(True)
        p.setFont(font)
        failed = f"  ⚠ {job.chunks_failed:,}" if job.chunks_failed else ""
        room = brect.left() - x - 6 - (p.fontMetrics().horizontalAdvance(failed) if failed else 0)
        name = p.fontMetrics().elidedText(job.name or job.job_id[:8], Qt.ElideRight, int(max(0, room)))
        p.setPen(text)
        p.drawText(QRectF(x, top, room, 18), Qt.AlignLeft | Qt.AlignVCenter, name)
        if failed:
            p.setPen(QColor(P["error"]))
            p.drawText(QRectF(x + p.fontMetrics().horizontalAdvance(name), top, 200, 18), Qt.AlignLeft | Qt.AlignVCenter, failed)

        # the executor, the bar, the counts
        p.setFont(small)
        line = top + 24
        if job.executor:
            cw = p.fontMetrics().horizontalAdvance(job.executor) + 10
            p.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(x, line, cw, 16), 4, 4)
            p.setPen(muted)
            p.drawText(QRectF(x, line, cw, 16), Qt.AlignCenter, job.executor)
            x += cw + 8
        said = counts_label(job)
        sw = p.fontMetrics().horizontalAdvance(said)
        p.setPen(muted)
        p.drawText(QRectF(right - sw, line, sw, 16), Qt.AlignRight | Qt.AlignVCenter, said)
        bar = QRectF(x, line + 6, max(0.0, right - sw - 10 - x), 4)
        p.setPen(Qt.NoPen)
        p.setBrush(pal.color(QPalette.ColorRole.Window))
        p.drawRoundedRect(bar, 2, 2)
        total = job.chunks_total or 0
        if total and bar.width() > 0:
            done = bar.width() * min(1.0, job.chunks_done / total)
            gone = bar.width() * min(1.0, job.chunks_failed / total)
            p.setBrush(QColor(P["ok"]))
            p.drawRect(QRectF(bar.left(), bar.top(), done, bar.height()))
            p.setBrush(QColor(P["error"]))
            p.drawRect(QRectF(bar.left() + done, bar.top(), gone, bar.height()))
        p.restore()


class JobList(QListWidget):
    """The jobs, as polled, active first. `job_selected` says the job picked by the user."""

    job_selected = Signal(object)  # its job_id, or None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setItemDelegate(_JobRow(self))
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setFrameShape(QListWidget.NoFrame)
        self.setStyleSheet("QListWidget { background: transparent; }")
        self._search, self._status, self._executors = "", "all", None
        self.currentItemChanged.connect(lambda item, _: self.job_selected.emit(None if item is None else item.data(_ROLE).job_id))

    def set_jobs(self, jobs: list[JobMonitorState]) -> None:
        """The rows follow `jobs`; the selected one stays selected while it is listed."""
        chosen = self.selected_job_id()
        if [self.item(i).data(_ROLE).job_id for i in range(self.count())] != [job.job_id for job in jobs]:
            self.blockSignals(True)
            self.clear()
            for job in jobs:
                self.addItem(QListWidgetItem())
            self.blockSignals(False)
        for at, job in enumerate(jobs):
            self.item(at).setData(_ROLE, job)
        self._apply_filters()
        if chosen and self.selected_job_id() != chosen:
            self.select_job(chosen)

    def jobs(self) -> list[JobMonitorState]:
        return [self.item(i).data(_ROLE) for i in range(self.count())]

    def select_job(self, job_id: str | None) -> None:
        """Select `job_id` (None: none) as if clicked."""
        item = next((self.item(i) for i in range(self.count()) if self.item(i).data(_ROLE).job_id == job_id), None)
        if item is None:
            self.clearSelection()
            self.setCurrentItem(None)
        else:
            self.setCurrentItem(item)

    def selected_job_id(self) -> str | None:
        job = self.selected_job()
        return None if job is None else job.job_id

    def selected_job(self) -> JobMonitorState | None:
        item = self.currentItem()
        return None if item is None else item.data(_ROLE)

    def visible_job_ids(self) -> list[str]:
        return [self.item(i).data(_ROLE).job_id for i in range(self.count()) if not self.item(i).isHidden()]

    def set_search_text(self, text: str) -> None:
        self._search = text.strip().lower()
        self._apply_filters()

    def set_status_filter(self, status: str) -> None:
        self._status = status
        self._apply_filters()

    def set_executor_filter(self, executors) -> None:
        """Only the jobs of these executors; None: every job."""
        self._executors = executors
        self._apply_filters()

    def _apply_filters(self) -> None:
        for i in range(self.count()):
            job = self.item(i).data(_ROLE)
            shown = (
                (self._status == "all" or job.status == self._status)
                and (not self._search or self._search in f"{job.name} {job.job_id} {job.status} {job.executor or ''}".lower())
                and (self._executors is None or job.executor in self._executors)
            )
            self.item(i).setHidden(not shown)


__all__ = ["GlowBar", "JobList", "counts_label", "status_color"]
