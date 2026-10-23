# RCDS (robust conjugate direction search)

A model-free optimizer designed for online accelerator tuning with noisy
measurements (Huang et al., SLAC).

## How it works

It searches along one direction at a time, fitting a parabola to a few noisy
points along that line to find the minimum, then updates its set of search
directions so later lines are better aligned with the problem.

## When to use it

- Noisy objectives where Nelder-Mead struggles.
- A moderate number of variables.
- You want fast steps without a model.

It does not handle constraints.

## Parameters (Optimization Algo)

- `noise`: your estimate of the noise in the objective, in its own units. Too small and it chases noise; too large and it stops early.
- `step`: the initial step along each direction, as a fraction of each variable's range.
- `init_mat`: the starting search directions; left empty, one per variable.

## Tips

- Measure the objective a few times at a fixed setting to estimate `noise`.
- Keep `step` small (0.01 to 0.05) on a running machine.
