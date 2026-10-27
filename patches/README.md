# Badger Patches

## Summary

### Patches for Badger 1.6.0 and Xopt

| Patch | Description | Required Components |
|-------|-------------|---------------------|
| `pydantic_editor-badger-1.6.0-dict-subtypes.patch` | Fixes "Dict type must have subtypes" error, handles `turbo_controller: null`, and fixes YAML parsing for 'None' strings | Badger 1.6.0 |
| `badger-1.6.0-full-gui-template-option.patch` | `badger -g -t <template>` loads a template at launch, as `-mini -t` already did (three files: CLI help, action dispatch, full-GUI launcher) | Badger 1.6.0 |
| `xopt-3.2.2-turbo-serialization.patch` | Stops the `PydanticSerializationUnexpectedValue` warning Badger logs on every iteration with a TuRBO controller: declares `_initial_state` as a private attribute and stores `best_value` as a plain float | Xopt 3.2.2 |
| `xopt-3.2.2-negative-strides.patch` | Fixes `ValueError: At least one stride in the given numpy array is negative` on the first BO step after the initial points (seen 2026-10-25 with `TuneQx_SimpleVirtualAccelerator.yaml`, TuRBO with `restrict_model_data`). When a run's data holds its variable columns in another order than the VOCS, pandas returns the selected columns as a reversed view, and `torch.tensor` rejects it. Five DataFrame-to-tensor conversions (`turbo.py` trust-region filter, `bayesian_generator.py` scaled data, `utils.py` training data) now `.copy()` first, as Xopt already does elsewhere in `utils.py`. Apply **after** `xopt-3.2.2-turbo-serialization.patch`. Test: `tests/xopt_negative_strides_test.py`. | Xopt 3.2.2 |
| `badger-mini-config.patch` | Initializes the settings singleton before template loading in `-mini` | Badger 1.6.0 |
| `badger-mini-var-table-env-configs.patch` | Rebuilds the `-mini` variable table's env configs *and* its rows from the template, so the table lists and queries the template's machine rather than the plugin defaults | Badger 1.6.0 |
| `badger-1.6.0-device-list-gui.patch` | Lists variables in environment (beam) order instead of alphabetical when a template/routine loads; replaces each "Filter…" box and "Show Checked Only" checkbox in `-g` and `-mini` with a search dropdown that opens on focus, lists every item in beam order with a check icon on selected ones, and adds an item when picked; lists always show checked rows; the "Enter new … here" placeholder rows are hidden and all four tables size to their visible rows (zero rows when nothing is checked); variable table sits in a collapsible box. Apply **after** the two `-mini` patches. | Badger 1.6.0 |
| `badger-1.6.0-revert-settings.patch` | Both GUIs (`-mini` and `-g`): snapshots every writable device's setting on each template load and at Go, adds a **Revert** button to the action bar, and asks Keep / Revert / Cancel on close when devices differ, listing them in a fixed-width table. All the GUI logic is one new mixin, `gui/components/settings_guard.py`; the pacsys work lives in `plugins/settings_snapshot.py`, the launcher in `safe_badger.py`; see `docs/safe-badger.md`. | Badger 1.6.0 |
| `badger-1.6.0-plugin-docs.patch` | Makes the "Open Docs" buttons show something. Algorithm docs: Badger looks for `documentation/docs/guides/generators/<name>.md` beside its own source, which the installed package does not ship (a FileNotFoundError, shown as the whole page); now it reads this repo's `docs/algorithms/<name>.md`, then Badger's own guide for it (setup fetches Badger's guides from GitHub, since the package does not ship them), then Xopt's docstring for the generator. Environment docs: no empty "Docstrings ... None" block when a plugin class has no docstring. One file, `badger/factory.py`. | Badger 1.6.0 |
| `badger-1.6.0-param-validation.patch` | Both GUIs: environment parameters that hold a `{name: value, ...}` mapping are edited as one line of text; each is now checked as it is typed. A bad one is marked red, with the reason as its tooltip (broken braces/commas with the position, "'X' has no value: is a ':' missing?", "expected a number, not 'abc'"; allowed value kinds come from the template's own value), and Go refuses to start, listing them. Also fixes Badger's `remove_style` leaving the widget's `error` property set. Apply **after** `badger-1.6.0-revert-settings.patch`. | Badger 1.6.0 |
| `badger-1.6.0-param-table-editor.patch` | Both GUIs: each `{name: value, ...}` parameter gets an **Edit...** button inside its field, opening a two-column table (Name, Value) with Add row / Remove row: no braces, colons or commas to type. Values are checked against the kinds the template used (bad cells marked, OK refuses); names complete from the environment's own variables, observables and `-SETPOINT` readings; OK writes the text back in table order, quoting what needs it. The field stays editable as text. Mults (`mults`) and bulk power supplies (`BulkPS_Limit`) get their own dialog: a section per mult or supply, with its step size or its limit(s) (one sum-of-|I| limit, or separate positive and negative limits) and its members picked from pulldowns of the environment's settable devices (mults also give each member a scale, and show scale x step). Mults and supplies are declared by the environment class (`mult:<name>`, `BulkPS_<group>...`), so they can be edited but not added or renamed there. Apply **after** `badger-1.6.0-param-validation.patch`. | Badger 1.6.0 |
| `badger-1.6.0-continue-run.patch` | Both GUIs: **Continue** (a checkable action-bar button, also "Continue from this run" in the History right-click menu) makes the next Go start a new run seeded with the displayed run's points, skipping initial points (armed, the button turns Go's green), so a range can be widened mid-tuning without losing what was measured. The new run has its own archive file; its description says "Seeded with N points from <run>". Its trust region (TuRBO) starts fresh on the new ranges (settings kept, shrunk length and centre dropped). Any Go first drops a "Seeded with" line copied from the shown run, so only a seeded run says it was. Variables and objectives must match the earlier run's by name. **Several runs:** with Continue armed, "Add its points" in the History menu adds a run without changing the displayed one; Go then shows a summary (each run's points, or why it is skipped: other variables or objectives, or a constraint it did not measure, which Xopt would count as violated) with two optional filters, points older than N hours and points outside the new ranges, and merges the rest oldest first. **Changed meaning:** constraint thresholds are always the new run's (only raw readings are archived), but an objective or observable can keep its name and change meaning; Go reports changed environment parameters (e.g. weights), formulas or another environment: a question for one run, a note per run in the summary. Seeded points are drawn as Badger's existing "earlier data" curve. In `-g` Continue also ticks the Data tab's "Load displayed data" + "Skip initial point sampling"; `-mini`, which had no data loading, gets the same seeding. Shared logic in a new `gui/components/continue_run.py`; test: `tests/continue_run_gui_test.py`. Apply **after** `badger-1.6.0-revert-settings.patch` and the `-mini` patches. | Badger 1.6.0 |
| `badger-1.6.0-turbo-state-reset.patch` | Both GUIs: a new run no longer inherits the trust-region (TuRBO) centre of the run shown before Go. Badger's `_compose_routine` blanks `center_x`/`best_value` only when the controller is named `optimize`/`safety`, but a controller loaded from a run is named `OptimizeTurboController`/`SafetyTurboController`, so the stale centre stayed; with a small region, every new point could fall outside it and the first BO step failed with `FeasibilityError: no points in the dataset are within the TuRBO trust region` (seen 2026-10-25, `TuneQx_SimpleVirtualAccelerator.yaml`). Now both names match. Apply **last** of the Badger patches. Test: `tests/continue_run_gui_test.py` (fails without it). | Badger 1.6.0 |
| `badger-1.6.0-spinbox-wheel-guard.patch` | Stops the mouse wheel from changing numeric field values in the Environment/Algorithm Parameters editor and the range-limit dialogs — a frequent source of accidental edits. Reuses Badger's own existing `MouseWheelWidgetAdjustmentGuard` (already used for the variable table's spin boxes) everywhere else it was missing. | Badger 1.6.0 |

### Patches for the `simpler_mini` branch (UI design changes, not bug fixes)

| Patch | Description | Required Components |
|-------|-------------|---------------------|
| `badger-1.6.0-mini-simpler-ui.patch` | `-mini` operator-facing redesign, all five changes under "Design Changes" below in one patch (`gui/mini/components/env_cbox.py`, `gui/mini/pages/routine_page.py`): "Template" → "Tuning Task" box that also holds a Parameters row (Machine Interface / Optimization Algo) in place of the Environment and Algorithm rows; VOCS labels lead their action rows and tables span full width; no collapse bars on Variables or Constraints/Observables, Initial Points locked open; "Environment + VOCS" tab → "Tuning", with its right margin set from the real scrollbar width. Apply **after** the `-mini` and device-list patches: diffed against that tree. | Badger 1.6.0 |
| `badger-1.6.0-full-gui-vocs-layout.patch` | Full GUI (`-g`): the same VOCS layout as `-mini` (change 2 and 3 below, and 6): each section name, bold and larger, leads its picker row; no left label column; no Variables collapse bar or "More" bar; Initial Points locked open. Its tabs, sidebar and Automatic mode are unchanged. Apply **after** `badger-1.6.0-device-list-gui.patch`. | Badger 1.6.0 |

## Issues Fixed

1. **"Dict type must have subtypes"** - Occurs when loading templates with dict/list environment params (e.g., `setpoints: {qx: 9.049, qy: 9.035}`)
2. **`turbo_controller: null` handling** - Prevents warnings and ensures correct null serialization
3. **YAML 'None' strings** - Fixes parsing of 'None' strings in flow maps (inline `{}` or `[]` syntax)
4. **VOCs field not found** - Fixes error when VOCs data is stored separately from generator parameters
5. **PydanticSerializationUnexpectedValue warnings** - Every iteration, Badger serializes the whole Xopt object (`Xopt.json()`), and two things in `xopt/generators/bayesian/turbo.py` trip pydantic: `TurboController.__init__` assigns `self._initial_state` without declaring it, so pydantic stores it on the instance and the serializer sees an unexpected field (safety controller); and `OptimizeTurboController.update_state` stores `best_value` as the `numpy.float64` pandas returns, which the Xopt-level serializer rejects (optimize controller). Fixed at the root by `xopt-3.2.2-turbo-serialization.patch` (three lines) rather than by filtering the warning. Verified offline on pristine xopt 3.2.2: 1 warning per `json()` before, 0 after, for both selectable controllers (optimize and safety).
6. **`-mini` variable table lists and queries the wrong machine** - Two caches hold the plugin's `configs.yaml` defaults and are never refreshed when a template points the environment elsewhere: `BadgerVariableTable.configs` (captured in `select_env()`, and the environment is rebuilt from it on every refresh) and `routine_page.vars_env`, the table's *rows*, which come from `configs["variables"]` — computed once by `factory.load_plugin` from an environment built with those same defaults. Loading a template on another lattice therefore reloads the *default* lattice repeatedly, errors on variables only the template's lattice has (e.g. `Cannot read 'iq2'`), and lists thousands of rows belonging to the wrong machine. Fixed by `badger-mini-var-table-env-configs.patch`, which re-runs `add_var()` and rebuilds `vars_env` from an environment carrying the template's params. Measured on `Xfer400MeV_example.yaml`: 2284 default-lattice rows → 124 rows of its own.

7. **Alphabetical device lists / checked and unchecked rows mixed together** - Both routine pages sort the variable dict (`dict(sorted(...))`) when loading a template or routine, so the plugin's beam-order listing is lost (environment selection alone preserved it). The four lists also showed every device with a free-text filter. Fixed by `badger-1.6.0-device-list-gui.patch`: drops the sort (dicts keep insertion order: env variables, then `additional_variables`, hard-limit overrides change values only), adds `gui/components/picker.py` (an editable `QComboBox` + contains-match `QCompleter` rebuilt from the table on focus/open, no signal wiring) in place of each filter box, and wraps the variable table in the existing `CollapsibleBox`. Also wires the `-mini` observables "Show Checked Only" checkbox, which upstream never connected.
8. **`AttributeError: 'Picker' object has no attribute 'setText'`** - Stopping/resetting a routine (`refresh_ui` in both routine pages) clears `edit_obj`/`edit_con`/`edit_sta` via `setText("")`, the way it cleared the `QLineEdit` filter boxes `Picker` replaced. Fixed by adding a `setText()` compatibility shim directly to `Picker` (clears the combo via `setCurrentIndex(-1)`) in `badger-1.6.0-device-list-gui.patch`, one guard covering all four call sites in both GUI variants instead of patching each caller.
9. **Mouse wheel changes numeric field values** - Hovering over a `QSpinBox`/`QDoubleSpinBox` and scrolling changes its value even without focus or a click — Qt's default behavior, and an easy way to silently mis-set an Environment/Algorithm parameter or a range-limit ratio/delta. Badger already has `RobustSpinBox` (`gui/components/robust_spinbox.py`) with wheel protection built in (`MouseWheelWidgetAdjustmentGuard`, `gui/utils.py`), but only wires it into the variable table; the parameter editor (`pydantic_editor.py`'s `resolve_qt`, one guard covering every int/float field it creates) and four dialogs that build plain `QSpinBox`/`QDoubleSpinBox` directly (`lim_vrange_dialog.py`, `ind_lim_vrange_dialog.py`, `terminition_condition_dialog.py`, `add_random_dialog.py`) never got it. Fixed by `badger-1.6.0-spinbox-wheel-guard.patch`: installs the same existing guard at all 10 previously-unprotected construction sites, reusing Badger's own mechanism rather than inventing a new one.

## Design Changes (`simpler_mini` branch)

Changes 1–5 were developed as separate patches and then merged into one, `badger-1.6.0-mini-simpler-ui.patch` (verified byte-identical to the old five-patch chain's output). Patch names in the entries below refer to that history.

1. **Collapse the Environment/Algorithm rows into one Parameters row** - The full "Badger Environment: [combo] [Parameters] [Open Docs]" and "Algorithm [combo] [Parameters] [Open Docs]" rows are full-GUI/developer-oriented: a `-mini` operator picks a template, which sets both, and has no reason to see "Badger Environment" framed as a thing to choose. `badger-1.6.0-mini-parameters-row.patch` replaces both rows with one "Parameters" row holding two buttons, "Machine Interface" and "Optimization Algo", each still expanding the same parameter editor as before (now with its "Open Docs" button moved inside, above the editor, since the row itself no longer has room for it). `env_cb`/`algo_cb` are still constructed and still drive selection via their existing signals (`currentIndexChanged` → `select_env`/`select_generator` in `routine_page.py`) — they're just not added to any visible layout, so a template still sets them the same way it always did. Gotcha hit twice while building this: a widget never added to a layout is garbage-collected unless explicitly parented (`QWidget(self)`, not `QWidget()`); and even once parented, it still renders at a stray default position unless also explicitly `.hide()`'d — "not in a layout" alone doesn't mean "invisible". Where the "Open Docs" buttons best belong, and the documentation content itself (currently close to empty), are open questions, not resolved by this patch.
2. **Full-width VOCS tables, no sidebar** - Each of the four device-list sections (Variables, Objectives, Constraints, Observables) put its label in a fixed-width (`LABEL_WIDTH = 96`) column to the left of its table, with a `addStretch(1)` pinning the label to the top of a column whose height matched the table's — producing a tall, visually empty strip under each label. `badger-1.6.0-mini-vocs-full-width.patch` replaces that side-by-side `QHBoxLayout` with a `QVBoxLayout` per section so the table spans the full width. First pass put the label on its own heading line above the action row (Picker + Refresh/checkbox) — a quick follow-up moved the label to lead that same row instead (label, then the "Add …" Picker, then Refresh for Variables), so the row doesn't cost an extra line of vertical space either. Labels got their own `VOCS_LABEL_WIDTH = LABEL_WIDTH + 14` (bold "Observables" clips at the plain `LABEL_WIDTH`) for consistent alignment across the four rows. Nothing about the tables, Pickers, or `CollapsibleBox`es changed — only where the label sits. Verified visually with offscreen screenshots (`QT_QPA_PLATFORM=offscreen`, `page.grab()`) at the page's natural content size — a first attempt at an artificially taller window showed an apparent gap between a label and its content, which turned out to be a test-harness artifact (forcing a bare widget taller than its content outside any scroll area), not a real layout bug.
3. **Stop collapsing Variables / Constraints + Observables** - The variable table sat inside its own `CollapsibleBox(" Variables")`, redundant with the row above it (which already says "Variables") and able to hide the whole table; Constraints and Observables shared one `CollapsibleBox(" Constraints + Observables")`, able to hide both sections with one click. `badger-1.6.0-mini-always-expanded.patch` removes both wrappers — the table/sections are now plain children of the layout, always visible, no toggle at all. "Initial Points" keeps its own `CollapsibleBox` (a secondary, less-often-needed table, worth the visual separation) but is locked open: `.expand()` once, then `toggle_button.clicked.disconnect(...)` and `setCheckable(False)` so the bar still renders but clicking it is a no-op. Verified by programmatically clicking the toggle button in a loaded page and confirming the content area's height is identical before and after.
4. **Parameters row moves into the Tuning Task box** - The "Template" label/row is renamed "Tuning Task", and the Parameters row (added in change 1 above) moves from its own separate row into that same styled `TemplateSelectorRow` box, as a second line under the task-selection line — the template already picked both the machine and the algorithm, so this reads as "more about the same task" rather than a new section. `TemplateSelectorRow`'s single `QHBoxLayout` became an outer `QVBoxLayout` wrapping that original row, plus a new `add_row()` method any later row can call. The Parameters row's label and both buttons got the frame's existing `TemplateSelectorLabel`/`TemplateSelectorButton` object names so they pick up its dark-background-appropriate styling for free, rather than needing new CSS. Known minor gap, not addressed here: a checked ("expanded") button doesn't look visually distinct from an unchecked one against that background.
5. **Rename the Tuning tab, fix its scrollbar clipping** - User reported the Tuning Task box's right edge (the rounded border, "From file", and "Optimization Algo") getting cut off by the tab's vertical scrollbar. Traced to `scroll_layout_env.setContentsMargins(0, 0, 5, 0)` in `routine_page.py` — a hardcoded 5px right margin with the comment "add extra right margin for macOS to prevent scrollbar overlap", already a guess that had drifted wrong. Fixed at the root: query the actual scrollbar width (`QApplication.style().pixelMetric(QStyle.PM_ScrollBarExtent)`) instead of hardcoding one. Also renamed the "Environment + VOCS" tab to "Tuning" — too technical for the target user, same reasoning as "Badger Environment" → "Machine Interface" earlier. Verified by forcing the vertical scrollbar to appear (a short window height) and screenshotting before/after.

6. **Full GUI gets the VOCS layout** - `badger-1.6.0-full-gui-vocs-layout.patch` brings changes 2 and 3 to the full GUI's `gui/components/env_cbox.py`, nothing more (decided 2026-10-23: its Metadata/Algorithm/Data tabs, History/Templates sidebar, Load Template bar and Automatic mode stay). The Variables section's picker row now comes first, led by the label; the Automatic/Refresh row follows it, indented under the picker. The "More" box holding Constraints and Observables is a plain panel.
7. **Save as... in `-mini`** - Upstream removed the `-mini` "Save as Template" button but kept `save_template_yaml`. Now part of `badger-1.6.0-mini-simpler-ui.patch`: a "Save as..." button beside "From file" in the Tuning Task box. The file dialog opens in `<template dir>/saved/` (`tuning_templates/saved/`, gitignored) with the name `<current template>_<YYYYmmdd_HHMM>.yaml`; saving anywhere else inside the template directory, i.e. over an operations template, is refused with a message. The Tuning Task dropdown lists saved templates as `saved/<name>`, and loading resolves such names against the template directory. The dropdown now shows a template's path relative to the template directory (`development/ZZ_PacsysTesting`, `saved/...`), not only its file name. `tests/save_template_gui_test.py` covers all of this; `tests/template_lint_test.py` skips `saved/`.

8. **Name each parameter panel** - With both Parameters panels open it was hard to tell which was which. Each panel's docs row now starts with a bold heading, "Machine Interface Parameters" or "Optimization Algo Parameters", followed by the selected environment or algorithm name (otherwise hidden in `-mini`, since the template picks them). The heading never widens the panel: it takes the spare width and clips, with the full text in its tooltip. Part of `badger-1.6.0-mini-simpler-ui.patch`.

## Applying the Patches

> **Never edit files under `site-packages` in place.** conda hard-links them to its
> package cache (`~/miniconda3/pkgs/`) and to every other env that installed the same
> build, so an in-place write (`open(path, 'w')`, an edit script, GNU `sed -i`) lands in
> all of them at once and makes conda report `SafetyError` on the next env build.
> Applying a `.patch` with `patch` is safe: it writes a new file. If `SafetyError`
> appears, delete the extracted `pkgs/<pkg>/` directory (keep the `.conda` archive)
> and rebuild the env.
>
> **From-scratch check** (do this before committing a new patch): `rsync` the working
> tree to `/tmp/X` excluding `.git` and `.pixi`, then `cd /tmp/X && ./bootstrap.sh --yes`
> (defaults to the FNAL-network-requiring onsite environment; add `--offsite`
> off that network). Legacy conda path:
> `./setup.sh --yes --env-name X` (drop the `acsys` lines from the copy's
> `environment.yml` first if off-site). Expect `applied` for every patch and a
> `badger/` + `xopt/` tree identical to the working env.
>
> Both setup scripts also sync their resolved paths into Badger's own
> per-user settings file (outside this repo, not per-clone — see
> "Syncing Badger's per-user config" in `setup.sh`/`pixi_setup.sh`), so a
> from-scratch check against `/tmp/X` temporarily points it at `/tmp/X`
> too. Harmless, but re-run setup against your real clone afterward before
> trusting a live "Go" there.

### Finding Badger Installation

First, locate your Badger installation in your pixi environment:

```bash
pixi run python -c "import badger; import os; print(os.path.dirname(badger.__file__))"
```

Legacy conda path: `conda run -n FermiBadger_env python -c "import badger; import os; print(os.path.dirname(badger.__file__))"` (replace `FermiBadger_env` with your environment name).

**`./bootstrap.sh` (or `./setup.sh` for the legacy conda path) applies all of
these for you** — the manual steps below are the fallback.

### Using `patch` Command

This patch carries `a/pydantic_editor.py` paths, so apply it from the
`gui/components` directory with `-p1`:

```bash
BADGER_PATH=$(pixi run python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
cd "$BADGER_PATH/gui/components"
patch -p1 < /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

### Using `git apply`

```bash
BADGER_PATH=$(pixi run python -c "import badger; import os; print(os.path.dirname(badger.__file__))")
cd "$BADGER_PATH/gui/components"
git apply /path/to/FermiBadgerPlugins/patches/pydantic_editor-badger-1.6.0-dict-subtypes.patch
```

### The `-mini` Patches

All of these patches carry `a/badger/...` paths, so apply them from the
`site-packages` directory with `-p1`:

```bash
SITE_PACKAGES=$(pixi run python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
cd "$SITE_PACKAGES"
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-mini-config.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-mini-var-table-env-configs.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-device-list-gui.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-full-gui-template-option.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-spinbox-wheel-guard.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-mini-simpler-ui.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-full-gui-vocs-layout.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-revert-settings.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-plugin-docs.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-param-validation.patch
patch -p1 < /path/to/FermiBadgerPlugins/patches/badger-1.6.0-param-table-editor.patch
```

## Applying the Xopt Patch

`xopt-3.2.2-turbo-serialization.patch` carries `a/xopt/...` paths and applies from
`site-packages` with `-p1`, like the `-mini` patches; `bootstrap.sh`/`setup.sh` applies it last.
It touches only `xopt/generators/bayesian/turbo.py`.

```bash
SITE_PACKAGES=$(pixi run python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
cd "$SITE_PACKAGES"
patch -p1 < /path/to/FermiBadgerPlugins/patches/xopt-3.2.2-turbo-serialization.patch
```

The same three lines are worth offering upstream to xopt-org/Xopt.


## Patch History

### Superseded Badger Patches

The following patches have been superseded by `pydantic_editor-badger-1.6.0-dict-subtypes.patch`:

- `pydantic_editor-badger-1.6.0-fixes.patch`
- `pydantic_editor-turbo_controller-null-1.6.0.patch`
- `pydantic_editor-combo-box-null-fix.patch`
- `pydantic_editor-null-turbo_controller-git-apply.patch`
- `pydantic_editor-null-turbo_controller.patch`
- `pydantic_editor-turbo_controller-string-PR.patch`
- `pydantic_editor-turbo_controller-string-fix.patch`
- `badger-1.6.0-none-parsing-fix.patch` (deleted 2026-10-07; its `pydantic_editor.py` change is in the dict-subtypes patch and its `gui/utils.py` change is not needed — a pristine 1.6.0 plus the four live patches is byte-identical to the working install)

### Deleted plugin patch

- `simple-virtual-accelerator-plugin-fix.patch` (deleted 2026-10-07): targeted `plugins/environments/SimpleVirtualAccelerator/`, which was renamed `99_Sim_SimpleVirtualAccelerator` with the fix already committed in the plugin itself.

### Retired Xopt patch

- `xopt-pydantic-serialization-fix.patch` and `apply_xopt_fix.py` (deleted 2026-10-08): generated against hand-edited xopt 3.2.1 files that the 2026-09-16 env rebuild replaced with pristine conda-forge xopt 3.2.2, so they could never apply to a fresh install. Replaced by `xopt-3.2.2-turbo-serialization.patch`, which fixes the cause instead of filtering the warning.

## Environment

Patches tested with:
- Badger 1.6.0
- Python 3.12
- Pydantic 2.x
