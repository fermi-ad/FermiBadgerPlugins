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
- `AMANDA_sq`, `CUBE_X_sq`, `CUBE_Y_sq`, `CUBE_Z_sq`: (device − 0.5)², each with its minimum at 0.5. Minimize their sum to watch an optimizer converge.

## Parameters (Machine Interface)

- `settings_role`: the DPM role used to write settings; your Kerberos principal must hold it (default `testing`).
- `debug`: print every read and write to the terminal.
