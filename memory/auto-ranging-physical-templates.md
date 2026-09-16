---
title: Auto-ranging rollout for physical-machine templates
---

# Auto-ranging rollout for physical-machine templates

Context: [RIL_tuning-live-bounds-and-dpm-hang](RIL_tuning-live-bounds-and-dpm-hang.md)
fixed one template's load errors and the `-g` "Automatic" hang. This is the
follow-up: turning `relative_to_current: true` on across *all* physical
(`BasicAcsysInterface`) templates, plus the edge-case audit that motivated it.

## The zero-current edge case (confirmed real)

`calc_auto_bounds()` / `set_ind_vrange()` in both
`badger/gui/mini/pages/routine_page.py` and `badger/gui/components/routine_page.py`
support 3 `limit_option_idx` modes per variable:

- **0 — "ratio with current value"** (multiplicative):
  `bounds = curr * (1 ± 0.5*sign(curr)*ratio_curr)`. **Bug**: when
  `curr == 0.0`, `np.sign(0.0) == 0.0`, so both bounds become `0.0` —
  collapses to a zero-width range regardless of `ratio_curr`.
- **1 — "ratio with full range"** (additive):
  `delta = 0.5*ratio_full*(hard_hi-hard_lo)`; `bounds = [curr-delta, curr+delta]`,
  clipped to hard limits. Immune — doesn't depend on `curr`'s sign/magnitude.
- **2 — "delta around current value"** (additive, absolute units):
  `bounds = [curr-delta, curr+delta]` where `delta` is a raw absolute value
  in the variable's own units — this is the "recommended half-width in
  absolute units" mechanism; already exists, no code changes needed. Also
  immune to the zero-current bug.

**Danger**: any variable missing from a template's `vrange_limit_options`
dict falls back to `self.limit_option` — whose hardcoded default is
`{"limit_option_idx": 0, ...}` — i.e. the unsafe mode, silently.

Per-variable config lives at the template's top level:
```yaml
vrange_limit_options:
  <var_name>:
    limit_option_idx: 1      # or 0, 2
    ratio_curr: <float>       # used only if idx==0
    ratio_full: <float>       # used only if idx==1
    delta: <float>            # used only if idx==2, absolute units
```

## Rollout (2026-09-16)

Audited all 9 templates whose `environment.name` is `BasicAcsysInterface`-backed
(`RIL_tuning`, `LinacQuadTuning`). All now have `relative_to_current: true`
and clean `vrange_limit_options` (every variable present, none on idx 0):

- `RIL_tuning_trims_and_sol.yaml`, `templates.yaml` — fixed bare-string
  `turbo_controller`, widened stale one-sided ATRM bounds (same bug/fix as
  the original `_LEBT_MEBTquads` template).
- `..._D34andTUNRAD_mobo.yaml`, `..._D34opt.yaml` — same ATRM bounds fix.
- `RIL_tuning_trims_and_sol_LEBT_MEBTquads.yaml`, `BooEFF_D7LMSM_mobo.yaml`,
  `LinacOutputTrajectory.yaml` — already clean, just flipped the switch.
- `LinacQuads.yaml` — all 18 variables were on unsafe idx 0
  (`ratio_curr: 0.25`); switched to idx 1, `ratio_full: 0.25` (same numeric
  window-size intent, now sign/zero-safe).
- `D13LM_reduce_wV5QSET.yaml` — separate, unrelated bug: legacy
  `!!python/tuple` YAML tags in `vocs.variables`/`vocs.constraints` (an old
  `badger_version: 1.4.4` dump). Badger's loader uses plain `yaml.safe_load`,
  which can't construct that tag — **this template could not load in current
  Badger at all**, independent of everything else here. Converted to plain
  lists. Its `vrange_limit_options` was also completely empty (`{}}`) despite
  3 declared variables — populated with idx 1, `ratio_full: 0.1` (Badger's
  own default magnitude — no prior per-variable ratio existed to preserve).

## Second bug found during re-test: empty-device-list DPM hang

After this rollout, live-testing `LinacQuads.yaml` hit a *different* hang:
`select_env()` calls `set_vrange()` when "Automatic" is already checked (true
because of `relative_to_current: true`), and `set_vrange()`'s trailing
`update_init_table()` call has no guard for "zero variables selected" (unlike
`toggle_relative_to_curr()`, which does check
`self.env_box.var_table.selected`). Right after an environment is
(re)selected, no variables are checked into the routine yet, so this fires
`env.get_variables([])` — an empty `drf_list`. `read_once()`/`set_once()`
didn't handle that: opened a DPM session with zero entries and hung waiting
for replies to a request that asked for nothing. Fixed in `plugins/scanner.py`:
both now return immediately (`[]`/`None`) on an empty `drf_list`, no DPM
session opened. This is generic to any `BasicAcsysInterface` environment
(not LinacQuadTuning-specific) — just happened to surface here first.

## Status: confirmed working, committed

User live-tested after the empty-device-list fix above: all 9 templates
load and run "Automatic" cleanly in the full GUI ("every template loads and
does AutoMode just fine"). Committed as `7e80442`, together with the user's
own widened RIL_tuning hard limit for `L:RFBPAH` (`[210, 230]` → `[100,
300]` — needed for auto-ranging to work out of the box there).

## Open

- `L_AutoSteerRestore`, `LinacEnergyStabilization`, `MinD7LMSM_using_Tank5Phase`,
  `Muon_DR_PID_tune` environments have no template files yet — nothing to
  auto-range there yet, but the same missing-entry-defaults-to-idx-0 trap
  will apply whenever templates are added for them.

## Environment note for future agentic sessions

Same constraint as before: this sandbox's Linux shell (via the device
bridge) can read/write/grep files in the user's `FermiBadgerPlugins` and
Badger `site-packages` trees, but cannot *execute* anything in
`FermiBadger_env` — it's a macOS conda env with Mach-O binaries, not
runnable from a Linux VM. `conda activate FermiBadger_env && python3 ...`
fails immediately (`No such file or directory` on the macOS conda binary).
Structural/YAML validation is possible; pydantic/xopt/live-hardware
validation is not — that always needs the user to run it.
