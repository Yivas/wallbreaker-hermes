"""Where Wallbreaker keeps downloaded corpora and batteries.

An installed package can live in a read-only location — the protected Windows runtime does — and a
download into it fails with ``WinError 5``. One resolver decides the directory for every consumer,
so a new cache does not reintroduce the problem by building its own path.
"""

from __future__ import annotations

import os
from pathlib import Path

LIBRARY_DIR_ENV = "WALLBREAKER_LIBRARY_DIR"


def user_data_dir() -> str:
    """Per-user data directory, chosen by environment rather than by platform name.

    Reading the environment keeps this testable on any system: a Windows profile advertises
    LOCALAPPDATA, and everything else falls back to the XDG directory or the home directory.
    """
    for var in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(var)
        if base:
            return str(Path(base) / "wallbreaker-hermes")
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return str(base / "wallbreaker-hermes")


def writable(path: Path) -> bool:
    """Whether a real write succeeds there.

    ``os.access`` cannot answer this on Windows: it looks at the read-only attribute, not the ACL,
    so a protected install reports writable and the download then dies with ``WinError 5``. Writing
    a probe costs one file and is the only dependable check.
    """
    probe = path / ".write-probe"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def library_dir() -> Path:
    """Writable directory for downloaded material.

    An explicit env var wins, then the package directory when a write really works there — a
    checkout keeps using its own ``library/`` — and otherwise the per-user data directory.
    """
    configured = os.environ.get(LIBRARY_DIR_ENV)
    if configured:
        return Path(configured)
    packaged = Path(__file__).resolve().parent.parent / "library"
    if writable(packaged):
        return packaged
    return Path(user_data_dir()) / "library"
