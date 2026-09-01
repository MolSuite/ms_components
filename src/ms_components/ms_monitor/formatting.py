from __future__ import annotations

from datetime import datetime


def format_progress(progress: float) -> str:
    return f"{max(0.0, progress):.1f}%"


def format_chunks(done: int, total: int) -> str:
    return f"{done:,} / {total:,}" if total > 0 else f"{done:,}"


def format_queue_wait(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = max(0.0, float(seconds))
    if seconds < 1.0:
        return f"{seconds:.2f}s"
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    if seconds < 3600.0:
        return f"{seconds / 60.0:.1f}m"
    return f"{seconds / 3600.0:.1f}h"


def format_throughput(eps: float) -> str:
    eps = max(0.0, eps)
    return "-" if eps <= 0.0 else f"{eps:.2f} eps"


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


def format_status(status: str, cancel_requested: bool = False) -> str:
    if cancel_requested and status not in {"canceled", "completed", "failed"}:
        return f"{status} (canceling)"
    return status or "-"


def format_executor_summary(active_jobs: int, running_chunks: int, accounting: str) -> str:
    return f"jobs={active_jobs} run={running_chunks} acct={accounting}"
