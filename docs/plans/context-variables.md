# Plan: a "Context" column in Badger's variable tables

User's request (2026-11-20): a checkable column in the variables table; a checked variable
is exogenous: modeled, never moved (Xopt's `ContextualVariable`), header "Context".
Wanted whether or not the RIL source study finds the ion-source settings helpful.

## How Xopt treats a contextual variable (3.2.2)

`ContextualVariable(domain=[lo, hi])` (`gest_api/vocs.py:44-54`, a `ContinuousVariable`).
The GP takes it as an input; `generate()` leaves it out of the candidates and holds the
acquisition at its last measured value (`bayesian_generator.py:1034-1037`), so the last
data row must carry it (not NaN). Give it a finite domain: an infinite one saves as
`null` and does not reload. The evaluator concatenates inputs and outputs, and a
duplicate column with a different value raises, so a context value must come back as an
output, never be sent as an input.

## Design: a flag in the table, wrapped at compose time

- **Tables** (full `badger/gui/components/var_table.py`, mini
  `badger/gui/mini/components/var_table.py`): a "Context" checkbox column with a
  tooltip ("Context: never moved; its value is read at every step and modeled as an
  input"), state kept in a name->bool dict like `selected` (rows are rebuilt on every
  `update_variables`). A context row keeps its range: that is its domain (default: the
  environment's hard limits).
- **Compose** (`env_cbox.compose_vocs`, both GUIs): checked rows become
  `ContextualVariable(domain=[lo, hi])`. Range code (`calc_auto_bounds`, `set_vrange`,
  ...) keeps working on plain bounds, untouched.
- **Templates**: load (both `routine_page`s) sets the flag for `type: ContextualVariable`
  entries; the mini GUI's `_round_bounds_inward` (`badger/utils.py`) keeps the type.
  Save already writes `{type, domain}` (`model_dump`).
- **Run loop**, the one place that writes: the evaluator (`badger/routine.py:141-152`)
  drops context names from the point before `env.set_variables`, then reads them with
  `env.get_variables(context_names)` and returns them with the observables.
- **Every other writer skips context variables**: initial points (`fill_curr`,
  `add_rand`, `calculate_initial_points`, both GUIs: add_rand currently raises KeyError
  on them), `calculate_variable_bounds`/`routine_runner` (keep the type),
  `run_monitor` reset / checkpoint / apply-solution writes, `continue_run`.
- **Generators**: only Bayesian ones support context (`supports_contextual_variables`);
  others raise `VOCSError`, shown as a clear message in the GUI.

One patch, `patches/badger-1.6.0-context-variables.patch`, appended last in
`pixi_setup.sh`; Xopt unchanged.

## Tests

- `tests/context_variables_test.py`, offline (FakeBackend): a routine with one context
  variable runs a few steps through Badger's run path; the context device is never
  written; every data row carries its measured value; the generator saw a
  `ContextualVariable`; initial points (current, random) work.
- `tests/context_variables_gui_test.py`, both GUIs offscreen: the column exists; checking
  it composes a `ContextualVariable` with the row's range; a template round-trips
  (save, reload: still checked, same domain); a past run reopens with it.
- Full suite before push.

## Open

- A context variable read outside its domain (user, 2026-11-24: the range must expand):
  the domain widens to take in the reading, just to it, with no margin (`widened()` in
  `badger/utils.py`): at each run step (the evaluator; logged at INFO), at Go
  (`calculate_variable_bounds`), and at template load with ranges relative to current
  (both GUIs). It is never recentered on the reading. No warning: the outside-limits
  check exempts context rows. Not covered: the run archive is written by the GUI, whose
  copy of the VOCS may keep the starting range (unchecked); a later Continue widens again
  at Go and at its first step.
- Writes: the run loop, Reset, checkpoints, and jump-to-optimum all drop context
  variables before `set_variables`; an environment may still refuse them (the RIL
  environment's `.READING` variables), which only fires when one is ticked without
  Context.
- Which environments get context candidates as variables (e.g. the RIL source settings)
  waits for the RIL source study.
