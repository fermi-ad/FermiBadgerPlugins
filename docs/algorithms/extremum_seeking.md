# Extremum seeking

A feedback method that keeps nudging the machine toward the optimum and can
follow it as it drifts (Scheinker et al.).

## How it works

Each variable is dithered, made to oscillate slightly at its own frequency,
while the objective is watched. The way the objective responds to each
oscillation shows which direction improves it, and the variable is moved that
way. It runs continuously rather than converging and stopping.

## When to use it

- Tracking a slowly drifting optimum over a long time.
- Many variables at once; its cost per step does not grow much with their number.

It needs many steps, every step moves every variable a little, and it does
not handle constraints.

## Parameters (Optimization Algo)

- `k`: feedback gain. Higher moves faster toward the optimum, but too high overshoots.
- `oscillation_size`: dither amplitude, as a fraction of each variable's range. Large enough to see in the objective above its noise, small enough to be acceptable on the machine.
- `decay_rate`: how fast the dither shrinks over time (1.0 = it does not shrink).

## Tips

- Start with a small `oscillation_size` and increase it only until the objective clearly responds.
