"""Per-executor mini-cards for the monitor header.

Surfaces ExecutorMonitorState fields the old single-line summary hid: backend,
mode, running chunks, CPU used/reserved and per-executor health. Rebuilt on each
snapshot — executors are few (typically 1-3), so a full rebuild is cheap.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ms_components.ms_monitor.job_cards import ExecutorBadge
from ms_components.ms_monitor.models import ExecutorMonitorState
from ms_components.ms_monitor.palette import P


class _HealthDot(QWidget):
    def __init__(self, ok: bool, parent=None):
        super().__init__(parent)
        self._color = P["ok"] if ok else P["error"]
        self.setFixedSize(10, 10)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(self._color)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(1, 1, 8, 8)


def _executor_ok(ex: ExecutorMonitorState) -> bool:
    return bool(dict(ex.health or {}).get("ok", True))


class ExecutorCard(QFrame):
    def __init__(self, ex: ExecutorMonitorState, parent=None):
        super().__init__(parent)
        self.setObjectName("executorCard")
        self.setStyleSheet(
            f"""
            QFrame#executorCard {{
                background: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; }}
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(_HealthDot(_executor_ok(ex), self), 0, Qt.AlignVCenter)
        name = QLabel(ex.name or "executor", self)
        name.setStyleSheet("color:palette(text); font-size:12px; font-weight:600;")
        top.addWidget(name)
        top.addWidget(ExecutorBadge(ex.backend or ex.name, self))
        top.addStretch(1)
        lay.addLayout(top)

        # Loky/dynamic executors don't pre-reserve CPUs (reserved_cpu == 0), so
        # "used/0 cpu" reads as a bug. Show the reservation only when there is one.
        if ex.reserved_cpu > 0:
            used = "-" if ex.used_cpu is None else str(ex.used_cpu)
            cpu = f"{used}/{ex.reserved_cpu} cpu"
        elif ex.used_cpu is not None:
            cpu = f"{ex.used_cpu} cpu"
        else:
            cpu = "-"
        stats = QLabel(
            f"{ex.active_jobs} jobs · {ex.running_chunks} chunks · {cpu}", self
        )
        stats.setStyleSheet("color:palette(placeholder-text); font-size:11px;")
        lay.addWidget(stats)

        meta_bits = [b for b in (ex.mode, ex.local_resource_accounting) if b and b != "none"]
        if ex.remote_backend:
            meta_bits.append("remote")
        if meta_bits:
            meta = QLabel(" · ".join(meta_bits), self)
            meta.setStyleSheet("color:palette(placeholder-text); font-size:10px;")
            lay.addWidget(meta)


class ExecutorPanel(QFrame):
    """Horizontal strip of ExecutorCards inside a titled panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 10)
        outer.setSpacing(6)
        header = QHBoxLayout()
        self._title = QLabel("Executors", self)
        self._title.setStyleSheet(
            f"color:palette(placeholder-text); font-size:10px; font-weight:600; letter-spacing:0.5px;"
        )
        header.addWidget(self._title)
        header.addStretch(1)
        # Global token pool of the scheduler (CPU always; GPU when present).
        self._resources = QLabel("", self)
        self._resources.setStyleSheet("color:palette(text); font-size:11px; font-weight:600;")
        self._resources.setVisible(False)
        header.addWidget(self._resources)
        outer.addLayout(header)
        self._row = QHBoxLayout()
        self._row.setSpacing(8)
        self._empty = QLabel("No executors", self)
        self._empty.setStyleSheet("color:palette(placeholder-text); font-size:12px;")
        self._row.addWidget(self._empty)
        self._row.addStretch(1)
        outer.addLayout(self._row)

    def set_executors(self, executors: list[ExecutorMonitorState]) -> None:
        # Clear old cards (keep the trailing stretch).
        while self._row.count():
            item = self._row.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._empty:
                w.deleteLater()
        self._empty.setVisible(not executors)
        if not executors:
            self._row.addWidget(self._empty)
            self._row.addStretch(1)
            return
        self._title.setText(f"Executors · {len(executors)}")
        for ex in executors:
            self._row.addWidget(ExecutorCard(ex, self))
        self._row.addStretch(1)

    def set_resources(self, resources) -> None:
        """Show 'CPU used/total · GPU used/total' for the global pool; hidden without CPU."""
        if resources is None or int(getattr(resources, "cpu_total", 0)) <= 0:
            self._resources.setVisible(False)
            return
        text = f"⚡ CPU {resources.cpu_used}/{resources.cpu_total}"
        if int(getattr(resources, "gpu_total", 0)) > 0:
            text += f" · GPU {resources.gpu_used}/{resources.gpu_total}"
        self._resources.setText(text)
        self._resources.setVisible(True)

    def clear(self) -> None:
        self.set_executors([])
        self.set_resources(None)
        self._title.setText("Executors")
