#!/usr/bin/env python3
"""Where things live, whether running from source or from a bundled .exe.

PyInstaller's one-file mode unpacks everything into a temporary directory and
points `__file__` at it. That directory is deleted on exit, so anything the
user edits or that we want to keep - config.json, the logs - must sit next to
the .exe instead. Read-only resources we ship, like the font, come from the
bundle.

    app_dir()     next to the .exe (or the source folder)   - writable, kept
    bundle_dir()  inside the bundle (or the source folder)  - read-only
"""

from __future__ import annotations

import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
_SOURCE_DIR = Path(__file__).resolve().parent


def app_dir() -> Path:
    """Beside the executable. Config and logs go here so they survive."""
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return _SOURCE_DIR


def bundle_dir() -> Path:
    """Inside the bundle. Shipped resources are read from here."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", _SOURCE_DIR))
    return _SOURCE_DIR


def config_path() -> Path:
    """config.json beside the exe, seeded from the bundled default first run.

    A single downloaded .exe should just work, and then leave an editable file
    behind rather than hiding its settings inside itself.
    """
    live = app_dir() / "config.json"
    if not live.exists():
        packaged = bundle_dir() / "config.json"
        if packaged.exists() and packaged != live:
            try:
                live.write_text(packaged.read_text(encoding="utf-8"),
                                encoding="utf-8")
            except Exception:
                return packaged
    return live


def resource(*parts) -> Path:
    return bundle_dir().joinpath(*parts)
