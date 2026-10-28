# Linac auto-steer restore (Pacsys)

Steers the beam at the end of the Linac back onto a reference trajectory,
using six trims, by minimizing the distance of the BPM readings from their
reference positions. It reads and writes ACNET through pacsys.
`01_Linac_AutoSteerRestore_Acsys` is the same environment through acsys.

## What it can tune (variables)

- Trims `L:D72TMH`, `L:D72TMV`, `L:D73TMH`, `L:D73TMV`, `L:D74TMH`, `L:D74TMV` (-4.5 to 4.0 A).

## What it can read (objectives, constraints, observables)

- `<BPM>-SETPOINT`: the squared distance of a BPM reading from its reference in `setpoints`, for D73, D74 and Q2, horizontal and vertical, as live (`...BPH`, `...BPV`, `B:HPQ2`, `B:VPQ2`) and integrated (`...HPA`, `...VPA`) readings.
- `L:TUNRAD`, `G:LINEFF`: transmission and efficiency.
- `VTrajError_SumSqBPM_calc`: the sum of the `-SETPOINT` errors read in the same evaluation.
- `W_SumLosses`: weighted sum of squares of the Linac loss monitors listed in `w_sumsq`.

## Parameters (Machine Interface)

The loaded template sets these; change them here before a run if needed.

- `settings_role`: the DPM role used to write settings; your Kerberos principal must hold it. The code default, `ril_tuning_fake`, cannot write.
- `sample_events`: which clock event each reading is taken on, `{device or 'default': '@e,<event>,e,0'}`. Default event 00; `B:BOOEFF` on 1f.
- `setpoints`: reference positions for the `-SETPOINT` observables, `{reading device: value}`.
- `w_sumsq`: weights for `W_SumLosses`, `{loss monitor: weight}`. Each term is (weight × (1 + reading))².
- `debug`: print every read and write to the terminal.

## Safety

- Every device this environment can write is recorded when the template loads; Revert, or the Keep/Revert question on close, puts them back.
