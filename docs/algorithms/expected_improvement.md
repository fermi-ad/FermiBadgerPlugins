# Expected improvement (Bayesian optimization)

The default for machine tuning, and what `01_Linac_RIL_tuning.yaml` uses.

## How it works

After each measurement it fits a statistical model (a Gaussian process) of how
the objective and every constraint depend on the checked variables. The next
point it tries is the one where the model expects the largest improvement over
the best feasible result so far. It balances trying near the best point
against exploring regions the model is unsure about.

## When to use it

- Measurements are slow or costly: it needs few evaluations.
- The objective is somewhat noisy.
- There are constraints, e.g. losses that must stay below a limit.
- Up to roughly 10 to 20 variables; it slows down and needs more points beyond that.

Each step takes a moment to compute, so it is not suited to very fast
feedback loops.

## Parameters (Optimization Algo)

- `turbo_controller`: keeps each new point inside a trust region.
  - `SafetyTurboController` (used by the operations template) centres the region on the average of the points that met all constraints. It grows the region when recent points meet them and shrinks it when they do not. It needs at least one constraint.
  - `OptimizeTurboController` centres the region on the best point so far. It grows the region when recent points improve on it and shrinks it when they do not.
  - Their settings:
    - `length`: region size, as a fraction of each variable's range. Start small for cautious steps.
    - `length_min`, `length_max`: limits on that size.
    - `scale_factor`: how much it grows or shrinks at a time.
    - `success_tolerance`, `failure_tolerance`: how many good or bad points in a row before it changes.
    - `restrict_model_data`: fit the model only to points inside the region.
- `max_travel_distances`: the largest step from the last point for each variable, as a fraction of its range, e.g. `[0.1, 0.1, ...]`. Another way to keep steps small.
- `numerical_optimizer`: how hard it searches the model for the next point. `n_restarts` is how many tries; `max_time` caps the seconds per step.
- `n_monte_carlo_samples`: samples used to evaluate the model; the default is fine.
- `gp_constructor`: how the model is built; leave at default unless you know why.
- `fixed_features`: hold some variables at a fixed value.
- `use_cuda`: use a GPU if one is available.

## Tips

- Start from a sensible machine state: the first points are taken around the current settings.
- Narrow the variable ranges (Δ) rather than widening them; the model learns faster in a small region.
- If it keeps proposing large jumps, reduce the trust region `length` or set `max_travel_distances`.
