# Random sampling

Tries points chosen uniformly at random within each variable's range. It does
not try to improve anything.

## When to use it

- A quick look at how the objective responds across the ranges.
- Collecting initial data before switching to a Bayesian method.

Every point is independent of the last, so on a live machine keep the ranges
(Δ) small: consecutive points can be far apart.

## Parameters (Optimization Algo)

None.
