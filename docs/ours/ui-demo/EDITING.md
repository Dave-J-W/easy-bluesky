# Editing a panel yourself

No Python, no agent. This is the workflow the `.ui` proposal exists to enable, written for
whoever needs a panel changed — including during a beamtime.

---

## Opening the editor

Qt Widgets Designer is already installed inside the demo environment and
**version-matched to the Qt that runs the app** (both 6.11.2). Use that one — other
`designer.exe` copies on this machine belong to other environments.

**Use the launcher.** From PowerShell, in `docs/ours/ui-demo`:

```powershell
.\edit_panel.ps1
```

or `.\edit_panel.ps1 trough_panel_extended` for the other one.

### Do not launch `designer.exe` directly — it fails silently

Both of these were hit on 2026-10-01 and neither is obvious:

| how | what happens |
|---|---|
| from **Git Bash** | `designer.exe: error while loading shared libraries: Qt6Core.dll` |
| from **PowerShell**, exe path only | a process starts, **never opens a window**, and prints *nothing*. `MainWindowHandle` stays `0` and the working set sits at ~5 MB instead of ~98 MB |

The cause is the same both times: `Qt6Core.dll` sits beside `designer.exe`, but *its* own
dependencies — ICU, pcre2, zstd, zlib — live in the env's `Library\bin`. Without that
directory on `PATH`, Qt cannot initialise, and it does not say so. The launcher prepends it
along with `QT_PLUGIN_PATH`, then checks the window actually appeared and tells you if it
did not.

If you want it on the taskbar, pin a shortcut to the launcher, not to `designer.exe`.

---

## The loop

**Edit → Save → Test → Look.** Four steps, and only the first needs you.

### 1. Edit

In Designer, the panel appears as you will see it. The **Object Inspector** (top right)
shows the widget tree; the **Property Editor** (bottom right) shows the selected widget's
properties.

### 2. Save

`Ctrl+S`. That is the whole commit of your change — the file Designer writes *is* what the
app loads.

### 3. Test

```bash
QT_QPA_PLATFORM=offscreen "$HOME/.conda/eb/python.exe" -m pytest docs/ours/ui-demo -q
```

Expect `20 passed`. If you broke something structural, this names it — see
[When it goes wrong](#when-it-goes-wrong).

### 4. Look

```bash
"$HOME/.conda/eb/python.exe" docs/ours/ui-demo/measure.py
```

Rewrites `trough_panel.png` with live sample values so you can check the result.

---

## Three edits worth practising

### Rename a label

Click the text in the panel, type the new text, `Ctrl+S`. Done — e.g. **Area** →
**Trough area**.

Do not confuse the two things called "name":

| | what it is | safe to change? |
|---|---|---|
| `text` property | what the operator reads | **yes, freely** |
| `objectName` | how Python finds the widget | **no** — see below |

### Add a readout row

The readouts are a 3-column grid: caption, value, unit.

1. Drag three **Label** widgets from the box on the left into the grid, on a new bottom row.
2. Set their `text` to e.g. `Subphase pH`, `--`, `pH`.
3. Set their `objectName` to `lbl_ph`, `val_ph`, `unit_ph`.
4. `Ctrl+S`.

That is all. The panel **discovers readout rows from this file**, so the new row appears and
updates with no Python change. The `_ph` suffix is the field name the data source will use.

> Already done for you as a worked example: `trough_panel_extended.ui` is this panel after
> exactly this edit (plus a relabel and a reorder). Open both side by side to compare.

### Reorder or regroup

Drag a group box above another, or drag widgets between groups. Layout order in the file is
layout order in the app. Nothing in Python cares.

---

## What you cannot break

This is the real reason this is safe to hand to a scientist.

**Designer cannot reach the panel's behaviour.** `update_readings`, the button
connections, the units logic — none of it is exposed by the tool. You can make the panel
look wrong; you cannot make it *do* the wrong thing.

The two ways to cause a real problem, and both are caught:

1. **Changing an `objectName` that Python looks up** — `btn_apply`, `combo_mode`,
   `setpoint_stack`, `spin_pressure`, `spin_area`, `status`, `title`. Rename one and the
   panel loses that control. The test suite fails and names it.
2. **A half-finished row** — a `val_*` without its `lbl_*` and `unit_*`. The suite reports
   which field, by name.

Both are a `Ctrl+Z` away.

---

## When it goes wrong

| the suite says | what happened | fix |
|---|---|---|
| `AttributeError: 'TroughPanel' object has no attribute 'btn_apply'` | an `objectName` Python needs was renamed or deleted | restore the name |
| `incomplete_rows() == ('ph',)` | the `ph` row is missing its caption or unit label | add the missing `lbl_ph` / `unit_ph` |
| `no .ui file at ...` | the file was renamed or moved | put it back, or pass the new stem |
| Designer will not open the file | the XML was hand-edited and is malformed | `git checkout` the file and redo in Designer |

Nothing here needs a programmer. If in doubt:

```bash
git checkout docs/ours/ui-demo/trough_panel.ui
```

and start again — the file is version-controlled, so no edit is irreversible.

---

## The rule for whoever maintains this

**Never run `pyuic`.** It compiles the `.ui` into Python, and from then on people edit the
Python and the next regeneration throws their work away. Every benefit above depends on the
`.ui` staying the thing that is loaded, at runtime, as data.
