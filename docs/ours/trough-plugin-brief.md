# Brief: trough control plug-in (software side)

**For:** an implementing agent
**Date:** 2026-10-01
**Reference implementation:** `docs/ours/ui-demo/` — read it first, then copy its shape
**Scope:** software only. No hardware, no serial ports, no Channel Access.

---

## 1. What to build

A trough control plug-in for our fork of `easy-bluesky`: a panel that shows trough
readouts and offers pressure/area control, as a self-registering tab.

**It must not know how the trough is reached.** It receives readings and sends commands
through the two interfaces in §3. Whoever writes the hardware adapter is a different job,
and a `FakeTroughSource` is what you develop and test against.

`docs/ours/ui-demo/` already contains a working panel with exactly this property —
`TroughPanel.update_readings()` takes a plain mapping and does no I/O. **Start by copying
it**, not from scratch.

---

## 2. Non-negotiables

These come from `docs/ours/2026-09-24-fork-design.md` and `CLAUDE.local.md`. Read both.

1. **Layout goes in a `.ui` file, loaded at runtime with `uic.loadUi`.** Reuse
   `ui-demo/ui_loader.py` rather than writing another loader.
2. **Never run `pyuic`.** Generating Python from the `.ui` makes the `.py` authoritative and
   silently discards hand edits. The whole point is lost.
3. **Discover readout rows from the `.ui`**, as the reference does: a row is a
   `val_<field>` label with `lbl_<field>` and `unit_<field>` beside it. Do **not** hardcode
   the field list in Python — a scientist adding a row in Designer must need no code change.
4. **Add files; do not edit upstream's.** Specifically never touch `main.py`,
   `experiments_tab.py`, `devices_plans_tab.py`, `mongo_browser.py`, or `worker.py`. Check
   current churn before touching anything — `CLAUDE.local.md` has the command.
5. **Qt comes from conda-forge, never pip.** Use the existing env at `%USERPROFILE%\.conda\eb`
   (PyQt6 6.11.0 / Qt 6.11.2).
6. **Reading PVs is fine; writing a PV needs explicit human approval every time.** You
   should not need either — you are behind the interfaces in §3.
7. Branch off `upstream/master`, rebase rather than merge, commit as `Dave-J-W`.

---

## 3. The interfaces you code against

Shaped to match `docs/ours/refactoring-plan.md`: commands never block and return a Future;
state arrives as events. Define these as `typing.Protocol` so a fake satisfies them.

```python
Readings = Mapping[str, float]          # {"pressure": 22.41, "area": 145.2, ...}

class TroughSource(Protocol):
    """Where readouts come from. One call, no I/O guarantees, never blocks the UI."""
    def latest(self) -> Readings: ...
    def subscribe(self, callback: Callable[[Readings], None]) -> None: ...

class TroughCommands(Protocol):
    """Every command is a request, not an action. Returns Future[Result(ok, msg, data)]."""
    def set_mode(self, mode: Literal["pressure", "area"]) -> Future: ...
    def set_setpoint(self, mode: str, value: float) -> Future: ...
    def start(self) -> Future: ...
    def stop(self) -> Future: ...
```

Rules for the panel:

- The panel **never blocks**. Attach continuations to the Future; do not call `.result()`
  on the Qt main thread.
- The panel **never decides policy** — it does not clamp a setpoint, retry, or interpret
  limits. It displays what it is given and reports what it is told. Policy belongs in the
  service.
- Confirmation dialogs stay in the panel. Anything that would move hardware must be
  confirmed by the operator in the UI before the command is sent.
- A field with no reading shows `--`. Never a stale number.
- Every displayed value carries the unit the `.ui` declares for it.

---

## 4. Deliverables

```
easy_bluesky_trough/            (new package — additive, conflicts with nothing)
  trough_tab.ui                 layout, Designer-authored
  trough_tab.py                 behaviour only; loads the .ui
  interfaces.py                 the Protocols from §3
  fake_source.py               FakeTroughSource + FakeTroughCommands
  test_trough_tab.py            see §5
  README.md                     how to run it against the fake
```

Plus: registration via the entry-point tab registry **if** it has landed. If it has not,
do **not** edit `main.py` — ship the tab importable and standalone, and say so in the
README.

---

## 5. Tests (all headless, no hardware)

Copy the patterns from `ui-demo/test_ui_demo.py`. Required:

1. **Every `.ui` loads** — reuse `iter_ui_files`.
2. **Rows are complete** — no `val_*` without its `lbl_*` and `unit_*`.
3. **The field set is not in Python** — assert readout field names do not appear in
   `trough_tab.py`. The reference has this test; it is the one that keeps rule 3 honest.
4. **An edited `.ui` works unmodified** — ship a second `.ui` with an extra row and assert
   the same class handles it. This is the deliverable's main claim; prove it.
5. **Readings render** — values formatted with units, missing field shows `--`.
6. **Commands are requests** — clicking Apply calls `set_setpoint` on a fake and does not
   block; assert the call, not an effect.
7. **Confirmation gate** — a command that would move hardware is not sent when the
   operator declines.

Run with:

```bash
QT_QPA_PLATFORM=offscreen ~/.conda/eb/python.exe -m pytest easy_bluesky_trough -q
```

---

## 6. Out of scope

- Any hardware driver, serial port, socket, opcode or motion command.
- Channel Access, PV creation, soft IOCs.
- Editing upstream files, including `main.py`.
- The entry-point tab registry itself (separate proposal).
- Deciding which physical trough this targets — that is a separate, human decision, and
  nothing in this brief depends on the answer.

## 7. Done when

All seven tests pass headless; the panel runs against `FakeTroughSource`; a reviewer can
add a readout row in Designer, re-run the suite, and see the new row without touching
Python. Report the measured line counts the way `ui-demo/measure.py` does.
