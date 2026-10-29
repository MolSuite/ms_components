"""What the machines that run jobs are using: CPU, memory and GPU of each host, over the last minutes.

A host is read where it is: this machine with `psutil` (or `/proc`); a node of a Ray that is on
from the metrics Ray's agent exports there (`Workspace.node_metrics`), so with no ssh; another one
through `ms_env.Host` (the system's `ssh`), with one command that prints `/proc/stat`,
`/proc/meminfo` and `nvidia-smi`. The CPU in use is the change of `/proc/stat` between two reads, so the first
read of a host shows none. Each host is read in its own thread, only while the strip is shown,
every `interval` seconds: a few for this machine, more for one over the network. The login node
of a queue is not read: what it uses says nothing of the nodes its jobs got.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QToolTip, QVBoxLayout, QWidget

from ms_components.theme import color

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
    via: str = ""  # "Ray" when its metrics said it


def parse_metrics(text: str) -> Sample:
    """A sample from the Prometheus text Ray's agent exports on a node: the whole machine."""
    got, gpus = {}, {}
    for line in text.splitlines():
        if not line.startswith("ray_node_") or "} " not in line:
            continue
        name, _, rest = line.partition("{")
        labels, _, value = rest.rpartition("} ")
        if name in ("ray_node_gpus_utilization", "ray_node_gram_used", "ray_node_gram_available"):
            index = labels.split('GpuIndex="', 1)[-1].split('"', 1)[0]
            gpus.setdefault(index, {})[name] = float(value)
        else:
            got.setdefault(name, float(value))
    sample = Sample(cpu=got.get("ray_node_cpu_utilization"), via="Ray")
    total = got.get("ray_node_mem_total", 0.0)
    if total:
        sample.mem_total_gb, sample.mem_used_gb = total / 1024**3, got.get("ray_node_mem_used", 0.0) / 1024**3
        sample.mem = 100.0 * sample.mem_used_gb / sample.mem_total_gb
    for _index, gpu in sorted(gpus.items()):
        used = gpu.get("ray_node_gram_used", 0.0)  # MiB
        sample.gpus.append((gpu.get("ray_node_gpus_utilization", 0.0), used, used + gpu.get("ray_node_gram_available", 0.0)))
    return sample


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

    def __init__(self, address: str, metrics=None):
        # `metrics()` gives the URL of the host's Ray metrics, or None while no Ray has it
        self.address, self._ticks, self._psutil, self._metrics, self._url = address, None, None, metrics, None
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
            if self._metrics is not None:
                self._url = self._url or self._metrics()
                if self._url:
                    try:
                        return parse_metrics(urllib.request.urlopen(self._url, timeout=10).read().decode())
                    except OSError:
                        self._url = None  # the node left, or its Ray ended: asked again, ssh meanwhile
            from ms_env import Host

            text = Host(self.address or None).run(_SCRIPT, timeout=30).decode(errors="replace")
            sample, self._ticks = parse(text, self._ticks)
            return sample
        except Exception as error:  # noqa: BLE001 - shown on the row of the host
            said = str(error).split("` on ", 1)[-1].strip()  # not the command: where, and what went wrong
            return Sample(error=said.splitlines()[-1] if said else type(error).__name__)


class Sparkline(QWidget):
    """One measure of one host over time, 0-100 %: a label row (the name, the value now), then the
    area under the line on a sunken panel. Hovering says the value under the pointer and how long
    ago it was."""

    _TOP = 18  # the label row

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title, self.values, self.interval, self.note = title, deque(maxlen=_HISTORY), 5, ""
        self.setMinimumSize(120, 70)
        self.setMouseTracking(True)

    def push(self, value: float | None, note: str = "") -> None:
        """`note` is said instead of the percent, when given."""
        self.values.append(value)
        self.note = note
        self.update()

    def _x(self, index: int) -> float:
        return self.width() * index / max(1, _HISTORY - 1)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        w, h, top = self.width(), self.height(), self._TOP
        small = p.font()
        small.setPixelSize(11)
        p.setFont(small)
        p.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
        p.drawText(0, 0, w, top - 4, Qt.AlignLeft | Qt.AlignVCenter, self.title)
        now = next((v for v in reversed(self.values) if v is not None), None)
        small.setBold(True)
        p.setFont(small)
        p.setPen(pal.color(QPalette.ColorRole.Text))
        p.drawText(0, 0, w, top - 4, Qt.AlignRight | Qt.AlignVCenter, self.note or ("—" if now is None else f"{now:.0f}%"))
        chart = QRectF(0, top, w, h - top)
        p.setPen(Qt.NoPen)
        p.setBrush(pal.color(QPalette.ColorRole.AlternateBase))
        p.drawRoundedRect(chart, 4, 4)
        p.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 1, Qt.DashLine))
        p.drawLine(QPointF(4, chart.center().y()), QPointF(w - 4, chart.center().y()))  # the 50 %
        start = _HISTORY - len(self.values)
        bottom = h - 1
        points = [QPointF(self._x(start + i), bottom - (chart.height() - 3) * min(100.0, v) / 100.0)
                  for i, v in enumerate(self.values) if v is not None]
        if len(points) < 2:
            return
        accent = pal.color(QPalette.ColorRole.Highlight)
        area = QPainterPath(QPointF(points[0].x(), bottom))
        for point in points:
            area.lineTo(point)
        area.lineTo(QPointF(points[-1].x(), bottom))
        fill = QColor(accent)
        fill.setAlphaF(0.38)
        clip = QPainterPath()
        clip.addRoundedRect(chart, 4, 4)
        p.setClipPath(clip)
        p.fillPath(area, fill)
        p.setPen(QPen(accent, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
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
    """One host: a header (name, kind, what it is, the jobs on it) over CPU, memory and GPU in
    time. Checked, it filters the jobs."""

    clicked = Signal(str)

    def __init__(self, name: str, address: str, kind: str, executors: list[str], interval: int | None, parent=None):
        super().__init__(parent)
        # this machine's pool has no executor row of its own: its jobs say `local`
        self.name, self.address, self.executors = name, address, executors or ([name] if kind == "local" else [])
        self.setObjectName("hostCard")
        self.setProperty("checked", False)
        self.setMinimumWidth(380)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{address or 'this computer'} · in {', '.join(self.executors) or 'no executor'}"
                        + (f" · read every {interval}s" if interval else "") + "\nClick: only its jobs")
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 8, 12, 10)
        box.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(7)
        dot = QLabel("●", self)
        dot.setStyleSheet(f"color:{color('green').name()}; font-size:10px;")
        title = QLabel(name, self)
        title.setStyleSheet("font-weight:650; font-size:13px;")
        chip = QLabel(kind, self)
        chip.setStyleSheet("color:palette(placeholder-text); border:1px solid palette(mid); border-radius:8px; padding:0 7px; font-size:11px;")
        self.about = QLabel(self)
        self.about.setStyleSheet("color:palette(placeholder-text); font-size:11px;")
        self.jobs = QLabel(self)
        self.jobs.setStyleSheet("color:palette(placeholder-text); font-size:11.5px;")
        for widget in (dot, title, chip, self.about):
            head.addWidget(widget)
        head.addStretch(1)
        head.addWidget(self.jobs)
        box.addLayout(head)
        charts = QHBoxLayout()
        charts.setSpacing(12)
        self.cpu, self.mem, self.gpu = Sparkline("CPU", self), Sparkline("Memory", self), Sparkline("GPU", self)
        for chart in (self.cpu, self.mem, self.gpu):
            chart.interval = interval or 0
            chart.setVisible(interval is not None)
            charts.addWidget(chart, 1)
        self.gpu.setVisible(False)  # until a read finds one
        box.addLayout(charts, 1)
        self.said = QLabel("not read: the login node of a queue" if interval is None else "", self)
        self.said.setStyleSheet("color:palette(placeholder-text); font-size:11px;")
        self.said.setVisible(interval is None)
        box.addWidget(self.said)
        self._describe(None)

    def _describe(self, sample: Sample | None) -> None:
        said = [self.address] if self.address else ["this computer", f"{os.cpu_count()} threads"]
        if sample is not None and sample.mem_total_gb:
            said.append(f"{sample.mem_total_gb:.0f} GB")
        if sample is not None and sample.via:
            said.append(f"via {sample.via}")
        self.about.setText(" · ".join(said))

    def set_jobs(self, active: int, cpus: int) -> None:
        self.jobs.setText(f"{active} active job{'s' * (active != 1)}" + (f" · {cpus:,} CPUs in use" if cpus else ""))

    def set_checked(self, checked: bool) -> None:
        self.setProperty("checked", checked)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.name)
        super().mouseReleaseEvent(event)

    def apply(self, sample: Sample) -> None:
        self.said.setVisible(bool(sample.error))
        if sample.error:
            self.said.setText(sample.error)
            return
        self._describe(sample)
        self.cpu.push(sample.cpu)
        self.mem.push(sample.mem, f"{sample.mem_used_gb:.1f}/{sample.mem_total_gb:.0f} GB")
        if sample.gpus:  # ponytail: the mean over the cards; one chart per card when a host has several that differ
            util = sum(g[0] for g in sample.gpus) / len(sample.gpus)
            self.gpu.title = f"GPU {len(sample.gpus)}×"
            self.gpu.push(util)
            self.gpu.setVisible(True)


class HostsStrip(QScrollArea):
    """The hosts of the executors that are on, side by side, read while shown. Clicking one keeps
    only the jobs of its executors (`filter_changed` gives their names, or None for all).

    `hosts()` gives `(name, address, kind, executors, interval_s or None)` for each host; by
    default they come from `workspace` (see `workspace_hosts`).
    """

    filter_changed = Signal(object)

    def __init__(self, workspace=None, *, hosts=None, parent=None):
        super().__init__(parent)
        self.hosts, self._workspace = hosts or (lambda: workspace_hosts(workspace)), workspace
        self._cards: dict[str, _HostCard] = {}
        self._chosen: str | None = None
        self._stop = threading.Event()
        self._relay = _Relay(self)
        self._relay.sampled.connect(self._on_sample)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(132)
        self.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }"
                           "QFrame#hostCard { background:palette(base); border:1px solid palette(mid); border-radius:8px; }"
                           "QFrame#hostCard[checked=\"true\"] { border:2px solid palette(highlight); }")
        self._jobs: list = []

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
        row.setSpacing(10)
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
            row.addWidget(card, 145 if kind == "local" else 100)
            if interval is not None:
                threading.Thread(target=self._read, args=(name, address, interval, stop, self._metrics(name, kind, executors)),
                                 name=f"resources-{name}", daemon=True).start()
        if not listed:
            empty = QLabel(failed or "No executor is on.", body)
            empty.setStyleSheet("color:palette(placeholder-text);")
            row.addWidget(empty)
            row.addStretch(1)
        self.setWidget(body)
        self.set_jobs(self._jobs)
        if self._chosen is not None and self._chosen not in self._cards:
            self._choose(self._chosen)  # it is gone: the filter goes with it

    @property
    def chosen(self) -> str | None:
        """The host whose jobs are the only ones shown, if one is."""
        return self._chosen

    def clear_choice(self) -> None:
        """No host checked, without saying so: the filter was dropped elsewhere."""
        self._chosen = None
        for card in self._cards.values():
            card.set_checked(False)

    def set_jobs(self, jobs) -> None:
        """The jobs as polled: each card says how many of its executors' are active and their CPUs."""
        self._jobs = jobs
        for card in self._cards.values():
            mine = [job for job in jobs if not job.is_terminal and job.executor in card.executors]
            card.set_jobs(len(mine), sum(job.cpu_used or 0 for job in mine))

    def stop(self) -> None:
        self._stop.set()  # daemons: each ends at its next wake-up, an ssh call in flight included

    def _choose(self, name: str) -> None:
        self._chosen = None if name == self._chosen else name
        for key, card in self._cards.items():
            card.set_checked(key == self._chosen)
        card = self._cards.get(self._chosen)
        self.filter_changed.emit(None if card is None else set(card.executors))

    def _metrics(self, name: str, kind: str, executors: list[str]):
        """What gives the URL of the Ray metrics of host `name`, for one under a Ray."""
        ask = getattr(self._workspace, "node_metrics", None)
        if kind != "ray" or ask is None:
            return None
        return lambda: next((url for executor in executors if (url := ask(executor).get(name))), None)

    def _read(self, name: str, address: str, interval: int, stop: threading.Event, metrics=None) -> None:
        reader = _Reader(address, metrics)
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


__all__ = ["HostsStrip", "INTERVALS", "Sample", "Sparkline", "parse", "parse_metrics", "workspace_hosts"]
