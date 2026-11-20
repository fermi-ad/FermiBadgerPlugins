# The Booster environment, 03_Booster_Pacsys

2026-11-19. One environment for every Booster tuning task; a template picks its devices.
Replaces the injection-only draft `03_Booster_InjectionTuning_Pacsys` (deleted; its
template, `development/03_Booster_InjectionTuning_Pacsys.yaml`, now uses this one).
DRAFT: devices and ranges are unconfirmed until the hardware owners sign off.

## Where the devices come from

`plugins/environments/03_Booster_Pacsys/devices.csv` (the environment reads it), built by
`scripts/make_booster_devices.py` from three sources, read only:

- **Device inventory**: fermi-ad/ad-tools (internal), its Booster, injection-line, and
  facility catalogs and its device-database export, read offline. Only the fields the
  environment needs are copied here (no alarm limits, no full export).
- **Logbook**: 24 months of Booster entries (1300 tuning entries, 869 naming a device),
  classified into 12 task types; which devices operators adjust and which they watch
  (columns `logbook_knob`, `logbook_watched`). Injection (505 entries) and orbit (473)
  lead; the most-tuned knobs are `L:C7PHAS`, `B:VIMIN`, `L:V5QSET`, and the injection
  bends; the most-watched readings are BLMs (`B:BLM026`, `B:BLMS06`, `B:BLMS13`, ...).
- **Data logger**: 90 days of `.SETTING` history to 2026-11-19 (`scripts/logger_ranges.py`)
  for the 110 candidate settings the logger keeps. The ring correctors, quads, and
  sextupoles (288 settings) are not logged, nor are their readings.

## What is in it

- Variables: 440 scalar settings in tuning families (injection line, Linac boundary,
  ring correctors and optics, RF, transition, extraction, notching) and the logbook's
  knobs; 402 have hard limits:
  - 94 logged: p1 to p99 over 90 days, widened by 25 % of that span on each side (at
    least 2 % of the median), within the database limits. For a periodic device, only
    its current state counts (readings within a quarter period of its last value).
  - 308 from the database's setting limits, which are mostly the full supply range, not
    an operating range; templates must use small windows around current values.
  - 38 left out: not logged and no usable database limits (wider than 10^6 units:
    timing tables, control words).
- Observables: 503 readings: Booster and injection-line BLMs, efficiencies, charge,
  DCCTs, toroids, BPMs, Linac losses, injection turns, and the computed `WorstLossNorm`.
- Writes: off (`settings_role` `nosettings`) until a template names a role.

The margins (25 %, 2 %), the 10^6 cut, and the 10 % threshold below are untested
choices, for the experts to review.

## Settings other loops also write

50 settings change on more than 10 % of their logged readings (median day), or are a
known autotune target: something else writes them. `L:C7PHAS` changes on 96 % of its
15 Hz readings; `L:RFBPAH` 89 %; gamma-t `B:GMTV` 83 %; the 400 MeV and injection-line
trims, the extraction kickers `B:MKS04`-`07`, and the Linac cavity phase and gradient
adjusts 20-62 %; `B:VIMIN` has its autotune. Column `auto_written`. The environment
refuses Badger writes to them unless its `allow_auto_written` names them, after the
hardware owner confirms the two will not fight (`tests/03_Booster_Pacsys_test.py`).

## Found along the way

- `L:C7PHAS` has two states 158 degrees apart: about 160 and about 316 (-44), the
  latter for days (2026-10-23 to 27) and briefly on other days. A change of phase
  reference? For the experts. Its range uses the current state: 154.0 to 167.5.
- Many Booster readings are logged per pulse with every cycle type mixed, and the logger
  serves no event-qualified version. `scripts/event_tag.py` tags readings by the clock
  events before them and checks the tagging three ways (shares against the cycles, the
  delay from cycle start, and how well the tags separate the values at cycle shifts -2
  to 2). `B:BLMS13` passes (logged 37 ms into each beam cycle; shares match to 0.02 %;
  R^2 0.84 at its own cycle, <= 0.05 elsewhere); `B:CHG0` does not (its readings
  straddle cycle boundaries).

## Open

- Noise profiles for Booster constraints (BLMs, efficiency per cycle type) need the
  readings tagged by cycle type first; existing profiles cover `B:BOOEFF`, `B:BLMLAM`,
  `L:D7TOR`, and `G:LINEFF` (`docs/noise-shapes.md`).
- For the experts: the ring magnets' base-device settings (what they do versus their
  ramp tables), `L:C7PHAS` vs `L:L7PADJ` as the phase knob, `L:C7PHAS`'s second state,
  which loops write the `auto_written` settings, and whether a BLM reading belongs to its
  own cycle (the tagging says so for `B:BLMS13`).
- Templates for the other tasks (orbit, RF capture and transition, extraction, notching,
  tune and chromaticity).
- Untested on the machine; only offline tests (`tests/03_Booster_Pacsys_test.py`).
