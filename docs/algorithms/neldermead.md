# Nelder-Mead simplex

A classic, model-free search: simple, predictable, and fast to compute.

## How it works

It keeps a set of points one more than the number of variables (a simplex)
and repeatedly replaces the worst one by reflecting it through the others,
stretching or shrinking the set as it goes. It only compares objective values;
it builds no model.

## When to use it

- Few variables (up to about 5).
- Low noise: noisy readings easily mislead it.
- You want each step to be computed instantly.

It does not handle constraints, and it does not look outside the neighbourhood
of its starting point.

## Parameters (Optimization Algo)

- `initial_point`: where to start; left empty, it starts from the current settings.
- `initial_simplex`: the starting set of points, if you want to give it explicitly.
- `adaptive`: adjust its internal step rules to the number of variables (recommended).
- `trace`: print its progress to the terminal.

## Tips

- The variable ranges (Δ) set the size of its first steps: keep them modest.
- If the objective is noisy, average more readings per point or use a Bayesian method instead.
