"""The folder a project gets on disk, from the name its author typed.

A project's name is theirs to write: spaces, punctuation, accents, emoji. The folder under it
is read back by other programs, and some of them parse a path badly -- Uni-Dock splits each
line of its ligand list on whitespace, so a project called "AmpC DUDE-Z screening (Unidock)"
made it abort on every ligand. The name stays whole in the catalog; only the folder is held to
what a file system and a plain parser can both carry.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

#: Letters, digits and the three separators every file system and parser takes.
_KEEP = re.compile(r"[^A-Za-z0-9._-]+")
_RUNS = re.compile(r"_{2,}")
#: Reserved on Windows, whatever the extension; a folder named this cannot be opened there.
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}
_MAX = 64  # keeps the whole path well inside the limits a deep project tree still has to fit


def folder_name(name: str) -> str:
    """The folder name for a project called `name`: its words, joined by `_`.

    Accents fold to their plain letters ("Mantén" -> "Manten") and anything else is dropped, so
    the result holds no space, quote, newline or shell character. Never empty, never a name
    Windows reserves, never longer than 64 characters.
    """
    folded = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    slug = _RUNS.sub("_", _KEEP.sub("_", folded)).strip("._-")[:_MAX].strip("._-")
    if not slug or slug.split(".")[0].upper() in _RESERVED:
        slug = f"project_{slug}" if slug else "project"
    return slug


def folder_for(parent: Path | str, name: str) -> Path:
    """A folder under `parent` for a project called `name`, free for it to be created in.

    Two names that fold to one slug ("A/B run" and "A B run") would otherwise open the same
    folder and write over each other's project, so the second gets `_2`, the third `_3`.
    """
    parent = Path(parent)
    base = folder_name(name)
    candidate = parent / base
    for n in range(2, 1000):
        if not candidate.exists():
            return candidate
        candidate = parent / f"{base}_{n}"
    return candidate
