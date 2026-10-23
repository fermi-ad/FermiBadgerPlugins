# Linac RIL tuning (Pacsys)

Tunes the front end of the Linac: the RIL ion sources, LEBT, RFQ and MEBT, plus
the last Linac trims, to raise transmission and lower losses. This is the
machine interface behind the operations template `01_Linac_RIL_tuning.yaml`.
It reads and writes ACNET through pacsys. `01_Linac_RIL_tuning_Acsys` is the
same environment through acsys.

## What it can tune (variables)

- Source A and B trims (`L:ATRM*`, `L:BTRM*`, `L:LTRM*`) and solenoids (`L:ASOL`, `L:LSOL`, `L:BSOL`)
- MEBT quads (`L:MUQ1`, `L:MUQ2`, `L:MDQ1`, `L:MDQ2`) and their trims (`L:MUQ1H` ...)
- Mult knobs `mult:MUQ` and `mult:MDQ`: move a pair of MEBT quads together, in fixed proportion (see `mults` below)
- RF phases `L:RFQPAH`, `L:RFBPAH`, `L:V5QSET`
- Linac trims `L:D72TM*`, `L:D73TM*`, `L:D74TM*`

Only the variables checked in the variable table are moved. Each has hard
limits in the code; the template's range (Δ) narrows them further.

## What it can read (objectives, constraints, observables)

- Toroids, efficiency and loss monitors: `L:TUNRAD`, `G:LINEFF`, `L:ATOR`, `B:BOOEFF`, the `L:D..LM` loss monitors, ...
- `<device>-SETPOINT`: the squared distance of a reading from its target in `setpoints`, e.g. `L:D73BPV-SETPOINT`
- `VTrajError_SumSqBPM_calc`: the sum of the three vertical `-SETPOINT` errors (D73, D74, Q2)
- `W_SumLosses`: weighted sum of squares of the loss monitors listed in `w_sumsq`
- `SumAbs_<group>`: the summed |current| of the trims on one bulk supply (see `supplies`)
- `MultOOB_<name>`: how much of the last mult step was lost to a member quad's limits (0 good, 1 = could not move)

## Parameters (Machine Interface)

The loaded template sets these; change them here before a run if needed.

- `settings_role`: the DPM role used to write settings. Must be one your Kerberos principal holds for these devices (operations uses `ril_tuning`). The code default, `ril_tuning_fake`, cannot write.
- `sample_events`: which clock event each reading is taken on, `{device or 'default': '@e,<event>,e,0'}`. Default event 52; `B:BOOEFF` on 1f.
- `average_events`: average each reading over N fresh events, `{device or 'default': N}`. Smoother objectives, but N machine cycles per evaluation. N > 1 needs a streaming event, not `@i`.
- `setpoints`: targets for the `-SETPOINT` observables, `{reading device: value}`.
- `w_sumsq`: weights for `W_SumLosses`, `{loss monitor: weight}`. Each term is (weight × (1 + reading))².
- `periods`: devices whose value wraps around, `{device: period}` (360 for the phases). Readings are unwrapped so a phase passing through 0 is not seen as a jump.
- `supplies`: each bulk power supply, its limit on the summed |current| of its trims in amps, and the trims it feeds, `{group: {limit: 7.0, devices: [DEV1, DEV2, ...]}}`. A write that would exceed a limit is reduced, largest current first. The 7.0 A limits are placeholders pending expert confirmation. **Edit...** opens a dialog: a limit and a device list per supply.
- `mults`: console-style knobs, `{name: {step: 0.05, members: {DEV: coefficient, ...}}}`. Each member moves by coefficient × step × (knob steps) from its as-found setting. With 20.0 and 0.05, one step moves each MEBT quad of a pair by 1.0 A. **Edit...** opens a dialog: a step size and a member table (device pulldown, scale) per mult.
- `debug`: print every read and write to the terminal.

## Safety

- Do not check a MEBT quad and its mult in the same run.
- The production template constrains `SumAbs_*` and `MultOOB_*`, so the optimizer learns to stay clear of supply and quad limits.
- Every device this environment can write is recorded when the template loads; Revert, or the Keep/Revert question on close, puts them back.
