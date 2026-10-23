# Sphere test function (simulation)

The simplest possible test: minimize the squared distance from the origin in
three variables. Nothing touches ACNET. Useful for checking that an algorithm
converges.

## What it can tune (variables)

- `x0`, `x1`, `x2` (-1 to 1 each).

## What it can read (objectives, constraints, observables)

- `f` = x0² + x1² + x2², with its minimum, 0, at the origin.

## Parameters (Machine Interface)

None.
