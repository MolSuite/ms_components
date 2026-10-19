"""Application-independent tutorial content, authored in Python or TOML."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class TutorialStep:
    id: str
    target: str
    title: str
    text: str
    advance_on: str | None = None

    def __post_init__(self):
        for name in ("id", "target", "title", "text"):
            _text(getattr(self, name), f"step.{name}")
        if self.advance_on is not None:
            _text(self.advance_on, "step.advance_on")


@dataclass(frozen=True)
class Tutorial:
    id: str
    title: str
    steps: tuple[TutorialStep, ...]

    def __post_init__(self):
        _text(self.id, "tutorial.id")
        _text(self.title, "tutorial.title")
        object.__setattr__(self, "steps", tuple(self.steps))
        if not self.steps or not all(isinstance(step, TutorialStep) for step in self.steps):
            raise ValueError("tutorial.steps must contain at least one TutorialStep")
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Tutorial step IDs must be unique")


def load_tutorial(path: str | Path) -> Tutorial:
    """Read data only: target/event names are resolved by the application, never evaluated."""
    with Path(path).open("rb") as source:
        data = tomllib.load(source)
    allowed = {"id", "title", "steps"}
    if set(data) - allowed:
        raise ValueError(f"Unknown tutorial keys: {', '.join(sorted(set(data) - allowed))}")
    if not isinstance(data.get("steps"), list):
        raise ValueError("Tutorial must contain [[steps]] tables")
    try:
        return Tutorial(id=data["id"], title=data["title"],
                        steps=tuple(TutorialStep(**step) for step in data["steps"]))
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid tutorial definition: {exc}") from exc
