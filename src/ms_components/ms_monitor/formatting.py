from __future__ import annotations

from datetime import datetime


def format_throughput(eps: float) -> str:
    eps = max(0.0, eps)
    return "-" if eps <= 0.0 else f"{eps:.2f} chunks/s"


def format_relative_time(value: datetime | None, *, now: datetime | None = None) -> str:
    if value is None:
        return "-"
    now = now or datetime.now()
    delta_s = max(0.0, (now - value).total_seconds())
    if delta_s < 60.0:
        return f"{int(delta_s)}s ago"
    if delta_s < 3600.0:
        return f"{int(delta_s // 60)}m ago"
    return f"{int(delta_s // 3600)}h ago"
