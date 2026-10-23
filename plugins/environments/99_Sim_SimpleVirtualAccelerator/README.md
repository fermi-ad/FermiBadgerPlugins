# Simple virtual accelerator (simulation)

A small toy storage ring (16 bends, two quad families) simulated with xtrack.
Nothing touches ACNET. A quick way to learn Badger: tune the two quads to put
the betatron tunes on target.

## What it can tune (variables)

- `kqf`: focusing quad strength (0.7 to 0.9).
- `kqd`: defocusing quad strength (-0.9 to -0.7).

## What it can read (objectives, constraints, observables)

- `qx`, `qy`: horizontal and vertical tunes.
- `qx-SETPOINT`, `qy-SETPOINT`: the squared distance of each tune from its target in `setpoints`.

## Parameters (Machine Interface)

- `setpoints`: tune targets, e.g. `{qx: 2.05015, qy: 1.20948}`.
- `quad_k_list`: which quad strengths are knobs (default `kqd, kqf`).
- `randomize_settings`: start from randomly perturbed quad settings, so there is something to correct.
- `quad_randomness`: size of that perturbation, as a fraction of each setting (default 0.01).
- `settings_filename`: where the ring's current settings are kept between runs (in this plugin's folder).
- `debug`: print details of each step to the terminal.
