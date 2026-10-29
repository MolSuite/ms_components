"""What the machines that run jobs are using: CPU, memory and GPU of each host, over the last minutes.

A host is read where it is: this machine with `psutil` (or `/proc`), another one through
`ms_env.Host` (the system's `ssh`), with one command that prints `/proc/stat`, `/proc/meminfo`
and `nvidia-smi`. The CPU in use is the change of `/proc/stat` between two reads, so the first
read of a host shows none. Each host is read in its own thread, only while the panel is shown,
every `interval` seconds: a few for this machine, more for one over the network, the most for
the login node of a queue, which is asked through the same `ssh` its jobs are.
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
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QScrollArea, QToolTip, QVBoxLayout, QWidget

# Seconds between two reads, by the kind of executor the host is under.
INTERVALS = {"local": 5, "ray": 15, "queue": 60}
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
    sampled = Signal(str, object)  # host key, Sample


class _HostRow(QFrame):
    def __init__(self, name: str, address: str, interval: int, parent=None):
        super().__init__(parent)
        self.setObjectName("hostRow")
        self.setStyleSheet("QFrame#hostRow { background:palette(base); border:1px solid palette(mid); border-radius:8px; }")
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 6, 10, 6)
        title = QLabel(f"<b>{name}</b> <span style='color:palette(placeholder-text)'>"
                       f"{address or 'this computer'} · every {interval}s</span>", self)
        grid.addWidget(title, 0, 0)
        self.said = QLabel(self)
        self.said.setStyleSheet("color:palette(placeholder-text); font-size:10px;")
        self.said.setWordWrap(True)
        self.said.setVisible(False)
        grid.addWidget(self.said, 1, 0)
        self.lines = {key: Sparkline(key, self) for key in ("CPU", "Memory", "GPU")}
        for at, line in enumerate(self.lines.values(), start=2):  # stacked: each its own axis, full width
            line.interval = interval
            grid.addWidget(line, at, 0)
        self.lines["GPU"].setVisible(False)

    def apply(self, sample: Sample) -> None:
        self.said.setText(sample.error)
        self.said.setVisible(bool(sample.error))
        if sample.error:
            return
        self.lines["CPU"].push(sample.cpu)
        self.lines["Memory"].push(sample.mem, f"{sample.mem_used_gb:.1f}/{sample.mem_total_gb:.0f} GB")
        if sample.gpus:  # ponytail: the mean over the cards; a line per card when one host has several that differ
            util = sum(g[0] for g in sample.gpus) / len(sample.gpus)
            used, total = sum(g[1] for g in sample.gpus) / 1024, sum(g[2] for g in sample.gpus) / 1024
            self.lines["GPU"].setVisible(True)
            self.lines["GPU"].push(util, f"{len(sample.gpus)}× · {used:.1f}/{total:.0f} GB")


class ResourcesPanel(QScrollArea):
    """The hosts of the executors that are on, under the name of each, read while shown.

    `hosts()` gives `(group, name, address, interval_s)` for each host to read; by default
    they come from `workspace` (see `workspace_hosts`).
    """

    def __init__(self, workspace=None, *, hosts=None, parent=None):
        super().__init__(parent)
        self.hosts = hosts or (lambda: workspace_hosts(workspace))
        self._rows: dict[str, _HostRow] = {}
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._relay = _Relay(self)
        self._relay.sampled.connect(self._on_sample)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

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
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 4, 4, 4)
        self._rows.clear()
        try:
            listed = list(self.hosts())
        except Exception as error:  # noqa: BLE001
            listed, failed = [], str(error)
        else:
            failed = ""
        group = None
        for at, (in_group, name, address, interval) in enumerate(listed):
            if in_group != group:
                group = in_group
                heading = QLabel(f"<b>{group}</b>", body)
                heading.setStyleSheet("color:palette(placeholder-text); margin-top:6px;")
                layout.addWidget(heading)
            key = f"{at}:{name}"
            self._rows[key] = row = _HostRow(name, address, interval, body)
            layout.addWidget(row)
            thread = threading.Thread(target=self._read, args=(key, address, interval, stop),
                                      name=f"resources-{name}", daemon=True)
            self._threads.append(thread)
            thread.start()
        if not listed:
            empty = QLabel(failed or "No executor is on.", body)
            empty.setStyleSheet("color:palette(placeholder-text);")
            layout.addWidget(empty)
        layout.addStretch(1)
        self.setWidget(body)

    def stop(self) -> None:
        self._stop.set()
        self._threads.clear()  # daemons: each ends at its next wake-up, an ssh call in flight included

    def _read(self, key: str, address: str, interval: int, stop: threading.Event) -> None:
        reader = _Reader(address)
        while not stop.is_set():
            began = time.monotonic()
            sample = reader.read()
            if stop.is_set():
                return
            self._relay.sampled.emit(key, sample)
            stop.wait(max(0.5, interval - (time.monotonic() - began)))

    def _on_sample(self, key: str, sample: Sample) -> None:
        row = self._rows.get(key)
        if row is not None:
            row.apply(sample)


def workspace_hosts(workspace) -> list[tuple[str, str, str, int]]:
    """`(executor, host, address, interval)` for every host of an executor that is on, a host under
    the first one that has it; this machine always, under `local` when no executor that is on has it."""
    if workspace is None:
        return [("local", "local", "", INTERVALS["local"])]
    kept = workspace.settings_manager.settings.hosts
    rows, seen = [], set()
    for executor in workspace.executors():
        if executor["state"] != "on":
            continue
        for name in executor["hosts"]:
            if name in seen:
                continue
            seen.add(name)
            address = getattr(kept.get(name), "address", "") or ""
            kind = "local" if not address else executor["kind"]
            group = f"{executor['name']} ({executor['kind']}{', login node' if kind == 'queue' else ''})"
            rows.append((group, name, address, INTERVALS.get(kind, INTERVALS["ray"])))
    if "local" not in seen:
        rows.insert(0, ("local", "local", "", INTERVALS["local"]))
    return rows


__all__ = ["INTERVALS", "ResourcesPanel", "Sample", "Sparkline", "parse", "workspace_hosts"]
