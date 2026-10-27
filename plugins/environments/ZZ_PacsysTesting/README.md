# Pacsys testing (scratch devices)

A harmless live test of the whole chain, from Badger to a real
Kerberos-authenticated pacsys write and read, on ACNET test devices with no
hardware behind them. Use it to check an installation, or safe-badger, before
touching the machine.

## What it can tune (variables)

- `G:AMANDA`, `Z:CUBE_X`, `Z:CUBE_Y`, `Z:CUBE_Z` (-100 to 100). Scratch devices: safe to vary freely.

## What it can read (objectives, constraints, observables)

- The four devices themselves.
- `AbsProduct`: |G:AMANDA × Z:CUBE_X × Z:CUBE_Y × Z:CUBE_Z|.
- `CombineObjective`: sign(G:AMANDA) × Z:CUBE_X × Z:CUBE_Y × Z:CUBE_Z.
- `TwoWells` (the template's objective, minimize): a demonstration landscape over all four devices. A tilted bowl (the knobs are coupled: the best value of one depends on the others) with its global minimum, −6.0, at `G:AMANDA`=3, `Z:CUBE_X`=−4, `Z:CUBE_Y`=2, `Z:CUBE_Z`=5, and a shallower decoy (−3.06) near (−6, 5, −5, −3). The template searches −10 to 10 on each device, starting from one point near the decoy, (−4, 4, −4, −2) (objective −0.98; set by the template's `initial_points`, whatever the devices read before). In offline runs of the template's algorithm, BO falls into the decoy (about −3.0) by point 20, then gets out and reaches −5.9 or better by point 41 (first point below −4.5 at 30-32): let it run about 40 evaluations. Started from all zeros instead, it reaches −5.9 within about 20 points.
- `AMANDA_sq`, `CUBE_X_sq`, `CUBE_Y_sq`, `CUBE_Z_sq`: (device − 0.5)², each with its minimum at 0.5. Minimize their sum to watch an optimizer converge.

## Parameters (Machine Interface)

- `settings_role`: the DPM role used to write settings; your Kerberos principal must hold it (default `testing`).
- `debug`: print every read and write to the terminal.
