# The Delivery Ring lattice in the Badger simulator

Notes for the lattice's author, 2026-11-16. Lattice: `sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx`.

The Mu2e Delivery Ring lattice now drives a fast Badger simulation: one optimizer
evaluation (set knobs, recompute the optics) takes about 30 ms, and five new tuning
templates exercise orbit, chromaticity, lattice functions, and model fitting on it.
Several findings below concern the lattice file itself and need the author's eye;
the questions are collected at the end.

## How the simulator uses the lattice

The file is read once per process; after that, a knob change only re-evaluates the
formulas that depend on it.

1. **Rewrite.** Every immediate assignment (`=`) is rewritten in memory as a
   deferred one (`:=`), so formulas such as
   `G_DQ206 = F_DQ206 * F_SQD * (C0_SQD + C1_SQD * I + ...) * E_LIGHT / (...)`
   survive instead of being frozen at parse time. Right-hand sides with `ranf`,
   `gauss`, `tgauss`, or `table()` stay immediate; CALLed files are not rewritten
   (this lattice has none).
2. **Verify.** MAD-X (through cpymad) loads both the rewritten and the original
   text, and every global and every element's `l`, `k1`, `k2`, `k3`, `angle`, and
   `tilt` are compared. This lattice passes. The result is stamped beside the
   file, so the check reruns only when the file, the rewriter, or cpymad changes.
3. **Convert.** The sequence `full` becomes an xtrack Line with the formulas in
   its dependency graph (xdeps).
4. **Deduce.** The knobs offered (2,284 lattice variables that drive elements:
   supply currents `I_*`, fudge factors `F_*`, and so on) and the readings (tunes,
   chromaticities, optics at the ring start, and the orbit at the 119 BPMs) are
   found in the lattice itself and cached in a `.varcache.json` beside it.
5. **Evaluate.** Setting a knob updates the graph (1.6 ms); a 4D periodic twiss
   then gives the optics (25 ms). The chromatic pass (112 ms) runs only when a
   chromaticity is read.

One xtrack behavior to know: changing a main bend's angle moves neither the orbit
nor the tune, because the reference trajectory moves with it.

## Speed

Measured on a MacBook (arm64); the production host was not measured.

| Step | Before | After (2026-11-10) |
|---|---|---|
| First load in a process (parse, rewrite, verify, convert) | 7.8–9.4 s | 4.0–5.4 s (verification stamped) |
| Each new environment (the GUI makes one per template load and per run) | 1.3 s | 0.12 s (deduced lists cached) |
| One evaluation: set knobs, twiss, read | 27–38 ms | unchanged |
| One optimizer step (choosing the next point), EI, closed loop | 3.3 s | 0.7 s (acquisition search limited to 0.5 s, 5 restarts) |

The optimizer, not the simulation, is the bottleneck: choosing a point costs about
20 times more than simulating it (about 100 times before the change above). Hand-written C or CUDA was not pursued: xtrack's
tracking is already compiled C (about half of the 25 ms twiss). Templates that need
multi-turn tracking (slow extraction, dynamic aperture) would change that picture;
not explored.

## Task templates built on the lattice

From the Delivery Ring tuning-task list (orbit, tunes, chromaticity, lattice
functions, model errors). Each starts from a deliberately imperfect machine and
aims back at the design optics. For each, least squares over the same knobs first
confirmed that a solution exists; then a closed-loop Badger optimization (20 steps,
30 for the lattice functions) was run.

| Template | Knobs | Imposed errors | Objective (constraints) | Closed loop | Least squares |
|---|---|---|---|---|---|
| `DR_OrbitH` | 11 horizontal trims `I_DHT*`, ±3 A | 4 quads offset 0.2–0.3 mm in x | RMS x at the horizontal BPMs | 0.62 → 0.36 mm | 0.21 mm |
| `DR_OrbitV` | 8 vertical trims `I_DVT*`, ±3 A | 4 quads offset 0.2–0.3 mm in y | RMS y at the vertical BPMs | 1.27 → 0.47 mm | 0.25 mm |
| `DR_BetatronTunes` (existing) | `I_DQF`, `I_DQD` | none (targets differ from design) | squared tune errors | — | — |
| `DR_Chromaticity` | `I_DSEXF`, `I_DSEXD`, design ±10% | 6 sextupole fudge factors off 6–8% | squared chromaticity errors (design 2.05, −1.53) | −99.5% | restored to 0.004 |
| `DR_LatticeFunctions` | `I_DQF`, `I_DQD` ±0.2%, `I_DQSS` ±0.5%, `I_DQ404` ±3%, `I_DQS105`, `I_DQS605`, `I_DQS301`, `I_DQS505` ±10% | 6 quad fudge factors off 2–2.5% | beta beat (x, y) + dispersion in the straights (phase 602→502 within 3° of 1050°, beta at the kickers, tunes within 0.01) | −23% | −27% |
| `DR_ModelFit` | 8 candidate quad fudge factors `F_DQ*` | hidden machine: `F_DQ105` 1.02, `F_DQ309` 0.975, `F_DQ512` 1.015 | RMS mismatch of the orbit response to all 19 trims | −32% | all 3 recovered to 0.001 |

Notes on the templates:

- The lattice-function knobs were chosen by sensitivity to these particular errors;
  other error sets would call for other knobs. A 1% change on a main bus moves
  `qx` by about 0.1, hence the narrow windows.
- The dispersion leaking into the straights is not corrected (0.08 m RMS after the
  errors, against 0.017 m in the design). Three of the six erring quads (`Q_DQ309`,
  `Q_DQ416`, `Q_DQ512`) are powered by the main buses alone; the other three have
  shunts (`I_DQS105`, `I_DQS213`, `I_DQS607`), of which only `I_DQS105` is among the
  eight knobs. Whether adding `I_DQS213` and `I_DQS607` fixes the straights is
  untested.
- In the model fit, the hidden machine stands in for real measurements. A
  real-machine version would read a measured orbit response instead.

## Findings about the lattice file

- **The movable quad stand variables do nothing.** `LH_DQ*` (36) and `LV_DQ*` (37)
  are defined (all 0), but no element refers to them, so changing one moves no
  quad. Quad offsets in the templates are therefore set directly on the elements
  (`shift_x`, `shift_y`).
- **Names differ from the task list.** The BPMs are `P_DHP*` and `P_DVP*` (119
  monitors), not `M_DHP*`/`M_DVP*`; ad-lattices maps them to ACNET (`P_DHP101` →
  `D:HP101`). The harmonic sextupoles are `S_DSX101`, `S_DSX602`, `S_DSX604`,
  `S_DSX504`, `S_DSX502`, and `S_DSX401`, with markers `M0_DSX*` and `M1_DSX*`;
  there are no `M_DSX*` elements.
- **Harmonic-sextupole phase advances.** At design, the horizontal phase advance
  from `M0_DSX602` to `M0_DSX502` is 1051.8°, 1.8° from 1050° (35 × 30°).
  Consecutive circuits are not 30° multiples: 64.4°, 81.4°, 886.2°, 84.2°, and
  64.9° (101→602→604→504→502→401).
- **Dispersion-free straights.** The 41 BPMs numbered x01–x07 in each sector have
  |Dx| < 0.05 m at design, 0.017 m RMS; all other BPMs reach up to 2.33 m.
- **Kickers.** `D_DKK3IA`, `D_DKK3IB`, `D_DKK5AA`, `D_DKK5AB`, and `D_DKK5AC` are
  RBENDs with βx 5.5–10.2 m, βy 6.8–12.7 m, and |Dx| ≤ 0.034 m at design.
- **Fudge factors are calibrated values,** not 1.0 (for example `F_DQ105` =
  1.0136). The model-fit template treats a few of them as the unknowns.
- **Design values in this model:** Qx 9.6489, Qy 9.7352, Q′x 2.048, Q′y −1.530;
  circumference 505.28 m. One amp on a trim moves the orbit by about 0.29 mm RMS;
  a 0.5 mm quad offset gives 0.69 mm RMS.

## Questions for the lattice author

- Should `LH_DQ*` and `LV_DQ*` drive the quad offsets (for example through EALIGN)?
- Is "M_DSX602 ~ M_DSX502" the horizontal phase advance from circuit 602 to circuit
  502, which should be a multiple of 30°? Are other circuit pairs meant too?
- Which elements are "the kickers," or aperture restrictions in general? Are the
  injection septum `D_DISEP`, the electrostatic septa `D_DESSA`/`D_DESSB`, and the
  Lambertson `D_DELAM` among them?
- Which quad supplies are independently adjustable on the machine for
  lattice-function tuning? The lattice has `I_DQF`, `I_DQD`, `I_DQSS`, `I_DQ404`,
  and 61 shunts `I_DQS*` (each subtracted from its bus current in the quad's
  formula).
- What sizes of errors are realistic: quad strength (percent), quad offsets (mm),
  sextupole strength?
- If beam size rather than beta should be scored at the kickers: what emittance and
  momentum spread?
- Is 0.017 m RMS of dispersion in the straights at design as intended?

## Where the code is

In this repository (fermi-ad/FermiBadgerPlugins):

- The simulation environment and what it can read:
  [`plugins/environments/99_Sim_VirtualAccelerator_MADXSuite/README.md`](../plugins/environments/99_Sim_VirtualAccelerator_MADXSuite/README.md);
  the `=` to `:=` rewrite:
  [`madx_deferred.py`](../plugins/environments/99_Sim_VirtualAccelerator_MADXSuite/madx_deferred.py).
- The templates:
  [`tuning_templates/simulation/`](../tuning_templates/simulation/) (`DR_*`), written by
  [`scripts/make_dr_task_templates.py`](../scripts/make_dr_task_templates.py) and
  checked with [`scripts/sim_closed_loop.py`](../scripts/sim_closed_loop.py).
- Speed measurements: [`scripts/profile_dr_sim.py`](../scripts/profile_dr_sim.py),
  [`scripts/profile_dr_speedups.py`](../scripts/profile_dr_speedups.py).
- Tests: [`tests/VA_dr_tasks_test.py`](../tests/VA_dr_tasks_test.py),
  [`tests/VA_load_caches_test.py`](../tests/VA_load_caches_test.py).
- History: [`docs/log.md`](log.md), entries of 2026-11-10 and 2026-11-16.
