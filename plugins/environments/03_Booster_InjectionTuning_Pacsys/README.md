# Booster injection tuning (Pacsys)

DRAFT: the first Badger environment for the Booster, unconfirmed until the hardware
owner signs off (see the module docstring). Tunes the Booster's horizontal/vertical
injection trajectory and the Linac/Booster boundary RF phase, reading and writing
ACNET through pacsys.

## What it can tune (variables)

- `L:C7PHAS`: Linac accelerating-cavity RF phase, shared Linac/Booster boundary device
- `B:VIMIN`, `B:VIMAX`: GMPS injection-porch and extraction-flattop current.
  **Safety:** `B:VIMIN` runs its own background autotune loop (`B:VIMLUP2` heartbeat,
  `B:VIMERR`, `B:VIMMOD`, `B:VIMDIAG`, targets `B:VIMTGT1-3`/`A-C`). Included here on
  the user's instruction, flagged unconfirmed; do not set `settings_role` to anything
  but `nosettings` until the hardware owner confirms Badger writes will not fight
  that loop.
- `B:MH1`, `B:MH2`: horizontal bend power supplies
- `B:MV1`, `B:MV2`: vertical bend power supplies

Only the variables checked in the variable table are moved. Each has a hard limit in
the code (the live readback band seen in elog screenshots, not a sign-off); the
template's range narrows them further.

## What it can read (objectives, constraints, observables)

- Readings: `B:BOOEFF`, `G:LINEFF`, and every Booster Short BLM (`B:BLMS01`-`24`),
  Long BLM (`B:BLML01`-`24`), and `B:BLMLAM`.
- `WorstLossNorm`: computed. `max` over the calibrated BLMs of
  `(reading - baseline) / scale`, both historical (see `_WORST_LOSS_BASELINE_SCALE`
  in the module). Only 28/49 BLMs are calibrated -- see the module's comment for
  which, and why; the rest are still readable but excluded from this max.

## Parameters (Machine Interface)

- `settings_role`: the DPM role used to write settings; `nosettings` reads only --
  do not change until the `B:VIMIN` autotune interaction above is resolved.
- `sample_events`, `average_events`, `periodic_devices`: present for consistency
  with the other Pacsys environments; empty/default here -- readings use a bare
  LOGGER DRF (no `@event`) historically, and live reads use whatever `get_values`
  defaults to.
- `debug`: print every read and write to the terminal.

## Safety

- Do not raise `settings_role` above `nosettings` for this environment until the
  `B:VIMIN` autotune interaction is confirmed safe by the hardware owner.
- Hard limits are read from elog screenshots, not validated against DevDB (still
  unreachable from the dev Mac) or signed off by the hardware owner.
