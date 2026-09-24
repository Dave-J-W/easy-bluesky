# easy-bluesky fork: editability, hutch separation, and surviving upstream

**Date:** 2026-09-24
**Status:** design, approved in outline; implementation plan not yet written
**Scope:** how we build on `nayanbera/easy-bluesky` — the client's editability and display
performance, and a second queue-server for our hutch — without fighting an upstream that
lands about six commits a day.

**Upstream's default branch is `master`, not `main`.** Every command below says `master`
deliberately.

Paths use `%USERPROFILE%` rather than the literal Windows username, because this document
is meant to be readable in a fork we share with the upstream author.

---

## 1. Why this exists

We set out to choose a GUI for an EPICS + Bluesky operator surface. Partway through, the
answer changed: a colleague already built one. `easy-bluesky` is a PyQt6 client with
pyqtgraph plots, ZMQ to `bluesky-queueserver`, direct Channel Access coalesced at 10 Hz, a
visual plan composer, MongoDB/HDF5 browsers and `lmfit` curve fitting. Rebuilding that
would be waste.

So the question stopped being *which stack* and became *how do we build on this one*. Two
constraints shape everything:

1. **We need our own queue-server, in the same format,** to separate our experimental
   hutch — or at minimum to separate the things that do not need sharing.
2. **Upstream is actively developed by a colleague we work with closely.** We want to
   improve things gently and contribute back, which makes repo discipline a design
   constraint rather than an afterthought.

A third motivation is ours alone. We like Phoebus because the display editor is good
enough that we change screens ourselves, without an agent. Any surface we adopt should
keep that property. `easy-bluesky` currently does not, and that is the one real gap.

### Upstream has precedence, and the pace is a feature

Nothing below is a complaint about the rate of change. Six commits a day on a two-month-old
project is a project being actively led, and it is the reason building on it beats starting
over. The churn table in §2.1 exists to let us *route around* that work, not to slow it
down: files upstream is actively shaping are files we should not be editing, and knowing
which ones those are is what lets us add panels without ever landing in someone's way.

Where our judgement differs from upstream's, upstream wins by default. We propose rather
than patch, we add files rather than edit them, and anything generally useful goes back as
a PR. `docs/ours/ui-demo/` is what that looks like in practice — a working demonstration
offered for judgement, with "no" listed as an acceptable answer.

---

## 2. What we measured

Everything below was measured on this machine on the date given. Claims are tagged
MEASURED, DERIVED or PROVISIONAL; the tag matters more than the claim, because an
untagged assertion cannot be audited later.

### 2.1 Upstream file churn — the single most important input

Commits per file over the 31 days to 2026-09-24 (MEASURED from full local history after
cloning). These supersede an earlier GitHub-API count, which undercounted: it reported 7
commits for `plot_tools.py` against the true 13, and missed `experiments_tab.py` entirely.

| file | commits | verdict |
|---|---:|---|
| `easy_bluesky/main.py` | **40** | radioactive |
| `easy_bluesky/experiments_tab.py` | **35** | radioactive |
| `easy_bluesky/mongo_browser.py` | 26 | very hot |
| `easy_bluesky/worker.py` | 16 | very hot |
| `easy_bluesky/devices_plans_tab.py` | 15 | hot |
| `easy_bluesky/live_viewer.py` | 14 | hot |
| `easy_bluesky/plot_tools.py` | 13 | hot |
| `easy_bluesky/ad_viewer.py` | 12 | hot |
| `easy_bluesky/hdf5_viewer.py` | 11 | hot |
| `easy_bluesky/widgets.py` | 8 | hot |
| `easy_bluesky/scripts/re_startup_mongo.py` | 4 | warm |
| `easy_bluesky/config.py` | 1 | cold |
| `easy_bluesky/themes.py` | **0** | cold |
| `easy_bluesky/styles.py` | **0** | cold |
| `easy_bluesky/scripts/start_re_managers.sh` | **0** | cold |
| `easy_bluesky/scripts/re_startup_sim.py` | **0** | cold |

Overall: **185 commits in 31 days** — about six a day sustained, bursting to ten (40 in the
four days 2026-09-20 → 2026-09-23). The first commit is **2026-07-19**, so this is a young
project, barely two months old and still finding its shape. That raises the odds of a large
refactor landing under us, which is a further argument for short branches.

Reproduce with:

```bash
git log --since="2026-08-24" --name-only --pretty=format: -- 'easy_bluesky/*' \
  | grep -v '^$' | sort | uniq -c | sort -rn | head -20
```

**Why this matters:** it converts fork discipline from opinion into arithmetic. A change
in a zero-commit file is nearly free; a change in `main.py` will conflict on most rebases.
Every decision in §3 follows from this table.

### 2.2 Display performance

Same workload both times — 8 traces, 4 panels, forced render, offscreen (MEASURED
2026-09-22):

| engine | points/trace | downsample + clipToView | median | duty @ 250 ms |
|---|---:|:---:|---:|---:|
| matplotlib, full `fig.clear()` | 720 | n/a | 106.3 ms | 42.5 % |
| pyqtgraph | 720 | off | **3.59 ms** | 1.4 % |
| pyqtgraph | 7,200 | off | 13.0 ms | 5.2 % |
| pyqtgraph | 72,000 | off | 95.0 ms | 38.0 % |
| pyqtgraph | 72,000 | **on** | **23.7 ms** | 9.5 % |

pyqtgraph is 29.6× faster than a matplotlib full redraw at the same job.

**Why this matters:** display performance is *not* a problem to solve — upstream already
chose correctly. The only live decision is history depth, and the levers earn nothing
below ~10k points and about 4× above.

### 2.3 Qt on this machine

- `pip install PySide6` (6.11.2) into a venv built on Anaconda →
  `ImportError: DLL load failed while importing QtCore` (MEASURED 2026-09-22).
- `conda create -c conda-forge python=3.12 pyside6 pyqtgraph` → imports cleanly, Qt 6.11.2
  (MEASURED 2026-09-22).
- **Why:** conda-forge Qt depends on `vc14_runtime` 14.51 and installs it; Anaconda's base
  has 14.29 already resident, loaded before Qt gets a say, so a pip wheel built against the
  VS2022 14.4x runtime loses. `os.add_dll_directory` does not help — the wrong DLL is
  already in memory.
- conda-forge carries the whole stack at parity: `pyqt6` 6.11.0, `pyside6` 6.11.2,
  `pydm` 1.29.0, `typhos` 4.3.0, `pyqtgraph` 0.14.0, `bluesky` 1.15.1, `ophyd` 1.11.2,
  `caproto` 1.3.0, `tiled` 0.2.18 (MEASURED, `conda search`).
- Qt Designer **6.11.2** is already installed at
  `%USERPROFILE%\AppData\Local\anaconda3\envs\shg\Library\lib\qt6\bin\designer.exe`, which
  matches conda-forge `pyqt6` 6.11.0 (MEASURED).

Two incidental traps, both hit while establishing the above: Windows long-path support is
**off** (`LongPathsEnabled = 0`), so PySide6 fails to install under deep paths; and
Anaconda ships pip 24.0, which cannot parse `shiboken6` 6.11.2's metadata.

### 2.4 The editability gap

`easy-bluesky` contains **no `.ui` files and no runtime UI loading** — MEASURED against the
local clone, which is definitive where the earlier remote checks were not:

```bash
find . -name "*.ui" -not -path "*/.git/*" | wc -l          # 0
grep -rn --include=*.py -E "loadUi|QUiLoader|pyuic" .      # no matches
```

An earlier GitHub code search agreed, but returned `incomplete_results: true` and so was
never sound evidence; the local clone is. Corroborating: `docs/architecture.md`'s "New tab"
recipe describes writing a `QWidget` subclass in Python.

All layout therefore lives in code, in modules of this size: `experiments_tab.py` 166 KB,
`main.py` 122 KB, `mongo_browser.py` 111 KB, `plan_builder.py` 110 KB,
`connection_settings.py` 96 KB.

**Why this matters:** every cosmetic or layout change is a code edit inside a file too
large to hold in context comfortably. That is precisely the property that makes Phoebus
pleasant and this painful, and it is the one thing worth fixing.

### 2.5 Queue-server separation

- `connection.json` holds "profiles, ports, SSH settings" and is **local, never committed**
  (`docs/architecture.md`, MEASURED).
- `start_re_managers.sh` defines a generic `start_instance(name, script, ctrl, info)` but
  calls it exactly twice, hardcoded `"real"` (60615/60625) and `"sim"` (60616/60626)
  (MEASURED, file read).
- Upstream already handles multiple clients against one RE Manager: an operator lock,
  "Take Control", and an amber banner for foreign plans (MEASURED, commit log
  2026-09-21/22).

**Why this matters:** the client side needs no change at all, and the server side needs a
change only in a file with zero recent commits.

---

## 3. Decisions

### D1 — Take Qt and the Bluesky stack from conda-forge; pip last, for the remainder only

**Why:** §2.3. This is the same failure mode that already broke the Anaconda base env's
numpy/matplotlib ABI (conda numpy 1.26.4, then pip numpy 2.5.x over the top). One rule
prevents both. Anaconda itself is a good choice here — the team knows it, switching envs
is easy, and conda-forge solves a problem pip cannot.

Deliverable: `environment.yml` in the fork, plus a short note that pip-installed Qt is
unsupported on this machine and why.

### D2 — Hutch separation is configuration plus one cold-file change

**Why:** §2.5. Splitting it this way means our hutch costs upstream nothing and costs us
almost no divergence.

- *Client:* nothing. Each hutch gets a `connection.json` profile with its own ports. The
  file is never committed, so it cannot conflict.
- *Server:* generalize `start_re_managers.sh` from two hardcoded calls to a data-driven
  instance table, and add `re_startup_<hutch>.py` as a **new** file. Both sit in
  zero-commit territory.
- *Ports:* allocate a distinct block per hutch, clear of 60615/60625 and 60616/60626.
- *Upstream:* offer the N-instance generalization as a PR. It serves upstream's own
  real+sim case, so it is an easy yes and it leaves our fork.

### D3 — Never edit `main.py`; make tabs self-register instead

**Why:** §2.1. Upstream's documented way to add a tab is two lines in `main.py`, the file
with 38 commits in 30 days. Those two lines would conflict on most rebases, forever, for a
feature that is otherwise purely additive.

Instead, PR upstream a small entry-point-based tab registry so tabs register themselves and
`main.py` stops being edited for every new tab. That deletes a conflict magnet for
*everyone*, including upstream, which is what makes it a plausible PR rather than a
favour. Until it merges, carry it as a single patch at `patches/0001-tab-registry.patch`,
re-applied on each rebase — one known conflict site instead of one per feature.

### D4 — Layout in runtime-loaded `.ui` files, edited in Qt Designer

**Why:** §2.4, and the Phoebus property we want to keep. If a `.ui` is loaded at runtime it
is a *data file*: open it in Designer, drag, save, relaunch. No rebuild, no agent. That is
structurally the same workflow as editing a `.bob`.

- **Never run `pyuic`.** Code generation makes the `.py` the source of truth and silently
  clobbers hand edits on the next regeneration, which destroys the entire benefit.
- Designer 6.11.2 is already installed and version-matched (§2.3) — no new tooling.
- **New panels only.** We do not convert `experiments_tab.py` or any other large module.
  Conversion would be a large diff in hot files, i.e. the worst possible trade.
- A headless test asserts every `.ui` in the tree loads. `pytest-qt` is already an upstream
  dev dependency, so this costs no new packages.

### D5 — Gate pyqtgraph's downsampling on history depth, not by default

**Why:** §2.2. `setDownsampling(auto=True)` plus `setClipToView(True)` cost slightly more
than they save at 720 points and save ~4× at 72,000. Switching them on reflexively is
cargo cult; switching them on as a function of history length is measured.

### D6 — Fork discipline

**Why:** §2.1. At ten commits a day, divergence compounds fast and quietly.

1. `master` is a pure mirror of upstream. Never commit to it.
2. Work on topic branches; **rebase** onto upstream, never merge, so our work stays a
   clean, reviewable patch series.
3. Rebase often — at this cadence, weekly is already too slow.
4. Prefer new files. New files never conflict.
5. Keep a **divergence budget** — the diff against upstream restricted to files we
   *modified* rather than added, since added files cannot conflict:

   ```bash
   git diff --stat --diff-filter=M upstream/master...HEAD
   ```

   Review it at every rebase. Anything generally useful gets PR'd upstream promptly so it
   leaves the fork.
6. Set the commit identity on the repo before the first commit; global identity on this
   machine is unset and defaults to the wrong author.

---

## 4. Sub-projects

| # | Sub-project | Depends on | Conflict surface |
|---|---|---|---|
| 0 | Environment (`environment.yml`) | — | new file |
| 1 | `.ui` convention: one real panel, loader helper, load-test | 0 | new files + D3 patch |
| 2 | Hutch queue-server: instance table + `re_startup_<hutch>.py` | 0 | one cold file + new file |
| 3 | Instrument device panels as `.ui` | 1 | new files |
| 4 | Live data panel, with D5's gating | 1 | new files |
| 5 | Run history / analysis | 0 | new files |

**Build 1 first.** It is small, it is the actual open question, it is fully testable under
the simulation-only constraint, and building it settles three things currently unverified:
PyDM under PyQt6, the Designer→`uic` round-trip at 6.11, and Designer plugin registration.

---

## 5. A CLAUDE.md for the fork

Tight on purpose. An agent that reads only this should not be able to cause a merge
disaster.

```markdown
# easy-bluesky (our fork)

Fork of nayanbera/easy-bluesky. Upstream lands ~10 commits/day. Our job is to add
panels without accumulating divergence.

## Never do these
- **Never edit `easy_bluesky/main.py`.** 38 commits in 30 days. Tabs self-register via
  the entry-point registry; if that is not merged yet, the patch is in
  `patches/0001-tab-registry.patch` — re-apply it, do not hand-edit main.py.
- **Never run `pyuic`.** `.ui` files are loaded at runtime with `uic.loadUi`. Generating
  Python from them makes the `.py` authoritative and clobbers hand edits.
- **Never `pip install` Qt.** Pip-built Qt6 fails here with
  `ImportError: DLL load failed while importing QtCore`. Qt comes from conda-forge.
- **Never commit to `master`.** It mirrors upstream. Work on a topic branch.
- **Never merge upstream.** Rebase, so our work stays a clean patch series.
- **Never create or write a PV.** Simulation only until a prefix is approved.

## Hot files — avoid touching
`main.py` (38), `widgets.py` (8), `plot_tools.py` (7) — commits in the last 30 days.
Edits here conflict. Cold and safe: `config.py`, `scripts/start_re_managers.sh`,
`scripts/re_startup_*.py`.

## Prefer
- New files over edits. New files never conflict.
- Layout in `.ui`, edited in Designer 6.11.2 (already installed, version-matched).
- Anything generally useful → PR upstream, so it leaves our fork.

## Environment
conda-forge only, from `environment.yml`. pip last, and only for what conda-forge lacks.

## Before every push
    git fetch upstream && git rebase upstream/master
    pytest                                            # includes the .ui load test
    git diff --stat --diff-filter=M upstream/master...HEAD   # the divergence budget

## Commit identity
Set it on the repo before the first commit — the global identity here is unset and
defaults to the wrong author.
```

---

## 6. Testing

- **`.ui` load test** — every `.ui` in the tree loads under `uic.loadUi` with an offscreen
  Qt platform. Catches a Designer/`uic` version mismatch the moment it appears.
- **Panel smoke test** — each new panel constructs, takes one simulated update, and
  renders, via `pytest-qt`.
- **No-hardware rule** — the whole suite runs with no EPICS, no serial port and no queue
  server, mirroring upstream's sim profile.
- **Divergence check** — a CI or pre-push step printing the divergence budget, so growth is
  visible rather than discovered at rebase time.

---

## 7. Risks

- **Upstream may not want the `.ui` convention.** It is one person's active design space.
  *Mitigation: ask nayanbera before building much.* A ten-minute conversation is cheaper
  than a rejected PR, and if he prefers layout in Python we need to know before
  sub-project 1, not after.
- **The tab-registry PR may stall.** Then we carry one patch indefinitely. Tolerable — one
  known conflict site — but it should be measured in the divergence budget, not forgotten.
- **Upstream may refactor under us.** At this cadence, a large refactor is plausible. Short
  branches and frequent rebases are the only real defence.
- **PyDM under PyQt6 is unverified.** We resolved its dependencies and tested PySide6, not
  PyDM on PyQt6. Sub-project 1 settles it; until then it is PROVISIONAL and nothing should
  depend on it.

---

## 8. Explicitly not doing

- Not converting existing tabs to `.ui`.
- Not touching `mongo_browser.py`, `live_viewer.py`, `experiments_tab.py`.
- Not replacing Phoebus. It stays the device-screen editor; its `WebBrowserWidget`
  (properties `url` and `show_toolbar` only, no `pv_name`, JavaFX 21 WebKit) is at most a
  frame for a static run-history page, not a host for live control.
- Not serving PVs. Simulation only; the prefix conversation is deferred to whenever a soft
  IOC actually appears.
- Not adopting `bluesky-widgets` (0.0.18, quiet) as a foundation.

---

## 9. Open questions

1. Does nayanbera accept the `.ui` convention and the tab registry? **Blocks sub-project 1.**
2. Which port block for our hutch?
3. Fork visibility — if it is ever public, the Windows username must be scrubbed from
   paths first.
