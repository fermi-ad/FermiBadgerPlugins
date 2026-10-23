# Linac energy stabilization (Acsys)

Holds the 400 MeV beam energy steady by adjusting Linac RF: the tank 5 phase
and the phases of two cavities, regulating two energy readings back to their
values at the start of the run. It reads and writes ACNET through acsys.
`01_Linac_EnergyStabilization_Pacsys` is the same environment through pacsys.

## What it can tune (variables)

- `L:V5QSET`: tank 5 phase setting.
- `L:CDPHAS,L:LDPADJ,tol2@0.1` and `L:C7PHAS,L:L7PADJ,tol3@0.45`: cavity phases as read/set pairs. The second device is written; the first is read back until it settles within the tolerance (`tolN@T`).

The phases wrap at 360 degrees; their limits are declared two periods wide
(0 to 720) so a phase can move through the wrap.

## What it can read (objectives, constraints, observables)

- `B:400DFT`, `B:400DF2`: the energy readings.
- `B:400DFT-SETPOINT`, `B:400DF2-SETPOINT`: the squared distance of each from its target in `setpoints`; the usual objectives.
- `DummySumSq`: a placeholder.

## Parameters (Machine Interface)

The loaded template sets these; change them here before a run if needed.

- `settings_role`: the DPM role used to write settings; your Kerberos principal must hold it. The code default, `nosettings`, writes nothing: pick the real role for the run.
- `sample_events`: which clock event each reading is taken on, `{device or 'default': '@e,<event>,e,0'}`. Default event 15.
- `setpoints`: targets for the `-SETPOINT` observables, `{reading device: value or 'hold'}`. `hold` means the reading at the start of the run, so the run regulates to wherever the machine was.
- `periods`: devices whose value wraps around, `{device: period}`. Readings are unwrapped so a phase passing through 0 is not seen as a jump.
- `debug`: print every read and write to the terminal.

## Safety

- With `nosettings` nothing is written and nothing is snapshotted for Revert.
- Every device this environment can write is recorded when the template loads (with a real role); Revert, or the Keep/Revert question on close, puts them back.
