# Linac energy toy model (simulation)

A three-variable test function standing in for a Linac energy optimization.
Nothing touches ACNET.

## What it can tune (variables)

- `C7PHAS` (-π to π), `x1` (-1 to 2), `x2` (-1 to 1).

## What it can read (objectives, constraints, observables)

- `f` = C7PHAS × (x1² + x2²).
- `C7PHAS` itself.

## Parameters (Machine Interface)

None.
