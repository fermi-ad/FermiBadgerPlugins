# Linac: minimize D7 losses with the tank 5 phase (Acsys)

A one-knob test environment: adjust the tank 5 phase to minimize the loss
monitor sum `L:D7LMSM`. It reads and writes ACNET through acsys.
`01_Linac_MinD7LMSM_using_Tank5Phase_Pacsys` is the same environment through pacsys.

## What it can tune (variables)

- `L:V5QSET`: tank 5 phase setting (-34 to -32).

## What it can read (objectives, constraints, observables)

- `L:D7LMSM`: D7 loss monitor sum, to minimize.

## Parameters (Machine Interface)

- `settings_role`: the DPM role used to write settings; your Kerberos principal must hold it (default `testing`).
- `sample_event`: the clock event the readings are taken on (default `E,15,E,0`).

## Known issue

This environment predates the current interface: it calls interface methods
in ways that no longer match (`get_value`, and adding `.SETTING` itself). It
is expected to fail until it is brought up to date. `01_Linac_RIL_tuning` and
`01_Linac_EnergyStabilization` show the current pattern.
