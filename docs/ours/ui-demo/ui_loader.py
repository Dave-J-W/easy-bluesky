"""Load a Qt Designer .ui file at runtime.

This is the whole mechanism. There is no build step and no generated code: the .ui is a
data file that Designer writes and the app reads, exactly the way Phoebus reads a .bob.

The rule that makes it work is negative: **never run pyuic**. The moment a .ui is compiled
to Python, the .py becomes the thing people edit, and the next regeneration silently
discards those edits. Keeping the .ui authoritative is what buys the editability.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QWidget


def load_ui(ui_name: str, target: QWidget, base_dir: Path | None = None) -> QWidget:
    """Load ``<ui_name>.ui`` into ``target`` and return it.

    Child widgets become attributes of ``target`` under their Designer object names, so
    ``self.val_pressure`` works immediately after the call.

    Raises FileNotFoundError with the searched path rather than Qt's opaque failure,
    because a missing .ui is otherwise diagnosed as a mysteriously empty panel.
    """
    base = base_dir or Path(__file__).resolve().parent
    path = base / f"{ui_name}.ui"
    if not path.is_file():
        raise FileNotFoundError(f"no .ui file at {path}")
    uic.loadUi(path, target)
    return target


def iter_ui_files(root: Path) -> list[Path]:
    """Every .ui under ``root``. Used by the load test so new panels are covered
    automatically rather than needing to be added to a list someone forgets."""
    return sorted(p for p in root.rglob("*.ui") if ".git" not in p.parts)
