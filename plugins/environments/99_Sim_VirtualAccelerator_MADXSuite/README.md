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
- Any optics column at any element, typed as `<element>.<column>`, e.g. `m0_dsx602.mux`.
- Whole-ring quantities, typed by name:
  - `<stat>(<column>@<regex>)`: a statistic (`rms`, `mean`, `max`, `min`, `maxabs`) of one column over the elements whose names match the regex. Examples: `rms(x@^p_dhp)`, the RMS horizontal orbit at the horizontal BPMs; `max(betx@^d_dkk)`, the largest beta at the kickers. The columns `bbetx` and `bbety` are the beta beat, beta / design beta − 1.
  - `phase_x(<a>,<b>)`, `phase_y(<a>,<b>)`: the phase advance from element a to a downstream element b, in degrees.
  - `sum(<observable>,...)`: the sum of other observables, e.g. `sum(dqx-SETPOINT,dqy-SETPOINT)`, one objective from two targets.
- `orm_rms`: with `truth_errors` set, the RMS difference (mm/A) between this machine's orbit response to each corrector and that of the hidden "real" machine. For fitting the model.

## Parameters (Machine Interface)

- `lattice_filename`: the MAD-X lattice, relative to the repo root (e.g. `sim_configs/DeliveryRing/...madx`).
- `sequence_name`: the MAD-X sequence to use.
- `beam_p0c_eV`: reference momentum × c in eV, used if the lattice defines no beam (default: Mu2e Delivery Ring protons, 8.89 GeV).
- `rel_range`, `zero_half_range`: how the variable bounds are derived (above).
- `bpm_name_pattern`: a case-insensitive regex to narrow which monitors count as BPMs.
- `twiss_init`: starting optics for a transfer line (`betx`, `alfx`, `bety`, `alfy`, optionally dispersion and centroid), as a mapping. Leave empty for a ring.
- `setpoints`: targets for `-SETPOINT` observables, e.g. `{qx: 9.65, qy: 9.74}`. Any observable not listed aims at its design value.
- `machine_errors`: makes the machine imperfect, `{name: value}` applied once at load: lattice variables (a fudge factor `f_dq303: 1.02`) or element attributes (a quad offset `q_dq303.shift_x: 0.0002`, in m). Targets stay at the design.
- `truth_errors`: the same form, for a hidden copy of the machine that plays the real one in model fitting (`orm_rms`). The optimizer never touches it.
- `extra_observables`: computed or element observables to offer besides the deduced ones, e.g. `[rms(x@^p_dhp), orm_rms]`. The GUI loads a template only if every objective, constraint, and observable it names is offered, so a template lists its computed names here.
- `orm_correctors`, `orm_kick`: the correctors used for the orbit response (a regex; default the DR trims `^i_d[hv]t`) and the change applied to each (default 0.1 A).
- `debug`: print details of each step to the terminal.

## Notes

- The first load of a large lattice takes several seconds; the deduced variables are cached beside the lattice (`.varcache.json`). Delete that file to force a fresh deduction.
- Changing a main bend angle moves neither orbit nor tune in this model; steer with corrector kicks.
- The Delivery Ring lattice defines the quad stand variables `LH_DQ*`, `LV_DQ*`, but nothing uses them; move a quad with `<quad>.shift_x` or `shift_y` instead.
