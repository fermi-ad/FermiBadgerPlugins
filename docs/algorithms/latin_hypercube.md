# Latin hypercube sampling

Spreads points evenly over the variable ranges, so a fixed number of samples
covers the space better than random sampling. It does not try to improve
anything.

## When to use it

- Mapping the response over the ranges, e.g. to build or check a model.
- Collecting well-spread initial data for a Bayesian method.

As with random sampling, consecutive points can be far apart: keep the ranges
(Δ) small on a live machine.

## Parameters (Optimization Algo)

- `batch_size`: how many points are planned at once; they are then used one by one.
- `scramble`: place each point randomly within its cell (on) or at the cell centre (off).
- `optimization`: improve the spread after sampling (`random-cd`), or not.
- `strength`: 1 for a plain Latin hypercube, 2 for a more uniform orthogonal one.
- `seed`: fix it to get the same points again.
