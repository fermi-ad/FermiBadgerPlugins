# Archetype (Pacsys)

<!-- ARCHETYPE-ONLY -->
**A pattern for developers, not for tuning.** This environment holds every feature
the Pacsys environments in this repo use, in one place, and never writes (it refuses any
settings role but `nosettings`). Make a new environment from it with
`pixi run new-env <region>_<Descriptive>_Pacsys`; see `docs/developer-guide.md`.
<!-- END ARCHETYPE-ONLY -->

One paragraph: what this environment tunes, and why. It reads and writes ACNET
through pacsys.

## What it can tune (variables)

- Source A trims `L:ATRMHU`, `L:ATRMVU`, `L:ATRMHD`, `L:ATRMVD` and MEBT Q1 trims
  `L:MUQ1H`, `L:MUQ1V`, `L:MDQ1H`, `L:MDQ1V`: each pair of four shares a bulk power
  supply (see `BulkPS_Limit`)
- MEBT quads `L:MUQ1`, `L:MUQ2`, and the mult knob `mult:MUQ`, which moves both
  together in fixed proportion (see `mults`)
- RFQ phase `L:RFQPAH` (periodic)
- Cavity phase: set `L:LDPADJ`, read `L:CDPHAS`, and wait for the reading to settle

Only the variables checked in the variable table are moved. Each has hard limits
in the code; the template's range (Δ) narrows them further.

## What it can read (objectives, constraints, observables)

- Readings: `G:LINEFF`, `L:D7TOR`, `L:TK1RAD`, `B:BOOEFF`
- `<device>-SETPOINT`: the squared distance of a reading from its target in
  `setpoints`, e.g. `B:400DFT-SETPOINT`
- `Z:ITGSIG_1_SRS[:]|std`: the spread of an array reading
- `W_SumLosses`: weighted sum of squares of the loss monitors in `w_sumsq`
- `VTrajError_SumSqBPM_calc`: the sum of the two vertical BPM `-SETPOINT` errors
- `SpillDutyFactor_calc`: 1 / (1 + variance of the spill), from two array readings
- `BulkPS_SourceATrims_Pos`, `BulkPS_SourceATrims_Neg`, `BulkPS_MEBTQ1trims`: the
  current drawn from each bulk supply
- `MultOOB_MUQ`: how much of the last mult step was lost to a quad's limits (0
  good, 1 = could not move)

## Parameters (Machine Interface)

The loaded template sets these; change them here before a run if needed.

- `settings_role`: the DPM role used to write settings; `nosettings` reads only.
- `sample_events`: which clock event each reading is taken on,
  `{device or 'default': '@e,<event>,e,0'}`.
- `average_events`: average each reading over N fresh events, `{device or 'default': N}`.
- `periodic_devices` (formerly `periods`): devices whose value wraps around, `{reading device: period}`.
- `setpoints`: targets for the `-SETPOINT` observables, a number or `'hold'` (the
  first reading of the run).
- `BulkPS_Limit`: each bulk power supply, its trims, and its limit in amps.
  **Edit...** opens a dialog.
- `mults`: console-style knobs, `{name: {step, members: {DEV: coefficient}}}`.
  **Edit...** opens a dialog.
- `w_sumsq`: weights for `W_SumLosses`.
- `spill_length`: samples per spill, for `SpillDutyFactor_calc`.
- `debug`: print every read and write to the terminal.

## Safety

- Do not check a MEBT quad and its mult in the same run.
- Constrain the `BulkPS_*` and `MultOOB_*` observables, so the optimizer learns to
  stay clear of supply and quad limits.
- Every device this environment can write is recorded when the template loads;
  Revert, or the Keep/Revert question on close, puts them back.
