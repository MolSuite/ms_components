"""What the machines that run jobs are using: CPU, memory and GPU of each host, over the last minutes.

A host is read where it is: this machine with `psutil` (or `/proc`); a node of a Ray that is on
from the metrics Ray's agent exports there (`Workspace.node_metrics`), so with no ssh; another one
through `ms_env.Host` (the system's `ssh`), with one command that prints `/proc/stat`,
`/proc/meminfo` and `nvidia-smi`. The CPU in use is the change of `/proc/stat` between two reads, so the first
read of a host shows none; a Mac, with no `/proc`, says it from `ps`, `sysctl` and `vm_stat`. Each host is read in its own thread, only while the strip is shown,
every `interval` seconds: a few for this machine, more for one over the network. The login node
of a queue is not read (what it uses says nothing of the nodes its jobs got): its nodes are, from
what the queue says it has taken of them (`Workspace.queue_nodes`), the whole of them in time or
each one now.
"""
from __future__ import annotations

import html
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from collections import Counter, deque
from dataclasses import dataclass, field

from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QStackedWidget, QToolButton,
                               QToolTip, QVBoxLayout, QWidget)

from ms_components.labels import ElidedLabel
from ms_components.theme import color

# Seconds between two reads, by the kind of executor the host is under.
INTERVALS = {"local": 5, "ray": 15, "queue": 30}
_HISTORY = 120  # reads kept per host: 10 min of this machine, 30 of one over the network

_ICONS = Path(__file__).with_name("icons")
# What a queue's jobs ask of it, shown as an icon, a number and what it is on hover.
_ASKED = (("cpu", "CPUs", "CPUs asked of the queue by its active jobs (CPUs of each node times its nodes)"),
          ("memory", "GB", "Memory asked of the queue by its active jobs (of each node times its nodes)"),
          ("gpu", "GPUs", "GPUs asked of the queue by its active jobs (of each node times its nodes)"))

_GPU_QUERY = "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits"
# macOS has no /proc: the CPU its processes use now (`ps`, 100 = one core), and memory from
# `sysctl` and `vm_stat` (free + inactive + speculative pages), said the way Linux says it.
_MAC = ("n=$(sysctl -n hw.ncpu); ps -A -o %cpu= | awk -v n=$n '{s += $1} END {printf \"cpunow %.1f\\n\", s / n}'; "
        "echo \"MemTotal: $(($(sysctl -n hw.memsize) / 1024)) kB\"; "
        "vm_stat | awk '/page size of/ {p = $8} /^Pages (free|inactive|speculative):/ {a += $NF} "
        "END {printf \"MemAvailable: %d kB\\n\", a * p / 1024}'")
# What a host is, read once: the name of its CPU, its threads, the name of each card.
_HARDWARE = ("grep -m1 'model name' /proc/cpuinfo 2>/dev/null || echo \"model name: $(sysctl -n machdep.cpu.brand_string)\"; "
             "echo \"threads: $(nproc 2>/dev/null || sysctl -n hw.ncpu)\"; "
             "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | sed 's/^/gpu: /'; true")
_SCRIPT = (f"if [ -r /proc/stat ]; then head -1 /proc/stat; grep -E '^(MemTotal|MemAvailable):' /proc/meminfo; "
           f"else {_MAC}; fi; {_GPU_QUERY} 2>/dev/null || true")


@dataclass(slots=True)
class Sample:
    cpu: float | None = None  # percent of all CPUs; None on the first read
    mem: float = 0.0  # percent
    mem_used_gb: float = 0.0
    mem_total_gb: float = 0.0
    gpus: list[tuple[float, float, float]] = field(default_factory=list)  # (util %, MiB used, MiB total)
    error: str = ""
    via: str = ""  # "Ray" when its metrics said it
    nodes: list[dict] = field(default_factory=list)  # a queue's: see `ms_flow.remote.read_nodes`
    hardware: dict = field(default_factory=dict)  # `cpu` (its name), `threads`, `gpus` (a name per card)


def parse_hardware(text: str) -> dict:
    """What `_HARDWARE` printed."""
    said: dict = {"gpus": []}
    for line in text.splitlines():
        key, _, value = (part.strip() for part in line.partition(":"))
        if key == "model name" and value:
            said["cpu"] = value
        elif key == "threads" and value.isdigit():
            said["threads"] = int(value)
        elif key == "gpu" and value:
            said["gpus"].append(value)
    return said


def hardware_lines(sample: Sample) -> list[str]:
    """What a machine has, for the hover of its card: CPU, memory, each kind of card."""
    hardware, lines = sample.hardware, []
    cpu = " · ".join(filter(None, (hardware.get("cpu", ""), f"{hardware['threads']} threads" if hardware.get("threads") else "")))
    if cpu:
        lines.append(f"<b>CPU</b> {html.escape(cpu)}")
    if sample.mem_total_gb:
        lines.append(f"<b>Memory</b> {sample.mem_total_gb:.0f} GB")
    names = hardware.get("gpus") or []
    cards = Counter()
    for index in range(max(len(names), len(sample.gpus))):
        total = sample.gpus[index][2] if index < len(sample.gpus) else 0.0
        cards[(names[index] if index < len(names) else "GPU") + (f" · {total / 1024:.0f} GB" if total else "")] += 1
    lines += [f"<b>GPU</b> {f'{n}× ' if n > 1 else ''}{html.escape(card)}" for card, n in cards.items()]
    return lines


def from_nodes(nodes: list[dict]) -> Sample:
    """A queue's nodes as one machine: the share of their CPUs, memory and cards its jobs have
    taken (not what they use of it)."""
    cpus, mem = sum(n["cpus"] for n in nodes), sum(n["mem_gb"] for n in nodes)
    gpus = sum(n["gpus"] for n in nodes)
    sample = Sample(cpu=100.0 * sum(n["cpus_used"] for n in nodes) / cpus if cpus else None, nodes=nodes,
                    mem_used_gb=sum(n["mem_used_gb"] for n in nodes), mem_total_gb=mem, via="the queue")
    sample.mem = 100.0 * sample.mem_used_gb / mem if mem else 0.0
    if gpus:
        sample.gpus = [(100.0 * sum(n["gpus_used"] for n in nodes) / gpus, 0.0, 0.0)] * gpus
    return sample


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
            if 'GpuDeviceName="' in labels:
                gpus[index]["name"] = labels.split('GpuDeviceName="', 1)[1].split('"', 1)[0]
        else:
            got.setdefault(name, float(value))
    sample = Sample(cpu=got.get("ray_node_cpu_utilization"), via="Ray")
    if got.get("ray_node_cpu_count"):
        sample.hardware["threads"] = int(got["ray_node_cpu_count"])
    if any("name" in gpu for gpu in gpus.values()):
        sample.hardware["gpus"] = [gpu.get("name", "GPU") for _index, gpu in sorted(gpus.items())]
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
        if line.startswith("cpunow "):  # a Mac says its share now, no counters
            sample.cpu = min(100.0, float(line.split()[1]))
        elif line.startswith("cpu "):
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

    def __init__(self, address: str, metrics=None, nodes=None):
        # `metrics()` gives the URL of the host's Ray metrics, or None while no Ray has it;
        # `nodes()`, those of the queue the host is the login node of
        self.address, self._ticks, self._psutil, self._metrics, self._url = address, None, None, metrics, None
        self._nodes, self._hardware = nodes, None
        if not address:
            try:
                import psutil

                psutil.cpu_percent(None)  # the first call only starts the count
                self._psutil = psutil
            except ImportError:
                pass

    def read(self) -> Sample:
        sample = self._read()
        if not sample.error and self._nodes is None:  # a queue's nodes say theirs
            if self._hardware is None and sample.via != "Ray":  # Ray's metrics say it, with no ssh
                self._hardware = self._read_hardware()
            sample.hardware = {**(self._hardware or {}), **sample.hardware}
        return sample

    def _read_hardware(self) -> dict:
        """Read once: a machine does not change its CPU. Nothing, if it cannot be read."""
        try:
            if not self.address:
                return parse_hardware(subprocess.run(["sh", "-c", _HARDWARE], capture_output=True, text=True, timeout=10).stdout)
            from ms_env import Host

            return parse_hardware(Host(self.address).run(_HARDWARE, timeout=30).decode(errors="replace"))
        except Exception:  # noqa: BLE001 - the hover only says less
            return {}

    def _read(self) -> Sample:
        try:
            if self._nodes is not None:
                nodes = self._nodes()
                return from_nodes(nodes) if nodes else Sample(error="the queue lists no nodes")
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

    def __init__(self, title: str, parent=None, *, icon: str = "", tip: str = ""):
        super().__init__(parent)
        self.title, self.values, self.interval, self.note = title, deque(maxlen=_HISTORY), 5, ""
        self.icon, self.tip = icon, tip  # drawn before the name; what the measure is, over the label row
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
        faint = pal.color(QPalette.ColorRole.PlaceholderText)
        p.setPen(faint)
        left = 0
        if self.icon:
            p.drawPixmap(0, 0, _icon(self.icon, faint.name(), top - 4, self.devicePixelRatioF()))
            left = top
        p.drawText(left, 0, w - left, top - 4, Qt.AlignLeft | Qt.AlignVCenter, self.title)
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
        if event.position().y() < self._TOP and self.tip:
            QToolTip.showText(event.globalPosition().toPoint(), self.tip, self)
            return
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
        self._where = (f"{address or 'this computer'} · in {', '.join(self.executors) or 'no executor'}"
                       + (f" · read every {interval}s" if interval else ""))
        self._tip(None)
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
        self.about = ElidedLabel("", self)  # a long address gives way to the jobs and the button
        self.about.setStyleSheet("color:palette(placeholder-text); font-size:11px;")
        self.jobs = QLabel(self)
        self.jobs.setStyleSheet("color:palette(placeholder-text); font-size:11.5px;")
        for widget in (dot, title, chip):
            head.addWidget(widget)
        head.addWidget(self.about, 1)
        head.addWidget(self.jobs)
        box.addLayout(head)
        self.queue = kind == "queue"
        self.pages = QStackedWidget(self)
        page = QWidget(self.pages)
        charts = QHBoxLayout(page)
        charts.setContentsMargins(0, 0, 0, 0)
        charts.setSpacing(12)
        self.pages.addWidget(page)
        if self.queue:
            # A queue is shared: by default, what its jobs asked of it; behind "Nodes", each node and
            # what every job has taken of it (Overall / per CPU, as system monitors do).
            self.asked = {}
            for icon, unit, tip in _ASKED:
                self.asked[icon] = cell = _Asked(icon, unit, tip, page)
                charts.addWidget(cell, 1)
            listed = QScrollArea(self.pages)
            listed.setWidgetResizable(True)
            listed.setFrameShape(QFrame.NoFrame)
            listed.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # the rows elide nothing; a narrow card cuts the load
            listed.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
            self.node_rows = QWidget(listed)
            self.node_grid = QGridLayout(self.node_rows)
            self.node_grid.setContentsMargins(0, 0, 4, 0)
            self.node_grid.setHorizontalSpacing(14)
            self.node_grid.setVerticalSpacing(1)
            listed.setWidget(self.node_rows)
            self.pages.addWidget(listed)
            self.toggle = QToolButton(self)
            self.toggle.setText("Nodes")
            self.toggle.setCheckable(True)
            self.toggle.setToolTip("Each node of the queue, or what its jobs asked of it (the default)")
            self.toggle.setCursor(Qt.ArrowCursor)
            self.toggle.setStyleSheet("QToolButton { font-size:11px; padding:0 6px; }")
            self.toggle.toggled.connect(lambda on: self.pages.setCurrentIndex(int(on)))
            head.addWidget(self.toggle)
        else:
            self.cpu, self.mem, self.gpu = (
                Sparkline("CPU", page, icon="cpu", tip="CPU use of the whole machine, by every program on it"),
                Sparkline("Memory", page, icon="memory", tip="Memory (RAM) in use on the machine, by every program on it"),
                Sparkline("GPU", page, icon="gpu", tip="GPU use: the mean over the machine's cards"))
            for chart in (self.cpu, self.mem, self.gpu):
                chart.interval = interval or 0
                charts.addWidget(chart, 1)
            self.gpu.setVisible(False)  # until a read finds one
        self.pages.setVisible(interval is not None)
        box.addWidget(self.pages, 1)
        self.said = QLabel("not read: the login node of a queue" if interval is None else "", self)
        self.said.setStyleSheet("color:palette(placeholder-text); font-size:11px;")
        self.said.setVisible(interval is None)
        box.addWidget(self.said)
        self._describe(None)

    def _describe(self, sample: Sample | None) -> None:
        said = [self.address] if self.address else ["this computer", f"{os.cpu_count()} threads"]
        if sample is not None and sample.nodes:
            up = sum(not _down(node["state"]) for node in sample.nodes)
            said.append(f"{len(sample.nodes)} node{'s' * (len(sample.nodes) != 1)}" + (f", {up} up" if up != len(sample.nodes) else ""))
            self.about.setText(" · ".join(said))  # its CPUs and memory: on its charts
            return
        if sample is not None and sample.mem_total_gb:
            said.append(f"{sample.mem_total_gb:.0f} GB")
        if sample is not None and sample.via:
            said.append(f"via {sample.via}")
        self.about.setText(" · ".join(said))

    def _tip(self, sample: Sample | None) -> None:
        """The hover of the card: where it is, then what it has (a queue: its nodes)."""
        lines = [html.escape(self._where)]
        if sample is not None:
            lines += [queue_summary(sample.nodes)] if self.queue else hardware_lines(sample)
        self.setToolTip("<br>".join(lines + ["<i>Click: only its jobs</i>"]))

    def set_jobs(self, active: int, cpus: int, asked: dict | None = None) -> None:
        self.jobs.setText(f"{active} active job{'s' * (active != 1)}" + (f" · {cpus:,} CPUs in use" if cpus else ""))
        if self.queue:
            for icon, cell in self.asked.items():
                cell.set((asked or {}).get(icon, 0))

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
        self._tip(sample)
        if self.queue:
            self._list(sample.nodes)
            return
        self.cpu.push(sample.cpu)
        self.mem.push(sample.mem, f"{sample.mem_used_gb:.1f}/{sample.mem_total_gb:.0f} GB")
        if sample.gpus:  # ponytail: the mean over the cards; one chart per card when a host has several that differ
            util = sum(g[0] for g in sample.gpus) / len(sample.gpus)
            self.gpu.title = f"GPU {len(sample.gpus)}×"
            self.gpu.push(util)
            self.gpu.setVisible(True)

    def _list(self, nodes: list[dict]) -> None:
        """One row for each node: its state, then what the queue's jobs have taken of it."""
        while self.node_grid.count():
            self.node_grid.takeAt(0).widget().deleteLater()
        faint = "color:palette(placeholder-text); font-size:11px;"
        for row, node in enumerate(nodes):
            hue = "red" if _down(node["state"]) else "green" if node["state"] in ("idle", "up") else "blue"
            cells = [("●", f"color:{color(hue).name()}; font-size:9px;"), (node["name"], "font-size:11.5px; font-weight:600;"),
                     (node["state"], faint), (f"{node['cpus_used']}/{node['cpus']} CPUs", "font-size:11px;"),
                     (f"{node['mem_used_gb']:.0f}/{node['mem_gb']:.0f} GB", "font-size:11px;"),
                     (_gpus(node), "font-size:11px;"),
                     ("" if node["load"] is None else f"load {node['load']:.2f}", faint)]
            for column, (text, style) in enumerate(cells):
                label = QLabel(text, self.node_rows)
                label.setStyleSheet(style)
                self.node_grid.addWidget(label, row, column)
        self.node_grid.setColumnStretch(7, 1)
        self.node_grid.setRowStretch(len(nodes), 1)


class _Asked(QWidget):
    """An icon and how much of one resource a queue's jobs asked; what it is, on hover."""

    def __init__(self, icon: str, unit: str, tip: str, parent=None):
        super().__init__(parent)
        self.unit = unit
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.icon = QLabel(self)
        self.icon.setPixmap(_icon(icon, self.palette().color(QPalette.PlaceholderText).name(), 18,
                                  self.devicePixelRatioF()))
        self.value = QLabel(self)
        self.value.setStyleSheet("font-size:15px; font-weight:650;")
        row.addWidget(self.icon)
        row.addWidget(self.value)
        row.addStretch(1)
        self.setToolTip(tip)
        self.set(0)

    def set(self, amount: float) -> None:
        self.value.setText(f"{amount:,.0f} {self.unit}" if amount else f"– {self.unit}")


def _icon(name: str, color_hex: str, size: int, dpr: float) -> QPixmap:
    svg = (_ICONS / f"{name}.svg").read_bytes().replace(b"currentColor", color_hex.encode())
    pixmap = QPixmap(round(size * dpr), round(size * dpr))
    pixmap.fill(Qt.transparent)
    with QPainter(pixmap) as painter:
        QSvgRenderer(QByteArray(svg)).render(painter)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def queue_asked(jobs) -> dict:
    """What `jobs` (snapshots of one queue) ask of it, added up: `cpu`, `memory` (GB), `gpu`."""
    total = {"cpu": 0, "memory": 0, "gpu": 0}
    for job in jobs:
        asked = getattr(job, "asked", None) or {}
        nodes = int(asked.get("nodes") or 1)
        for key, said in (("cpu", "cpus"), ("memory", "memory_gb"), ("gpu", "gpus")):
            try:
                total[key] += nodes * float(asked.get(said) or 0)
            except (TypeError, ValueError):  # a site's own form ("a100:2"): not added
                pass
    return total


# ponytail: a queue of more nodes than this lists the first ones; a scrolling popup if that hurts.
_LISTED_NODES = 40


def queue_summary(nodes: list[dict]) -> str:
    """The whole of a queue, for the hover of its card: its nodes, what everyone has taken of their
    CPUs, memory and cards, then each node."""
    if not nodes:
        return "The queue lists no nodes"
    up = sum(not _down(node["state"]) for node in nodes)
    taken = lambda key: sum(node[key] for node in nodes)  # noqa: E731
    lines = [f"<b>{len(nodes)} node{'s' * (len(nodes) != 1)}</b>, {up} up · taken by every job of the queue:",
             f"CPUs {taken('cpus_used'):,}/{taken('cpus'):,} · memory {taken('mem_used_gb'):,.0f}/{taken('mem_gb'):,.0f} GB"
             + (f" · GPUs {taken('gpus_used')}/{taken('gpus')}" if taken("gpus") else "")]
    rows = "".join(
        f"<tr><td>{node['name']}</td><td>{node['state']}</td><td>{node['cpus_used']}/{node['cpus']} CPUs</td>"
        f"<td>{node['mem_used_gb']:.0f}/{node['mem_gb']:.0f} GB</td>"
        f"<td>{_gpus(node)}</td></tr>"
        for node in nodes[:_LISTED_NODES])
    more = f"<br>+{len(nodes) - _LISTED_NODES} more" if len(nodes) > _LISTED_NODES else ""
    return "<br>".join(lines) + f"<table cellspacing='6'>{rows}</table>{more}"


def _gpus(node: dict) -> str:
    return f"{node['gpus_used']}/{node['gpus']} GPUs" if node["gpus"] else ""


def _down(state: str) -> bool:
    """Slurm's `down`, `drained`, `fail`, `not_responding` (with their `*`); Grid Engine's `down`."""
    return any(word in state for word in ("down", "drain", "fail", "not_responding", "unknown"))


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
                threading.Thread(target=self._read, args=(name, address, interval, stop, self._metrics(name, kind, executors),
                                                          self._nodes(kind, executors)),
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
            card.set_jobs(len(mine), sum(job.cpu_used or 0 for job in mine), queue_asked(mine))

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

    def _nodes(self, kind: str, executors: list[str]):
        """What gives the nodes of the queue a login host is of."""
        ask = getattr(self._workspace, "queue_nodes", None)
        if kind != "queue" or ask is None or not executors:
            return None
        return lambda: ask(executors[0])

    def _read(self, name: str, address: str, interval: int, stop: threading.Event, metrics=None, nodes=None) -> None:
        reader = _Reader(address, metrics, nodes)
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
    every such executor it is in; this machine always. A queue's login node is read for its nodes."""
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
            rows[name] = [name, address, kind, [executor["name"]], INTERVALS.get(kind, INTERVALS["ray"])]
    if "local" not in rows:
        rows = {"local": ["local", "", "local", [], INTERVALS["local"]], **rows}
    return [tuple(row) for row in rows.values()]


__all__ = ["HostsStrip", "INTERVALS", "Sample", "Sparkline", "from_nodes", "parse", "parse_metrics", "queue_asked",
           "queue_summary", "workspace_hosts"]
