"""Measure the two implementations and render the panel, for the case document.

Counts *code* lines only — blank lines, comments and docstrings excluded — so the
comparison is not inflated by the explanatory prose in either file.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtWidgets import QApplication  # noqa: E402


def code_lines(path: Path) -> int:
    """Non-blank lines that are neither comments nor docstring bodies."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))

    n = 0
    for i, line in enumerate(src.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("#") or i in doc_lines:
            continue
        n += 1
    return n


app = QApplication([])

from trough_panel import TroughPanel  # noqa: E402
from trough_panel_handcoded import TroughPanelHandCoded  # noqa: E402

ui_py = code_lines(HERE / "trough_panel.py")
hand_py = code_lines(HERE / "trough_panel_handcoded.py")
ui_xml = len((HERE / "trough_panel.ui").read_text(encoding="utf-8").splitlines())

print(f"{'implementation':<42}{'python':>8}{'other':>8}")
print("-" * 58)
print(f"{'trough_panel.py + trough_panel.ui':<42}{ui_py:>8}{ui_xml:>8}  (.ui, Designer-managed)")
print(f"{'trough_panel_handcoded.py':<42}{hand_py:>8}{0:>8}")
print("-" * 58)
print(f"Python a human writes and maintains: {ui_py} vs {hand_py} "
      f"({hand_py - ui_py} fewer lines, {100 * (hand_py - ui_py) // hand_py} %)")

READINGS = {"pressure": 22.41, "area": 145.2, "temperature": 21.8, "barrier": 63.5}


def render(cls, mode: int, out: str) -> None:
    panel = cls()
    panel.resize(460, 380)
    panel.update_readings(READINGS)
    panel.set_mode(mode)
    panel.spin_pressure.setValue(30.0)
    panel.spin_area.setValue(145.0)
    panel.set_status("Running — simulation")
    panel.grab().save(str(HERE / out))


# Both modes, to show the dropdown. Both implementations, to show they agree.
render(TroughPanel, 0, "trough_panel.png")
render(TroughPanel, 1, "trough_panel_area_mode.png")
render(TroughPanelHandCoded, 0, "trough_panel_handcoded.png")

print("\nrendered trough_panel.png, trough_panel_area_mode.png, "
      "trough_panel_handcoded.png")
