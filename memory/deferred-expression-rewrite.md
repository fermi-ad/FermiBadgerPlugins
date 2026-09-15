---
name: deferred-expression-rewrite
description: How VirtualAccelerator_MADXSuite gets live knobs, and what that makes read-only
metadata:
  type: project
---

`create_VA()` rewrites the lattice source `=` -> `:=` (madx_deferred.py) before
handing it to MAD-X, so the formulas reach xtrack's xdeps graph and
`set_variables()` is just `line.vars.update()`. Consequences a developer will
trip over:

- **The rewrite is verified, and it can fall back.** `_verify_rewrite()` loads
  the original into a throwaway `Madx` and compares every global and element
  attribute at rtol=1e-12. On mismatch it sets `_use_deferred = False` and the
  old per-iteration `_update_madx_variables()` rebuild runs instead — correct,
  but ~150x slower. Check `env._use_deferred` when iterations feel slow.
- **Expression-driven quantities are no longer knobs.** `q_dq303.k1` and the
  `g_*` gradients are outputs of the supply currents now; assigning one would
  overwrite its formula and sever the dependence for the session. Tune with
  `i_dqd`, `i_dht301`, etc.
- **Monitors come from MAD-X base type**, not `bpm_name_pattern` (which is now
  an optional extra filter, default None). Each advertises only the plane it
  measures.
- **`twiss_init` switches the twiss from periodic to open** (START..END) for a
  transfer line, and suppresses qx/qy/dqx/dqy, which do not exist there.
- **Bend angles still move nothing** — xtrack's `Bend` carries the reference
  trajectory with the geometry. Pre-existing, not caused by the rewrite.

Details and measured numbers: docs/progress.md, 2026-09-14.
Tests: tests/VA_deferred_expressions_test.py, and the `__main__` self-check in
madx_deferred.py.
