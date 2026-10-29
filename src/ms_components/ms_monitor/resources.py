"""What the machines that run jobs are using: CPU, memory and GPU of each host, over the last minutes.

A host is read where it is: this machine with `psutil` (or `/proc`), another one through
`ms_env.Host` (the system's `ssh`), with one command that prints `/proc/stat`, `/proc/meminfo`
and `nvidia-smi`. The CPU in use is the change of `/proc/stat` between two reads, so the first
read of a host shows none. Each host is read in its own thread, only while the strip is shown,
every `interval` seconds: a few for this machine, more for one over the network. The login node
of a queue is not read: what it uses says nothing of the nodes its jobs got.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QToolTip, QVBoxLayout, QWidget

# Seconds between two reads, by the kind of executor the host is under; a queue's is not read.
INTERVALS = {"local": 5, "ray": 15}
_HISTORY = 120  # reads kept per host: 10 min of this machine, 30 of one over the network

_GPU_QUERY = "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits"
_SCRIPT = f"head -1 /proc/stat; grep -E '^(MemTotal|MemAvailable):' /proc/meminfo; {_GPU_QUERY} 2>/dev/null || true"


@dataclass(slots=True)
class Sample:
    cpu: float | None = None  # percent of all CPUs; None on the first read
    mem: float = 0.0  # percent
    mem_used_gb: float = 0.0
    mem_total_gb: float = 0.0
    gpus: list[tuple[float, float, float]] = field(default_factory=list)  # (util %, MiB used, MiB total)
    error: str = ""


def parse(text: str, previous: tuple[int, int] | None) -> tuple[Sample, tuple[int, int] | None]:
    """What `_SCRIPT` printed, and the CPU counters it read (busy, total) for the next read."""
    sample, ticks, mem = Sample(), None, {}
    for line in text.splitlines():
        if line.startswith("cpu "):
            values = [int(v) for v in line.split()[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)  # idle + iowait
            ticks = (sum(values) - idle, sum(values))
        elif line.startswith(("MemTotal:", "MemAvailable:")):
            key, value = line.split(":")
            mem[key] = int(value.split()[0]) / 1024**2  # kB → GB
        elif line.count(",") == 2:
            try:
                sample.gpus.append(tuple(float(v) for v in line.split(",")))
            except ValueError:
                pass
    if ticks and previous and ticks[1] > previous[1]:
        sample.cpu = 100.0 * (ticks[0] - previous[0]) / (ticks[1] - previous[1])
    total = mem.get("MemTotal", 0.0)
    if total:
        sample.mem_total_gb, sample.mem_used_gb = total, total - mem.get("MemAvailable", total)
        sample.mem = 100.0 * sample.mem_used_gb / total
    return sample, ticks


def _local_gpus() -> list[tuple[float, float, float]]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(_GPU_QUERY.split(), capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return parse(out, None)[0].gpus


class _Reader:
    """Reads one host; keeps what the next read needs."""

    def __init__(self, address: str):
        self.address, self._ticks, self._psutil = address, None, None
        if not address:
            try:
                import psutil

                psutil.cpu_percent(None)  # the first call only starts the count
                self._psutil = psutil
            except ImportError:
                pass

    def read(self) -> Sample:
        try:
            if self._psutil is not None:
                memory = self._psutil.virtual_memory()
                return Sample(self._psutil.cpu_percent(None), memory.percent, (memory.total - memory.available) / 1024**3,
                              memory.total / 1024**3, _local_gpus())
            from ms_env import Host

            text = Host(self.address or None).run(_SCRIPT, timeout=30).decode(errors="replace")
            sample, self._ticks = parse(text, self._ticks)
            return sample
        except Exception as error:  # noqa: BLE001 - shown on the row of the host
            said = str(error).split("` on ", 1)[-1].strip()  # not the command: where, and what went wrong
            return Sample(error=said.splitlines()[-1] if said else type(error).__name__)


class Sparkline(QWidget):
    """One measure of one host over time, 0-100 %: the line, the area under it and the value now.
    Hovering says the value under the pointer and how long ago it was."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title, self.values, self.interval, self.note = title, deque(maxlen=_HISTORY), 5, ""
        self.setMinimumSize(160, 64)
        self.setMouseTracking(True)

    def push(self, value: float | None, note: str = "") -> None:
        self.values.append(value)
        self.note = note
        self.update()

    def _x(self, index: int) -> float:
        return self.width() * index / max(1, _HISTORY - 1)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        w, h, top = self.width(), self.height(), 14
        p.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 1))
        p.drawLine(0, h - 1, w, h - 1)  # the 0 %, recessive
        p.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
        p.drawText(0, 0, w, top, Qt.AlignLeft | Qt.AlignTop, self.title)
        now = next((v for v in reversed(self.values) if v is not None), None)
        p.setPen(pal.color(QPalette.ColorRole.Text))
        p.drawText(0, 0, w, top, Qt.AlignRight | Qt.AlignTop,
                   "—" if now is None else f"{now:.0f}%" + (f"  {self.note}" if self.note else ""))
        start = _HISTORY - len(self.values)
        points = [QPointF(self._x(start + i), h - 1 - (h - top - 2) * min(100.0, v) / 100.0)
                  for i, v in enumerate(self.values) if v is not None]
        if len(points) < 2:
            return
        accent = pal.color(QPalette.ColorRole.Highlight)
        area = QPainterPath(QPointF(points[0].x(), h - 1))
        for point in points:
            area.lineTo(point)
        area.lineTo(QPointF(points[-1].x(), h - 1))
        fill = QColor(accent)
        fill.setAlphaF(0.18)
        p.fillPath(area, fill)
        p.setPen(QPen(accent, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(points)

    def mouseMoveEvent(self, event):
        index = round(event.position().x() / max(1.0, self.width()) * (_HISTORY - 1)) - (_HISTORY - len(self.values))
        if 0 <= index < len(self.values) and self.values[index] is not None:
            ago = (len(self.values) - 1 - index) * self.interval
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"{self.title}: {self.values[index]:.0f}% · {ago}s ago" if ago else f"{self.title}: {self.values[index]:.0f}% · now", self)
        else:
            QToolTip.hideText()


class _Relay(QObject):
    sampled = Signal(str, object)  # host name, Sample


class _HostCard(QFrame):
    """One host in the strip: CPU over time, memory and GPU now. Checked, it filters the jobs."""

    clicked = Signal(str)

    def __init__(self, name: str, address: str, kind: str, executors: list[str], interval: int | None, parent=None):
        super().__init__(parent)
        self.name, self.executors = name, executors
        self.setObjectName("hostCard")
        self.setProperty("checked", False)
        self.setFixedWidth(230)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{address or 'this computer'} · in {', '.join(executors) or 'no executor'}"
                        + (f" · read every {interval}s" if interval else "") + "\nClick: only its jobs")
        box = QVBoxLayout(self)
        box.setContentsMargins(8, 4, 8, 4)
        box.setSpacing(0)
        title = QLabel(f"<b>{name}</b> <span style='color:palette(placeholder-text)'>{kind}</span>", self)
        box.addWidget(title)
        self.cpu = Sparkline("CPU", self)
        self.cpu.setMinimumSize(120, 36)
        self.cpu.interval = interval or 0
        self.said = QLabel("not read: the login node of a queue" if interval is None else "", self)
        self.said.setStyleSheet("color:palette(placeholder-text); font-size:10px;")
        self.cpu.setVisible(interval is not None)
        box.addWidget(self.cpu)
        box.addWidget(self.said)

    def set_checked(self, checked: bool) -> None:
        self.setProperty("checked", checked)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.name)
        super().mouseReleaseEvent(event)

    def apply(self, sample: Sample) -> None:
        if sample.error:
            self.said.setText(sample.error)
            return
        self.cpu.push(sample.cpu)
        said = f"Mem {sample.mem_used_gb:.1f}/{sample.mem_total_gb:.0f} GB"
        if sample.gpus:  # ponytail: the mean over the cards; one per card when a host has several that differ
            util = sum(g[0] for g in sample.gpus) / len(sample.gpus)
            used, total = sum(g[1] for g in sample.gpus) / 1024, sum(g[2] for g in sample.gpus) / 1024
            said += f" · GPU {util:.0f}% {used:.1f}/{total:.0f} GB" + (f" ({len(sample.gpus)}×)" if len(sample.gpus) > 1 else "")
        self.said.setText(said)


class HostsStrip(QScrollArea):
    """The hosts of the executors that are on, side by side, read while shown. Clicking one keeps
    only the jobs of its executors (`filter_changed` gives their names, or None for all).

    `hosts()` gives `(name, address, kind, executors, interval_s or None)` for each host; by
    default they come from `workspace` (see `workspace_hosts`).
    """

    filter_changed = Signal(object)

    def __init__(self, workspace=None, *, hosts=None, parent=None):
        super().__init__(parent)
        self.hosts = hosts or (lambda: workspace_hosts(workspace))
        self._cards: dict[str, _HostCard] = {}
        self._chosen: str | None = None
        self._stop = threading.Event()
        self._relay = _Relay(self)
        self._relay.sampled.connect(self._on_sample)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(92)
        self.setStyleSheet("QFrame#hostCard { background:palette(base); border:1px solid palette(mid); border-radius:8px; }"
                           "QFrame#hostCard[checked=\"true\"] { border:2px solid palette(highlight); }")

    def showEvent(self, event):
        super().showEvent(event)
        self.start()

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)

    def start(self) -> None:
        self.stop()
        self._stop = stop = threading.Event()
        body = QWidget()
        row = QHBoxLayout(body)
        row.setContentsMargins(0, 0, 0, 0)
        self._cards.clear()
        try:
            listed = list(self.hosts())
        except Exception as error:  # noqa: BLE001
            listed, failed = [], str(error)
        else:
            failed = ""
        for name, address, kind, executors, interval in listed:
            self._cards[name] = card = _HostCard(name, address, kind, executors, interval, body)
            card.set_checked(name == self._chosen)
            card.clicked.connect(self._choose)
            row.addWidget(card)
            if interval is not None:
                threading.Thread(target=self._read, args=(name, address, interval, stop),
                                 name=f"resources-{name}", daemon=True).start()
        if not listed:
            empty = QLabel(failed or "No executor is on.", body)
            empty.setStyleSheet("color:palette(placeholder-text);")
            row.addWidget(empty)
        row.addStretch(1)
        self.setWidget(body)
        if self._chosen is not None and self._chosen not in self._cards:
            self._choose(self._chosen)  # it is gone: the filter goes with it

    def stop(self) -> None:
        self._stop.set()  # daemons: each ends at its next wake-up, an ssh call in flight included

    def _choose(self, name: str) -> None:
        self._chosen = None if name == self._chosen else name
        for key, card in self._cards.items():
            card.set_checked(key == self._chosen)
        card = self._cards.get(self._chosen)
        self.filter_changed.emit(None if card is None else set(card.executors))

    def _read(self, name: str, address: str, interval: int, stop: threading.Event) -> None:
        reader = _Reader(address)
        while not stop.is_set():
            began = time.monotonic()
            sample = reader.read()
            if stop.is_set():
                return
            self._relay.sampled.emit(name, sample)
            stop.wait(max(0.5, interval - (time.monotonic() - began)))

    def _on_sample(self, name: str, sample: Sample) -> None:
        card = self._cards.get(name)
        if card is not None:
            card.apply(sample)


def workspace_hosts(workspace) -> list[tuple[str, str, str, list[str], int | None]]:
    """`(host, address, kind, executors, interval)` for every host of an executor that is on, with
    every such executor it is in; this machine always. `interval` is None for a queue's login node."""
    if workspace is None:
        return [("local", "", "local", [], INTERVALS["local"])]
    kept = workspace.settings_manager.settings.hosts
    rows: dict[str, list] = {}
    for executor in workspace.executors():
        if executor["state"] != "on":
            continue
        for name in executor["hosts"]:
            if name in rows:
                rows[name][3].append(executor["name"])
                continue
            address = getattr(kept.get(name), "address", "") or ""
            kind = "local" if not address else executor["kind"]
            rows[name] = [name, address, kind, [executor["name"]], INTERVALS.get(kind, INTERVALS["ray"]) if kind != "queue" else None]
    if "local" not in rows:
        rows = {"local": ["local", "", "local", [], INTERVALS["local"]], **rows}
    return [tuple(row) for row in rows.values()]


__all__ = ["HostsStrip", "INTERVALS", "Sample", "Sparkline", "parse", "workspace_hosts"]
