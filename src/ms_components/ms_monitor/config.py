"""Default configuration for the monitor component.

Qt-free on purpose: host apps (e.g. AMDockVS) import this model to nest it as a
section in their own configuration and persist overrides in their config file,
without pulling in PySide. The component owns the defaults; the host owns the
storage.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MonitorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_ms: int = Field(500, ge=50, description="Polling interval of the monitor bridge, in ms.")
    max_recent_jobs: int = Field(20, ge=1, description="How many recent jobs the monitor keeps.")


__all__ = ["MonitorConfig"]
