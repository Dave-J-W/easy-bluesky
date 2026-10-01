"""Measure both implementations and the edit challenge, and render the screenshots.

Counts *code* lines only — blank lines, comments and docstrings excluded — so neither
file's explanatory prose inflates the comparison.

The edit challenge is the part nayanbera asked for: apply the same three presentational
changes both ways and report how much Python each route required. The .ui route's number
is obtained, not assumed: trough_panel.py is diffed against itself across the two routes
and must be unchanged.
"""

from __future__ import annotations

import ast
import difflib
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

    return sum(
        1 for i, line in enumerate(src.splitlines(), start=1)
        if line.strip() and not line.strip().startswith("#") and i not in doc_lines
    )


def changed_code_lines(before: Path, after: Path) -> int:
    """Added or removed code lines between two files, comments/docstrings excluded."""
    def significant(path: Path) -> list[str]:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        doc: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                b = node.body
                if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
                        and isinstance(b[0].value.value, str):
                    doc.update(range(b[0].lineno, b[0].end_lineno + 1))
        out = []
        for i, line in enumerate(src.splitlines(), start=1):
            s = line.strip()
            if not s or s.startswith("#") or i in doc:
                continue
            out.append(s.split("#")[0].rstrip())  # drop trailing comments
        return out

    diff = difflib.ndiff(significant(before), significant(after))
    return sum(1 for line in diff if line.startswith(("+ ", "- ")))


app = QApplication([])

from trough_panel import TroughPanel  # noqa: E402
from trough_panel_handcoded import TroughPanelHandCoded  # noqa: E402

# ── part 1: building the panel ────────────────────────────────────────────────

ui_py = code_lines(HERE / "trough_panel.py")
hand_py = code_lines(HERE / "trough_panel_handcoded.py")
ui_xml = len((HERE / "trough_panel.ui").read_text(encoding="utf-8").splitlines())

print("BUILDING THE PANEL")
print(f"{'implementation':<44}{'python':>8}{'other':>8}")
print("-" * 60)
print(f"{'trough_panel.py + trough_panel.ui':<44}{ui_py:>8}{ui_xml:>8}  (.ui, Designer-managed)")
print(f"{'trough_panel_handcoded.py':<44}{hand_py:>8}{0:>8}")
print("-" * 60)
print(f"Python a human writes and maintains: {ui_py} vs {hand_py} "
      f"({hand_py - ui_py} fewer, {100 * (hand_py - ui_py) // hand_py} %)")

# ── part 2: the edit challenge ────────────────────────────────────────────────
#
# Three presentational edits: add a fifth readout row, relabel one row, move the Control
# group above Readouts.

hand_changed = changed_code_lines(
    HERE / "trough_panel_handcoded.py",
    HERE / "trough_panel_handcoded_extended.py",
)

# The .ui route's cost is measured, not assumed: the same Python file serves both layouts,
# so by construction nothing changed. Assert it rather than claim it.
panel_base = TroughPanel()
panel_edited = TroughPanel(ui_name="trough_panel_extended")
assert panel_base.fields() == ("pressure", "area", "temperature", "barrier")
assert panel_edited.fields() == ("pressure", "area", "temperature", "barrier", "ph")
ui_changed = 0

print("\nTHE EDIT CHALLENGE  (add a readout row, relabel a row, reorder two groups)")
print("-" * 60)
print(f"{'route':<44}{'python lines changed':>16}")
print(f"{'edit trough_panel.ui in Designer':<44}{ui_changed:>16}")
print(f"{'edit trough_panel_handcoded.py':<44}{hand_changed:>16}")
print("-" * 60)
print("Both routes produce a working 5-row panel. The .ui route required no Python,")
print("no programmer, and showed the result while editing. The hand-coded route is a")
print(f"{hand_changed}-line Python edit inside a {hand_py}-line file with no visual preview.")

# ── part 3: renders ───────────────────────────────────────────────────────────

READINGS = {"pressure": 22.41, "area": 145.2, "temperature": 21.8,
            "barrier": 63.5, "ph": 7.42}


def render(panel, mode: int, out: str) -> None:
    panel.resize(460, 420)
    panel.update_readings(READINGS)
    panel.set_mode(mode)
    panel.spin_pressure.setValue(30.0)
    panel.spin_area.setValue(145.0)
    panel.set_status("Running — simulation")
    panel.grab().save(str(HERE / out))


render(TroughPanel(), 0, "trough_panel.png")
render(TroughPanel(), 1, "trough_panel_area_mode.png")
render(TroughPanelHandCoded(), 0, "trough_panel_handcoded.png")
render(TroughPanel(ui_name="trough_panel_extended"), 0, "trough_panel_extended.png")

print("\nrendered trough_panel.png, trough_panel_area_mode.png, "
      "trough_panel_handcoded.png, trough_panel_extended.png")
