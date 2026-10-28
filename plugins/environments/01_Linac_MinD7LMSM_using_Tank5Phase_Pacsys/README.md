# Linac: minimize D7 losses with the tank 5 phase (Pacsys)

A one-knob test environment: adjust the tank 5 phase to minimize the loss
monitor sum `L:D7LMSM`. It reads and writes ACNET through pacsys.
`01_Linac_MinD7LMSM_using_Tank5Phase_Acsys` is the same environment through
acsys.

## What it can tune (variables)

- `L:V5QSET`: tank 5 phase setting (-34 to -32).

## What it can read (objectives, constraints, observables)

- `L:D7LMSM`: D7 loss monitor sum, to minimize.

## Parameters (Machine Interface)

- `settings_role`: the DPM role used to write settings; your Kerberos principal must hold it (default `testing`).
- `sample_events`: which clock event the readings are taken on, `{device or 'default': '@e,<event>,e,<delay>'}`. Default event 15.
