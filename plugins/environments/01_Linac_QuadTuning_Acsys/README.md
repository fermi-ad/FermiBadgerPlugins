# Linac quad tuning (Acsys)

Tunes the Linac quadrupoles to lower beam losses along the Linac. It reads and writes ACNET through acsys. `01_Linac_QuadTuning_Pacsys` is the same environment through pacsys.

## What it can tune (variables)

- Drift-tube Linac quads `L:Q01` ... `L:Q44` (45 to 185 A).
- Side-coupled Linac quad supplies `L:QPS501` ... `L:QPS513` (60 to 200 A). `L:QPS508` runs on an isolation transformer after a failure: do not push it high.

## What it can read (objectives, constraints, observables)

- `L:400SCA`, `L:TUNRAD`, `L:DELM5`, `G:LINEFF`: transmission, efficiency and losses.
- `W_SumLosses`: weighted sum of squares of the Linac loss monitors listed in `w_sumsq`; the usual objective.
- `DummySumSq`: a placeholder.

## Parameters (Machine Interface)

The loaded template sets these; change them here before a run if needed.

- `settings_role`: the DPM role used to write settings; your Kerberos principal must hold it (default `linac_quads`).
- `sample_events`: which clock event each reading is taken on, `{device or 'default': '@e,<event>,e,0'}`. Default event 0A.
- `w_sumsq`: weights for `W_SumLosses`, `{loss monitor: weight}`. Each term is (weight × reading)².
- `debug`: print every read and write to the terminal.

## Safety

- Every device this environment can write is recorded when the template loads; Revert, or the Keep/Revert question on close, puts them back.
