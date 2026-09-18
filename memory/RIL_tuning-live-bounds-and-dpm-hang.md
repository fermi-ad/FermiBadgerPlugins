---
name: RIL_tuning-live-bounds-and-dpm-hang
---

# RIL_tuning physical templates: pydantic load errors, stale bounds, and a DPM hang

Full writeup: `docs/progress.md`, dated 2026-09-16. Three distinct, layered
bugs hit loading `RIL_tuning_trims_and_sol_LEBT_MEBTquads.yaml` (and likely
its still-unfixed siblings `RIL_tuning_trims_and_sol.yaml` / `templates.yaml`,
which carry the same stale patterns).

## 1. `turbo_controller: safety` (bare string)

Pre-1.4 Badger/Xopt templates stored `turbo_controller` as a bare name
string. Current `pydantic_editor.py` expects `null` or a full nested object;
a bare string crashes `initialize_special_field()` with
`TypeError: 'str' object does not support item assignment` (it does
`special_item_dict["vocs"] = ...` assuming a dict). **Fix: `turbo_controller: null`**
— the same convention already used by every current sim template
(`DR_BetatronTunes_sim.yaml`, `Xfer400MeV_example.yaml`, etc.) and specifically
hardened for in the Badger 1.6.0 upgrade ("Fix 1" in `docs/badger-upgrade-1.6.0.md`).
Do not hand-author a `SafetyTurboController`/`OptimizeTurboController` object
from scratch — the only full examples in this repo's templates are captured
mid-optimization run state (`center_x`, `failure_counter`, etc.), not a clean
starting config.

## 2. Stale static `vocs.variables` bounds vs. live hardware

`-mini` always force-auto-fills the init table on load
(`routine_page.update_init_table(force=True)` → `add_rand_in_init_table()`),
sampling a region around each variable's *live* current value
(`env.get_variables()`) and clipping to the template's declared
`vocs.variables` bounds via `np.clip`. If the live value is far enough
outside those bounds, both clip ends land on the same boundary → zero-width
range → `xopt.vocs.validate_variable_bounds` raises
`Bounds ... do not satisfy value[1] > value[0]`, surfaced as
`badger.errors.VariableRangeError`.

This is a live-hardware-state question, not a code bug — don't guess-widen
bounds. Use `check_RIL_tuning_live_bounds.py` (tests/; **read-only**, only
calls `get_variables`/`get_settings`, never touches `set_variables`/`set_values`)
to dump every template variable's live reading next to its declared bounds in
one shot. Decide per-variable with the user whether to widen the template
(and to what — check whether a sibling variable already has the right-shaped
range, e.g. `L:ATRMVU`'s `[-4, 1]` vs. the broken one-sided `[0, upper]` on
`L:ATRMHD`/`L:ATRMHU`/`L:ATRMVD`) or whether the hardware needs to move back
in range first. Also sanity-check against the environment class's own hard
limits (`plugins/environments/RIL_tuning/__init__.py`'s `variables` dict,
`[-4.0, 4.0]` for the ATRM trims) — the template's sub-range must stay inside
those.

Longer-term fix available: `relative_to_current: true` (the "Automatic"
checkbox / `AUTO_REFRESH` config) makes Badger recompute `vocs.variables` from
live values against the *environment's* hard bounds every load, so it can't go
stale the way hand-typed numbers did here. Not yet turned on for these
templates — see open item below.

## 3. `-g` GUI hangs forever with "Automatic" checked (fixed)

Root cause: `plugins/scanner.py`'s `read_once()` called `await dpm.start()`
once per device *inside* its registration loop, instead of once after all
entries are added (contrast `set_once()` in the same file, which does it
correctly). A single one-shot read tolerates this, but "Automatic" mode does
two live reads back-to-back on fresh `Connection`s
(`calc_auto_bounds()` then, via `try_populate_init_table()` →
`update_init_table()`, `add_rand_in_init_table()` again) and that's what
exposed it. Fix: move `dpm.start()` outside the loop. Also added
`asyncio.wait_for(timeout=15.0)` around the reply-wait as a permanent safety
net — this whole path (`acsys.run_client()` → `loop.run_until_complete()`)
runs synchronously on the calling thread with no other timeout anywhere, so a
future stuck DPM session would otherwise freeze the Qt GUI thread forever
with no diagnostic trace, same as this one did.

## Open

- `RIL_tuning_trims_and_sol.yaml` and `templates.yaml` have the same stale
  `turbo_controller` string and old singular `sample_event`/`setpoint` params
  (the latter harmless — silently dropped by pydantic's `extra='ignore'` — but
  worth cleaning). Not yet swept.
- `relative_to_current: true` not yet enabled on the fixed template.

## Environment note for future agentic sessions

Reaching this repo's actual conda env (`FermiBadger_env`) or a live Terminal
was not straightforward: the sandboxed file-access shell is a separate Linux
VM that cannot execute the macOS conda binaries at all (`Exec format error`),
and computer-use access to Terminal is click-only by platform policy (no
typing/keystrokes). All debugging here was done by static-reading
`badger`/`xopt`/`acsys` site-packages source plus the user's own pasted
tracebacks, with the user running each retest.
