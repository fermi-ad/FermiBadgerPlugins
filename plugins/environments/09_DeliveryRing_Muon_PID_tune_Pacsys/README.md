# Delivery Ring muon slow-spill PID tuning (Pacsys)

Tunes the gains of the Delivery Ring slow-extraction regulation loop to make
the muon-campaign spill smoother, i.e. to raise the spill duty factor. It reads
and writes ACNET through pacsys. `09_DeliveryRing_Muon_PID_tune_Acsys` is the
same environment through acsys.

## What it can tune (variables)

- `Z:QDPID_P_SRS`, `Z:QDPID_I_SRS`, `Z:QDPID_D_SRS`: the proportional, integral and derivative gains (-0.1 to 0.1).

## What it can read (objectives, constraints, observables)

- `DR_SDF_calc`: spill duty factor, 1 / (1 + variance of the spill signal `Z:ITGSIG_1_SRS` over the spill). The spill starts at the first non-zero sample of `Z:INSPLL_1_SRS` and lasts `spill_length` samples. Higher is smoother.

## Parameters (Machine Interface)

- `settings_role`: the DPM role used to write settings; your Kerberos principal must hold it. The code default, `fake`, cannot write.
- `spill_length`: spill length in samples (default 430).
- `sample_events`: which clock event each reading is taken on, `{device or 'default': '@e,<event>,e,<delay>'}`. Default event 83.
- `setpoints`, `w_sumsq`: present for consistency with the other machine environments; not used by `DR_SDF_calc`.
- `debug`: print every read and write to the terminal.

## Known issue

`DR_SDF_calc` currently fails: the code checks for the name `DR_SDF` instead of
`DR_SDF_calc` when deciding to read the spill arrays, so they are never read.
The Acsys twin also has a syntax error that stops it loading.

## Safety

- Every device this environment can write is recorded when the template loads; Revert, or the Keep/Revert question on close, puts them back.
