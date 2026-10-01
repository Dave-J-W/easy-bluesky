<!--
  Reconciled 2026-10-01. Original content by a parallel agent session (Claude Code cloud),
  2026-09-30, pushed as branch claude/relaxed-johnson-3fje1h.

  Three changes were made to land it without diverging from upstream. The plan's substance
  is unaltered.

    1. Moved docs/refactoring-plan.md -> docs/ours/refactoring-plan.md, so it sits in our
       namespace rather than upstream's.
    2. Reverted the edits to upstream's CLAUDE.md and docs/architecture.md. Their content
       is preserved verbatim in the two boxes below. docs/architecture.md had already taken
       two upstream commits since, so that edit would have conflicted.
    3. Re-authored as Dave-J-W; the original commit carried the wrong identity.
-->

# ── Reconciliation note ──────────────────────────────────────────────────────

This document was written by a parallel agent asked to look at the project from a
different angle. It is kept because its analysis is sound, not because it followed our
fork rules — it did not, and the next two boxes are the content it tried to put into
files upstream maintains.

**It is a proposal.** Upstream has precedence. Nothing here is started.

### Intended for upstream's `docs/architecture.md` (not applied)

> **Planned refactor:** [refactoring-plan.md](refactoring-plan.md) proposes separating the
> Qt UI from the services it uses, in phases. The Qt-free layers would be `core`, `services`
> and `app`, with enforced import contracts between them. It also lists the invariants to
> preserve.

### Intended for upstream's `CLAUDE.md` (not applied)

> ## Refactoring plan (proposed, not started)
>
> `docs/refactoring-plan.md` describes a phased plan to separate the UI from the services:
>
> - Qt-free `core/`, `services/` and `app/` layers under an enforced
>   `ui → app → services → core` dependency rule, checked with import-linter.
> - A serializable command/event API between the layers, with `ui/qt_bridge.py` as the only
>   module that knows both Qt and the services.
>
> The plan also lists invariants:
>
> - **A1–A8 (architectural):** targets for the refactor.
> - **D1–D8 (domain) and N1–N3 (numerical):** describe current behavior and hold today.
>   Keep them intact when changing scan numbering, plan-log matching,
>   environment-transition detection, the operator lock, the watchdog, DESC PVs, the remote
>   `function_execute` names, or the derivative/error code.
> - **N3 exception:** N3 also documents a known approximation in derivative error bars on
>   uneven x spacing. Its planned fix should land as its own behavior-changing commit.

### Relationship to the `.ui` proposal

`docs/ours/ui-demo/` proposes that panel *layout* move into Qt Designer `.ui` files. The
two are orthogonal and compose: this plan decides where logic lives, that one decides where
layout lives. Phase 3 here moves each view under `ui/` receiving a facade instead of
`worker`; a view that owns neither I/O nor its own layout is just a binding. The `PVBatch`
event defined below is already the input `TroughPanel.update_readings` accepts.

Either can be adopted without the other.

---

# Refactoring Plan: Separating the UI from the Services

**Status:** Proposed. No code has changed yet.  
**Date:** 2026-09-30  
**Baseline:** commit `e2bef38`

---

## Question

> "propose a refactoring plan for easy-bluesky that allows for complete separation of the UI from
> the underlying services"

## Answer

### Why this is needed

Today the PyQt6 widgets *are* the application. All of the following is written inside `QWidget`,
`QThread` and `QMainWindow` subclasses:

- RE Manager/ZMQ communication
- SSH/SFTP
- EPICS CA
- MongoDB
- HDF5/JSONL files
- experiment bookkeeping
- safety interlocks

As a result, none of it can run, be tested, or be reused without a GUI. Evidence from the
baseline tree:

- **Qt everywhere.** 28 of the 37 modules in `easy_bluesky/` import PyQt6 at import time.
  Every module that talks to the RE Manager, EPICS, MongoDB or HDF5 is among them. So is
  `ssh_manager.py`: it imports `profile_slug` from `connection_settings.py`, a 2,297-line file
  that mixes the profile schema with Qt dialogs.
- **Business logic in the window.** `main.py` (2,743 lines) handles:
  - operator locking (4-hour staleness rule)
  - client heartbeats
  - queue loop and auto-start
  - abort/stop-after-pause retries
  - busy-retries for `queue_start`/`mv`
  - SSH diagnostics and SFTP uploads
- **Safety logic in widgets.** Two safety behaviours only work while their tabs exist:
  - PV Watchdog auto-pause/resume is `PVWatchdogTab._evaluate`.
  - Pausing when the experiment folder disappears is `ExperimentsTab._handle_exp_dir_lost`.
- **Blocking I/O on the Qt main thread.**
  - `worker.connect()` does a 3 s TCP probe plus a ZMQ `status()` call. It is called directly on
    the main thread from `_on_reconnect_requested`, `_on_profile_changed`,
    `_on_connection_settings` and `_auto_reconnect_mode`.
  - Every queue/RE command (`queue_start`, `add_item`, …) runs synchronously in a UI handler
    behind `_rm_lock`.
  - `PlanBuilder._poll_for_env_ready` calls `worker.rm.status()` on the UI thread.
- **Duplicated rules that have already drifted.**
  - Parsing the RE status into an environment state is written six times: in `worker.py`,
    `main.py`, `experiments_tab.py`, `queue_manager.py`, `re_control_bar.py` and `plan_builder.py`.
  - The two Start buttons use different enable rules. ExperimentsTab blocks during
    queue-lifecycle `manager_state`s; QueueManager ignores `manager_state` entirely, contrary to
    the README.
  - Other copies: `_poisson_sigma` and `_apply_deriv` ×3, `_plan_summary` ×2, and three HDF5
    exporters that write the same `scan_NNNN` layout.
  - EPICS access is split across four pyepics wrappers, plus ad-hoc `caget` calls in ExperimentsTab.
  - Two ZMQ subscribers read the same document stream: `worker._LocalDocWriter` and
    `LiveViewer.ZMQDocThread`. Meanwhile `worker.scan_point_completed` is emitted but never
    connected.
- **Reach-through into private code.**
  - `ssh_manager._get_client` is called from 5 other modules (11 call sites).
  - `PlanBuilder` mutates `PlanCatalog._types` directly.
  - `main.py` wires signals into `experiments_tab.live_viewer.*` internals.
- **Thin safety net.** There are 6 tests (1 skipped) and no CI.

### Intended outcome

- A service layer that is free of Qt and can be tested on its own.
- A small, serializable command/event API between the services and the UI.
- A Qt app that is only a thin client of that API.

The separation is enforced mechanically, with import contracts checked in CI. It is done in
small steps, so the beamline app keeps working after every step.

**Decisions**

- **Scope:** separate the layers inside one process, but make them ready to run as a daemon. The
  services run inside the GUI process. Invariant A7 (serializable boundary) keeps a separate
  service process possible later; that is Phase 5, which is optional and not scheduled.
- **First step:** record this plan only. Implementation starts with Phase 0 when the maintainers
  decide to go ahead.

## Target architecture

```
easy_bluesky/
  core/      pure logic: dataclasses + functions. No Qt, no I/O.           ("functional core")
  services/  I/O adapters + stateful services. No Qt. Publish events.     ("imperative shell")
  app/       composition root: AppContext builds services from settings, owns lifecycle,
             exposes the facade the UI uses
  ui/        PyQt6 + pyqtgraph only. Renders events, sends commands.       ("humble views")
  main.py    build AppContext → build MainWindow → app.exec()
```

Dependencies point one way only: `ui → app → services → core`.

### Boundary API

The UI and the services talk to each other only through these four channels.

- **Commands.** These are facade methods such as `ctx.run.start_queue()`, `ctx.queue.add(item)` or
  `ctx.remote.restart_manager()`.
  - They never block. Each returns a `concurrent.futures.Future[Result]`, where
    `Result(ok, msg, data)`.
  - When the UI has to make a decision, the result is typed, e.g. `CloseEnvResult.NEEDS_ABORT`.
  - Dialogs stay in the UI; the policy lives in the services.
- **Events.** These are frozen dataclasses published on a thread-safe `EventBus`:
  - RE state: `StatusChanged(ReStatus)`, `QueueChanged`, `HistoryChanged`, `RunningItemChanged`,
    `EnvOpened(from_closed)`, `EnvClosed`, `PlansChanged`, `DevicesChanged`
  - Streams: `ConsoleText`, `DocumentReceived`, `ScanPointCompleted`, `PVBatch`
  - Presence: `ClientsChanged`, `OperatorLockChanged`
  - Experiments: `ExperimentChanged`, `PlanLogChanged`, `ExperimentFolderLost`, `PlanFailed`
  - Jobs and alerts: `JobProgress`/`JobFinished`, `WatchdogTripped`, `AppLog`
- **Queries.** These are synchronous reads of cached state only (e.g. `ctx.re.last_status`). They
  never do I/O.
- **Qt bridge.** `ui/qt_bridge.py` is the only module that knows both sides.
  - It subscribes to the bus and re-emits each event through one `pyqtSignal(object)`. That signal
    is queued onto the main thread, where events are dispatched by type.
  - `bridge.when_done(future, slot)` delivers a Future's completion on the main thread.
  - It replaces the current ad-hoc `_thread_log` / `_thread_reconnect` /
    `try: emit … except RuntimeError` pattern.

### Concurrency model

The design uses threads; there is no asyncio rewrite.

- **RE Manager.** One single-thread executor owns `REManagerAPI`. It replaces:
  - `_rm_lock` and the poll thread
  - the `_PVNamesReader`, `_DeviceStatusReader` and `_SimDeviceSetter` QThreads
  - the `reset_scan_id` daemon thread

  Status polling is a scheduled job on that executor. Waiting for a `function_execute` result is a
  chain of short `task_result` jobs, never a 15 s blocking loop.
- **Streaming readers.** The ZMQ console, ZMQ document stream and SSH log tail stay on daemon
  threads, as today. They publish events.
- **SSH/SFTP, MongoDB, HDF5 export, and ESAF/AI HTTP.** These run on small `ThreadPoolExecutor`s.
  Long jobs publish `JobProgress`.
- **Timers.** `services/scheduler.py` (`call_later`, `call_every`) replaces `QTimer` in logic code.
  A `FakeScheduler` makes retries and timeouts deterministic in tests.
- **pyepics.** The CA thread calls into `PVMonitorService`, which batches updates into `PVBatch`
  events at most 10 times a second. The 100 ms flush now in `DevicesPlansTab._flush_pv_updates`
  moves there.

## Invariants: what must hold after every phase

### Architectural

| # | Invariant | How it is enforced |
|---|---|---|
| A1 | `core`, `services` and `app` never import PyQt6 or pyqtgraph, directly or transitively. | An import-linter `forbidden` contract. A pytest also imports each module in a subprocess with `sys.modules["PyQt6"] = None`. |
| A2 | `ui` never imports I/O libraries: `zmq`, `paramiko`, `epics`, `p4p`, `pymongo`, `h5py`, `bluesky_queueserver_api`, `anthropic`, `openai`, `urllib`, `subprocess`, `socket`. | An import-linter `forbidden` contract covering external packages. |
| A3 | Layers go `ui → app → services → core`. `core` depends only on the stdlib, numpy, scipy and lmfit. | An import-linter `layers` contract. |
| A4 | Widgets are touched only on the Qt main thread, and services never call UI code. | All service→UI traffic goes through `QtEventBridge`, which asserts it is on the main thread when dispatching. |
| A5 | No blocking network or disk call runs on the Qt main thread. | Follows from A2 plus futures-only commands. A test with a slow fake adapter checks that the event loop keeps turning. |
| A6 | Each external resource has one owner: one `REManagerAPI`, used only on the RE executor; one doc-stream SUB socket; one pyepics PV per name (ref-counted); one writer per settings file. | Code structure and unit tests. |
| A7 | Everything that crosses the boundary is a serializable DTO: JSON types, with numpy arrays allowed only for bulk data. | A test JSON-round-trips an example of every event and result type. This keeps the separate-process option open. |
| A8 | Each rule has exactly one implementation: status parsing, plan summary, derivative/error model, HDF5 schema, PV monitoring. | Duplicates are deleted in Phase 1, and the canonical versions are unit-tested. |

### Domain

These describe how the app behaves today. They are preserved as-is and pinned by
characterization tests before any code moves.

- **D1 — Scan numbers.**
  - `scan_num` = max(`scan_num` in `plans_log.jsonl` ∪ `queued_scans.jsonl`) + 1.
  - It is locked into `md` at queue time. Stored numbers are never renumbered.
  - Motion-only plans get no number.
  - Aborted scans consume their number. A reservation stays even if the item is later removed
    from the queue.
  - Known limit: two clients adding plans at the same instant can race. This refactor does not
    change that, but `ExperimentService` becomes the single place to add a lock later.
- **D2 — Metadata merge.**
  - User-supplied `md` wins over automatic `md`.
  - `md` is injected only when the plan signature has an `md` parameter.
- **D3 — History to plan log.**
  - Each item uid is logged once, across all experiments under `EXPERIMENTS_DIR`.
  - The item must have an `exit_status`.
  - `time_stop` must fall between this experiment's creation and the next experiment's creation.
  - Items whose `md.exp_dir` points at a different experiment are skipped.
- **D4 — Environment transitions.** This is the truth table from `ZMQWorker.poll`, pinned by a
  characterization test.
  - `env_opened(from_closed)` fires once when the environment becomes open (idle, executing_plan
    or paused) after being closed or unknown.
  - `from_closed` is true for closed → executing_task → idle, and for the first poll after
    startup. It is false otherwise, for example when closed → idle is seen without the
    intermediate executing_task.
  - A `function_execute` or `script_upload` finishing (executing_task → idle, starting from an
    open environment) is not an open. It reloads plans and devices only if this client started
    the task.
  - `env_closed` fires on open → closed.
- **D5 — Operator lock.**
  - A lock older than 4 h is stale.
  - For remote profiles, queue control and RE Manager restart/stop are blocked while connected if
    another host holds the lock.
- **D6 — Watchdog.**
  - It pauses only on a fresh failure while the RE is running or `executing_queue`. The pause is
    immediate; between plans it falls back to `queue_stop`.
  - It auto-resumes only if all of these hold: the watchdog did the pausing, the RE is still
    paused, the delay has elapsed, and all conditions still pass.
- **D7 — DESC PV.** The field suffix is stripped before `.DESC` is appended:
  `IOC:M1.RBV` → `IOC:M1.DESC`.
- **D8 — Remote function contract.**
  - Through `function_execute`, the client calls exactly four functions: `get_device_pvnames`,
    `read_devices_status`, `set_sim_device` and `reset_scan_id`.
  - Each must be a public top-level function in `easy_bluesky/scripts/re_startup_mongo.py`. A test
    checks this by parsing the file with `ast`.

### Numerical

These apply to `core/analysis`. The code is first moved there unchanged.

- **N1.** Derivatives keep length N and the original x positions. (`np.gradient` does not shift
  the data.)
- **N2.** The error of normalized counts is σ(y/n) = √(y/n² + y²/n³).
  - This is first-order error propagation with Poisson-distributed y and a Poisson monitor n,
    assumed uncorrelated.
  - It holds only when the monitor is measured in counts.
- **N3.** The derivative error formula used today is exact only when the x points are evenly
  spaced. The formula is:

  σ(ẏᵢ) = √(σᵢ₊₁² + σᵢ₋₁²) / (xᵢ₊₁ − xᵢ₋₁)

  **The exact version.** `np.gradient` computes each interior point as ẏᵢ = a·yᵢ₋₁ + b·yᵢ + c·yᵢ₊₁,
  where h_s = xᵢ − xᵢ₋₁, h_d = xᵢ₊₁ − xᵢ, and:
  - a = −h_d / (h_s (h_s + h_d))
  - b = (h_d − h_s) / (h_s h_d)
  - c = h_s / (h_d (h_s + h_d))

  For uncorrelated inputs, the exact error is:

  Var(ẏᵢ) = a²σᵢ₋₁² + b²σᵢ² + c²σᵢ₊₁²

  **Where the current formula is wrong.**
  - Interior points: the exact error reduces to the current formula only when h_s = h_d. It
    differs on scans with uneven steps, such as `adaptive_scan`.
  - Endpoints: these already match. They use one-sided differences (`edge_order=1`).
  - Second derivative: iterating the formula for d²y/dx² ignores the correlation between
    neighbouring first derivatives.

  **The fix.** This comes in a separate commit after the move, because it changes results. Write
  the operator as a matrix D and propagate Σ_out = D Σ Dᵀ, using D₂ = D·D for the second
  derivative. This is the linear case of the law of propagation of uncertainty (GUM §5). Check
  the result with a Monte Carlo test.

## Migration phases

The migration follows the strangler-fig pattern: new code grows around the old until the old can
be removed, and every phase ships a working app.

### Phase 0 — Safety net

No behavior changes in this phase.

- **Tooling.** In `pyproject.toml`:
  - Add a pytest config, with offscreen Qt set up in `conftest.py`.
  - Add `import-linter` to the `dev` extra.
  - Add `[tool.importlinter]` contracts for A1–A3. They start with `ignore_imports` listing every
    current violation. This baseline is then reduced step by step.
- **CI.** `.github/workflows/ci.yml` runs ruff, pytest (Linux, offscreen Qt) and `lint-imports`.
- **Characterization tests.** Cover:
  - invariants D1–D8, N1 and N2
  - `_DirectConsoleMonitor._extract`, `_migrate`/`_fix_port_conflicts`, `_plan_summary`,
    `_parse_motor_ranges`, `_parse_jsonl_run`
  - the JSONL → HDF5 export schema
  - both Start-button rules, recording today's disagreement

  Logic that lives inside widgets is tested through pytest-qt, using a `FakeWorker` that exposes
  the same signals.
- **Dead code.** Delete what is confirmed unused: `data_browser.py`, `styles.py`,
  `_HistoryWidgetStub`, `ZMQWorker.sim_mode` and the unconnected `ZMQWorker.scan_point_completed`.
  `esaf_dialog.py` is also unreferenced, but the README still documents it, so confirm with the
  maintainers before deleting it.

**Exit:** CI is green, and the baseline violations are recorded in the contract ignore-lists.

### Phase 1 — Functional core

This phase moves code mechanically and changes no behavior.

Create `core/` and move pure code into it. Old import paths re-export the moved names as
temporary shims, so no call site has to change.

- **`core/profiles.py`**, from `connection_settings.py`:
  - schema and defaults, `_migrate`, `profile_slug`
  - the active profile per host, `make_zmq_addrs`, `is_local_host`
  - port-conflict logic (port probing is passed in as a function)
  - delete/restore/purge

  This move alone makes `ssh_manager` and `registry` free of Qt.
- **`core/re_status.py`:**
  - `ReStatus.from_dict()`: one parser for environment state and manager state, with predicates
    such as `can_start_queue` and `can_pause`.
  - `EnvTransitionTracker`: the state machine currently inside `ZMQWorker.poll`.

  The Start-rule conflict is resolved here. Proposal: adopt ExperimentsTab's rule (block only
  during queue-lifecycle manager states), and update the README and CLAUDE.md to match.
- **`core/plans.py`:**
  - `plan_summary`, deduplicated
  - `is_motion_only` and `MOTION_PLANS`, deduplicated
  - `build_metadata` and `inject_metadata`, which are pure once their inputs are passed in
  - `parse_motor_ranges`
- **`core/scan_log.py`**, from `ExperimentsTab.update_history` and `_load_plan_log`:
  - the next scan number, computed from log lines
  - the queued-scan reservation entry
  - converting a history item into a plan-log entry
  - the rules for whether an item belongs to this experiment
- **`core/eta.py`:** `_estimate_plan_seconds`, `_format_duration` and the progress-bar
  arithmetic.
- **`core/watchdog.py`:** `WatchdogCondition`, plus a pure decision function
  `evaluate(conditions, re_state, manager_state, flags) -> Action`.
- **`core/operator_lock.py` and `core/queue_loop.py`:** the decision logic from `MainWindow`
  (`_on_lock_checked`, auto-start, loop).
- **`core/console.py`:** the console frame parser (`_DirectConsoleMonitor._extract`).
- **`core/analysis/`:**
  - `peak_fit.py`, unchanged
  - `poisson_sigma` and `derivative`, replacing the three copies
  - the centerline functions, which are already module-level in `centerline_dialog.py`
  - `plot_tools.build_2d_map`
  - the multi-scan 2D stitching duplicated in `mongo_browser` and `hdf5_viewer`
  - the χ² and RSD math from `_draw_statistics`

**Exit:** `lint-imports` enforces A1 and A3 for `core` with no ignores, and all Phase 0 tests pass
unchanged.

### Phase 2 — Service layer next to the legacy code

Build services that are free of Qt, each with unit tests that use fakes. Legacy classes become
adapters over the new services, so no tab has to change yet.

- **Infrastructure:** `services/bus.py`, `services/scheduler.py`, `services/jobs.py`.
- **`services/re_manager.py`:** `ReManagerService`, built from `worker.py`.
  - It handles connect, disconnect and polling.
  - Commands return Futures, and one generic `call_function(name, **kw)` covers
    `function_execute`.
  - `ZMQWorker` becomes a thin Qt adapter. It forwards calls to `ReManagerService` and re-emits
    bus events as its existing signals, so the tabs keep working unchanged.
- **Streams:**
  - `services/console.py`: the ZMQ console, the SSH log tail and diagnostics.
  - `services/documents.py`: a single subscriber to the document stream. The local JSONL writer
    and `ScanPointCompleted` subscribe to it.
- **`services/remote_host.py`:** `RemoteHost`, the only module that imports paramiko. It absorbs
  everything in `ssh_manager.py`, plus the SFTP/exec code scattered across the app:
  - `main.py`: `_sftp_upload_sim_script`, `_run_console_diagnostics`
  - `devices_editor.py`: `_sftp_pull`, `_sftp_push`
  - `worker.py`: `_ScanLogFetcher`
  - `connection_settings.py`: `_SFTPConnectWorker`, `_SshKeyInstaller`, `_MongoCheckWorker`
  - `plan_builder.py`: the remote plan-file threads

  `ssh_manager.py` keeps thin wrappers until Phase 4.
- **`services/local_manager.py`:** the local `start-re-manager` subprocess and
  `_get_scripts_dir`. **`services/registry.py`** moves over too.
- **`services/presence.py`:** the operator lock and client heartbeats (the 30 s poll).
- **`services/run_control.py`:** run-control policies, using the `core` policies and the
  scheduler:
  - start, pause, resume, abort and stop, including pause-then-abort retries
  - busy-retries for start and `mv`
  - the watchdog's pause fallback
  - closing the environment with an abort
  - loop restarts
- **EPICS:**
  - `services/pv_monitor.py`: the single pyepics wrapper, with ref-counted subscriptions, DESC
    handling (D7), batching, and `put`/`get`.
  - `services/image_stream.py`: p4p PVA for the AD viewer.
  - `services/watchdog.py`: runs `core/watchdog` on PV events, publishes `WatchdogTripped`, and
    calls `run_control`.
- **`services/settings_store.py`:** the only code that knows about `~/.easy_bluesky`.
  - It handles `connection.json` (written atomically: temp file + `os.replace`), UI prefs and
    theme, recent and active experiments, `plans_config.json`, watchdog files, the
    `device_metadata.json` cache, AD/XRF settings and AI memory.
  - It sets the EPICS environment variables before `PVMonitorService` is created, because libca
    must see them first.
- **`services/data/`:**
  - `MongoRunRepository`: `list_runs`, `fetch_streams`, `full_start`, with one client per
    repository.
  - `jsonl_runs.py`.
  - `hdf5_archive.py`: one writer, one reader and one schema. It replaces the three exporters and
    the parsing in `HDF5Viewer.load_file`.
- **`services/experiments.py`:** `ExperimentService` handles:
  - the active experiment per profile
  - plan-log I/O, scan-number reservations and metadata injection
  - `console.log`
  - polling the experiment folder's health (this replaces `QFileSystemWatcher`)
  - ESAF info and DOI polling
  - export jobs
  - the inputs for ETA estimates
- **Other services:**
  - `services/esaf.py`: the existing `esaf.py`, plus the health, DOI and APS-list fetchers from
    `experiments_tab`.
  - `services/ai.py`: the provider loop, tool schemas and memory. Prompt context comes from
    `ExperimentService` instead of `experiments_tab`.
  - `services/plan_catalog.py`: `PlanCatalog` is injected instead of being a global singleton.
- **`app/context.py`:** `AppContext` builds everything from settings and provides:
  - `start()`
  - `stop()`, the ordered shutdown now in `MainWindow.closeEvent`
  - `switch_profile(name)`, whose logic is now spread across `_on_profile_changed` and
    `_on_connection_settings`
- **Headless CLI:** `python -m easy_bluesky.app status|queue|console --profile NAME` proves the
  stack runs without Qt.

**Exit:** A1 is enforced for `services` and `app`; the headless CLI works against a local sim RE
Manager; the GUI is unchanged.

### Phase 3 — Move the UI onto the facade, one tab at a time

- Add `ui/qt_bridge.py`. Each view receives only the facade parts it needs through its
  constructor, instead of `worker`.
- Migrate in this order, from lowest to highest risk:
  1. REConsole
  2. REControlBar
  3. QueueManager
  4. PVWatchdogTab
  5. DevicesPlansTab, with the AD and XRF viewers
  6. LiveViewer
  7. MongoDataBrowser and HDF5Viewer
  8. PlanBuilder and DevicesEditor
  9. ExperimentsTab
  10. ConnectionDialog, RegistryAdmin and ProfilePicker
  11. AI window
  12. MainWindow, which ends up as layout, menus, tab detach and confirmation dialogs
- For each tab:
  - Delete its QThreads and I/O imports.
  - Route its business rules through `core` and the services.
  - Keep its confirmation dialogs.
  - Remove its entries from the A2 ignore-list.
- Views move under `ui/`: `ui/main_window.py`, `ui/tabs/`, `ui/dialogs/`, `ui/widgets/`. The
  `easy_bluesky.main:main` entry point stays the same.

**Exit, per tab:** the tab passes A2 with no ignores and is smoke-tested against a
`FakeAppContext`.

### Phase 4 — Enforce and clean up

- Delete the shims (old module paths and the `ssh_manager.py` wrappers) and the `ZMQWorker`
  adapter.
- Empty the ignore-lists, so CI fails on any violation.
- Update `docs/architecture.md` (layers, event catalog, thread model), the CLAUDE.md key-files
  table, and the README architecture section.
- Optionally, make PyQt6 and pyqtgraph a `gui` extra, so the services can be installed without a
  GUI.

### Phase 5 — Separate service process (optional, not scheduled)

Phases 0–4 keep this option open without committing to it.

- Add `easy_bluesky/server/`, a FastAPI app on the same stack as `esaf_server/`.
  - It exposes the facade commands over HTTP and the event bus as a WebSocket stream.
  - A7 makes this mechanical.
- The UI gets a `RemoteAppContext` with the same interface. The watchdog, operator lock and
  heartbeats then keep running when the GUI closes or crashes.

## Critical files

- **Files to split or move:**
  - `easy_bluesky/worker.py`, `main.py`, `connection_settings.py`, `experiments_tab.py`,
    `ssh_manager.py`
  - `devices_plans_tab.py`, `pv_watchdog.py`, `live_viewer.py`, `mongo_browser.py`,
    `hdf5_viewer.py`
  - `plan_builder.py`, `queue_manager.py`, `re_control_bar.py`
  - `ad_viewer.py`, `xrf_viewer.py`, `devices_editor.py`, `registry_admin.py`, `ai_assistant.py`
- **Files to reuse as-is** (already free of Qt):
  - `peak_fit.py`
  - `esaf.py` (`ESAFServerClient`, `PIGroupRegistry`)
  - `plans_manager.PlanCatalog`
  - `sim_generator.py`
  - `report_generator.py`
  - `registry.py` (fully free of Qt once Phase 1 moves `profile_slug`)

  `esaf_server/repository.py` already uses the ports-and-adapters pattern (ABC ports plus a
  backend factory). Use it as the in-repo template.
- **New files:**
  - `easy_bluesky/{core,services,app,ui}/`
  - `tests/{core,services,ui,architecture}/`
  - `.github/workflows/ci.yml`

## Verification

- **Every phase:** `ruff check`, `pytest -q` (offscreen Qt) and `lint-imports`, all run in CI.
- **Behavior preservation:** the Phase 0 characterization tests pass unchanged through Phases
  1–4. The only intended behavior change is the unified Start rule, which is documented.
- **Headless proof (Phase 2 onward):**
  - `python -c "import sys; sys.modules['PyQt6'] = None; import easy_bluesky.app.context"`
    succeeds.
  - The CLI works against a local sim RE Manager (`start-re-manager` + `devices_sim.py`). This
    needs Redis.
- **GUI end-to-end:** a manual run on a sim profile before each Phase 3 tab is merged:
  1. Connect and open the environment. The device tree fills from the sim poll.
  2. Add a `count` plan and start the queue. The live plot and ETA bars update.
  3. A plan-log entry appears with its scan number.
  4. MongoDB and HDF5 export work.
  5. A watchdog trip pauses the run, which then auto-resumes.
  6. Abort, stop, and switch profile.
  7. Close the app. The lock is released and the heartbeat file is removed.
- **Real beamline check:** before Phase 4 is merged, on a remote SSH profile:
  1. Restart the RE Manager over SSH.
  2. The RE Console log tail works.
  3. The operator-lock conflict dialog appears with two clients.
  4. EPICS monitors work on real PVs.

## Out-of-scope findings (to file separately)

- **SSH host keys are never verified.** `ssh_manager._get_client` uses
  `paramiko.AutoAddPolicy()` without loading `known_hosts`. This is a man-in-the-middle exposure.
  `RemoteHost` is the natural place to fix it.
- **AI API keys are stored in plaintext** in `connection.json`, which may be shared over NFS (per
  the comment in `get_active_profile_name`).
- **Documentation drift:**
  - CLAUDE.md references `_find_run_file_for_entry`, which does not exist.
  - The repo-root `scripts/re_startup_mongo.py` is a stale 96-line copy of the packaged 918-line
    script.

## References

**Architecture and migration**

- A. Cockburn, *Hexagonal Architecture (Ports and Adapters)*:
  <https://alistair.cockburn.us/hexagonal-architecture>
- M. Fowler, *Strangler Fig Application*:
  <https://martinfowler.com/bliki/StranglerFigApplication.html>
- M. Fowler, *Humble Object*: <https://martinfowler.com/bliki/HumbleObject.html>
- M. Fowler, *Presentation Model* (2004): <https://martinfowler.com/eaaDev/PresentationModel.html>
- G. Bernhardt, *Functional Core, Imperative Shell*:
  <https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell>
- *Characterization test* (M. Feathers, *Working Effectively with Legacy Code*):
  <https://en.wikipedia.org/wiki/Characterization_test>

**Tooling and libraries**

- import-linter contract types (`layers`, `forbidden`). To forbid third-party packages, set
  `include_external_packages = true` at the top level:
  <https://import-linter.readthedocs.io/en/stable/contract_types/forbidden/>
- Qt 6, *Threads and QObjects* (queued signals across threads):
  <https://doc.qt.io/qt-6/threads-qobject.html>
- bluesky-queueserver, which stores the queue and history in Redis. This is why the headless
  integration test needs Redis:
  <https://blueskyproject.io/bluesky-queueserver/installation.html>,
  <https://blueskyproject.io/bluesky-queueserver/features_and_config.html>
- bluesky-queueserver-api: <https://blueskyproject.io/bluesky-queueserver-api/>

**Numerics and error propagation (invariants N1–N3)**

- NumPy `gradient`, including the stencil for uneven spacing and `edge_order`:
  <https://numpy.org/doc/stable/reference/generated/numpy.gradient.html>
- B. Fornberg, "Generation of finite difference formulas on arbitrarily spaced grids",
  *Math. Comp.* 51(184), 699–706 (1988): <https://doi.org/10.1090/S0025-5718-1988-0935077-0>
- JCGM 100:2008 (GUM), §5, the law of propagation of uncertainty:
  <https://doi.org/10.59161/JCGM100-2008E>
- P. R. Bevington & D. K. Robinson, *Data Reduction and Error Analysis for the Physical
  Sciences*, 3rd ed. (McGraw-Hill, 2003). Covers Poisson statistics and error propagation (N2).
