# Virtual accelerator from a MAD-X lattice (simulation)

A simulated machine built from a MAD-X lattice file: changing a knob
re-simulates the optics in a fraction of a second. Nothing touches ACNET. The
variables and observables are found in the lattice itself, so any lattice
works without code changes.

## What it can tune (variables)

Deduced from the lattice: its knobs and element strengths, such as quad
`k1`s and corrector kicks. Bounds are the current value ± `rel_range`, or
± `zero_half_range` for a knob that is currently zero.

## What it can read (objectives, constraints, observables)

- Ring optics: tunes `qx`, `qy`; chromaticities `dqx`, `dqy`; beta, alpha and dispersion at the start (`beta_x`, `alpha_x`, `disp_x`, `dpx`, and the y versions).
- Beam positions at every BPM (MAD-X monitor elements), per plane.
- `<observable>-SETPOINT`: the squared distance of an observable from its target in `setpoints`, or from its design value at load.
- `optics_stable`: 1.0 while the optics solve, 0.0 when they do not. Use the constraint `optics_stable > 0.5` to keep the optimizer out of unstable regions; there every optics observable reads NaN.

## Parameters (Machine Interface)

- `lattice_filename`: the MAD-X lattice, relative to the repo root (e.g. `sim_configs/DeliveryRing/...madx`).
- `sequence_name`: the MAD-X sequence to use.
- `beam_p0c_eV`: reference momentum × c in eV, used if the lattice defines no beam (default: Mu2e Delivery Ring protons, 8.89 GeV).
- `rel_range`, `zero_half_range`: how the variable bounds are derived (above).
- `bpm_name_pattern`: a case-insensitive regex to narrow which monitors count as BPMs.
- `twiss_init`: starting optics for a transfer line (`betx`, `alfx`, `bety`, `alfy`, optionally dispersion and centroid), as a mapping. Leave empty for a ring.
- `setpoints`: targets for `-SETPOINT` observables, e.g. `{qx: 9.65, qy: 9.74}`.
- `debug`: print details of each step to the terminal.

## Notes

- The first load of a large lattice takes several seconds; the deduced variables are cached beside the lattice (`.varcache.json`). Delete that file to force a fresh deduction.
- Changing a main bend angle moves neither orbit nor tune in this model; steer with corrector kicks.
