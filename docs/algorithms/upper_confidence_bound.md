# Upper confidence bound (Bayesian optimization)

A Bayesian optimizer like expected improvement, with one knob that sets how
adventurous it is.

## How it works

It fits the same kind of statistical model of the objective and constraints.
The next point is where the predicted value plus a multiple of the model's
uncertainty is best. A larger multiple sends it to explore less-known regions;
a smaller one keeps it near what already looks good.

## When to use it

- As for expected improvement: slow, noisy measurements, constraints, up to 10 to 20 variables.
- When you want to control the balance between exploring and refining directly.

## Parameters (Optimization Algo)

- `beta`: exploration weight (default 2.0). Larger explores more; smaller refines around the best point.
- `shift`: a vertical offset to the acquisition value, used with constraints; leave at 0 unless advised.
- `turbo_controller`, `max_travel_distances`, `numerical_optimizer`, `n_monte_carlo_samples`, `gp_constructor`, `fixed_features`, `use_cuda`: as for expected improvement. The trust-region controller and `max_travel_distances` are the ways to keep steps small.

## Tips

- Lower `beta` toward 0.5 to 1 when close to a known good state and you only want to refine.
- Raise it when the run seems stuck in one region.
