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
- `TwoWells` (the template's objective, minimize): a demonstration landscape over all four devices. A tilted bowl (the knobs are coupled: the best value of one depends on the others) with its global minimum, −6.0, at `G:AMANDA`=3, `Z:CUBE_X`=−4, `Z:CUBE_Y`=2, `Z:CUBE_Z`=5, and a shallower decoy (−3.06) near (−6, 5, −5, −3). The template searches −10 to 10 on each device from wherever they are: from all zeros (objective 0.19), expected improvement typically reaches −5.9 within about 20 points. Start the devices near the decoy to watch it get out of a local minimum.
- `AMANDA_sq`, `CUBE_X_sq`, `CUBE_Y_sq`, `CUBE_Z_sq`: (device − 0.5)², each with its minimum at 0.5. Minimize their sum to watch an optimizer converge.

## Parameters (Machine Interface)

- `settings_role`: the DPM role used to write settings; your Kerberos principal must hold it (default `testing`).
- `debug`: print every read and write to the terminal.
