from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlmodel import Session


@runtime_checkable
class SessionProvider(Protocol):
    def get_session(self) -> Session:
        """Return a fresh SQLModel session for a query cycle."""
