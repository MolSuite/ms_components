from __future__ import annotations

from datetime import datetime


def format_speed(eps: float) -> str:
    """Chunks per second, or per minute below one a second."""
    eps = max(0.0, eps)
    if eps <= 0.0:
        return "—"
    return f"{eps:,.1f}/s" if eps >= 1 else f"{eps * 60:,.1f}/min"


def format_duration(seconds: float) -> str:
    seconds = int(max(0.0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"
    return f"{seconds // 86400}d {seconds % 86400 // 3600}h"


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
