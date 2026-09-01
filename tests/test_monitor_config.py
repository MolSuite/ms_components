from __future__ import annotations

import pytest
from pydantic import ValidationError

from ms_components.ms_monitor.config import MonitorConfig


def test_monitor_config_defaults():
    cfg = MonitorConfig()
    assert cfg.poll_ms == 500
    assert cfg.max_recent_jobs == 20


def test_monitor_config_rejects_out_of_range_and_extra_keys():
    with pytest.raises(ValidationError):
        MonitorConfig(poll_ms=10)  # below ge=50
    with pytest.raises(ValidationError):
        MonitorConfig(max_recent_jobs=0)  # below ge=1
    with pytest.raises(ValidationError):
        MonitorConfig(unknown=1)  # extra="forbid"
