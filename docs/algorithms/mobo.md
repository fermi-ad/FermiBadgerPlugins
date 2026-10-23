# Multi-objective Bayesian optimization (MOBO)

For two or more objectives that pull against each other, for example
transmission versus losses, or two tunes at once.

## How it works

It models every objective, then looks for the best trade-offs between them:
the set of points where no objective can improve without another getting
worse (the Pareto front). Each new point is chosen to extend that front as
much as possible.

## When to use it

- You care about several objectives and want to see the trade-off, rather than combining them into one number yourself.
- Measurements are slow; like the other Bayesian methods it needs few evaluations.

The result is a set of good compromises, not a single best point; pick one
from the run data and use Dial in solution.

## Parameters (Optimization Algo)

- `reference_point`: required. For each objective, the worst value you would still accept, e.g. `{loss: 1.0, efficiency: 0.8}`. Points worse than this in any objective count for nothing.
- `use_pf_as_initial_points`: start the search for the next point from the current Pareto front.
- `turbo_controller`, `max_travel_distances`, `numerical_optimizer`, `n_monte_carlo_samples`, `gp_constructor`, `fixed_features`, `use_cuda`: as for expected improvement.

## Tips

- Set the reference point a little worse than your current values, so the start already counts.
- Two or three objectives work well; more need many more points.
