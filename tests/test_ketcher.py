"""run_editor hands the molblock to a child process and returns only an applied drawing."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ms_components import ketcher


@pytest.mark.parametrize("applied", [True, False])
def test_run_editor_returns_the_drawing_only_after_apply(monkeypatch, applied):
    seen = {}

    def run(command, *, input, **_kwargs):
        seen.update(json.loads(command[-2]), molblock=input)
        if applied:
            Path(command[-1]).write_text("drawn")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ketcher.subprocess, "run", run)
    result = ketcher.run_editor(Path("/ketcher"), "original", "Edit", note="Apply replaces it.")
    assert result == ("drawn" if applied else None)
    assert (seen["folder"], seen["title"], seen["note"], seen["molblock"]) == (
        "/ketcher", "Edit", "Apply replaces it.", "original")


def test_a_crashed_editor_raises(monkeypatch):
    monkeypatch.setattr(ketcher.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=-11, stderr="boom"))
    with pytest.raises(RuntimeError, match="exit code -11"):
        ketcher.run_editor(Path("/ketcher"), "original", "Edit")


def test_cannot_apply_when_loading_the_molecule_failed(monkeypatch):
    monkeypatch.setattr(ketcher.QMessageBox, "warning", lambda *_args: None)
    # No button access: Apply must stay disabled when setMolecule rejects.
    ketcher.KetcherDialog._ready(SimpleNamespace(), {"error": "invalid structure"})
