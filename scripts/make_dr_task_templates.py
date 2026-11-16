"""Writes the Delivery Ring task templates in tuning_templates/simulation/ (2026-11-16):

    DR_OrbitH, DR_OrbitV, DR_Chromaticity, DR_LatticeFunctions, DR_ModelFit

Each template's machine errors, knobs, windows, and limits were chosen by checking that a
solution exists (scipy least squares over the same knobs) and that a closed-loop run
improves (scripts/sim_closed_loop.py); the numbers quoted in each description come from
those checks. Rerun after editing a choice here, then rerun those checks.

Run from the repo root:
    pixi run python scripts/make_dr_task_templates.py
"""
import copy, importlib, math, logging, sys, yaml
logging.disable(logging.WARNING)
sys.path.insert(0, 'plugins')
va = importlib.import_module('environments.99_Sim_VirtualAccelerator_MADXSuite')
from interfaces.VirtualAccelerator_MADXSuiteInterface import Interface
LAT = 'sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx'
base = yaml.safe_load(open('tuning_templates/simulation/DR_BetatronTunes_sim_VirtualAccelerator_MADXSuite.yaml'))
env = va.Environment(interface=Interface(), lattice_filename=LAT, zero_half_range=3.0)
bounds = dict(va.Environment.variables)
deduced = set(va.Environment.observables)  # offered by every DR environment
STRAIGHTS = '^p_d[hv]p[1-6]0[1-7]$'
def _str(dumper, text):  # multi-line text as a readable block
    return dumper.represent_scalar('tag:yaml.org,2002:str', text, style='|' if '\n' in text else None)
yaml.SafeDumper.add_representer(str, _str)
STABLE = {'optics_stable': {'type': 'GreaterThanConstraint', 'value': 0.5}}

def window(v, frac=None):
    """The template's range: within the hard limits, rounded inward to 6 decimals; frac
    narrows it to +-frac of the design value (the middle of the hard limits)."""
    lo, hi = bounds[v]
    if frac is not None:
        mid = (lo + hi) / 2
        lo, hi = max(lo, mid * (1 - frac)), min(hi, mid * (1 + frac))
    return [math.ceil(lo * 1e6) / 1e6, math.floor(hi * 1e6) / 1e6]


def template(name, description, variables, objective, constraints=None, params=None, observables=None,
             fractions=None):
    t = {k: copy.deepcopy(base[k]) for k in ('badger_version', 'generator', 'initial_point_actions', 'xopt_version')}
    t['generator'].pop('vocs', None)
    t.update({
        'name': f'DR_{name}_sim', 'description': description + '\n', 'relative_to_current': False,
        'critical_constraint_names': [], 'formulas': {}, 'constraint_formulas': {}, 'observable_formulas': {},
        'vrange_hard_limit': {}, 'vrange_limit_options': {}, 'additional_variables': [],
        'environment': {'name': '99_Sim_VirtualAccelerator_MADXSuite', 'params': {
            'beam_p0c_eV': 8889999999.0, 'debug': False, 'lattice_filename': LAT, 'rel_range': 0.1,
            'sequence_name': 'full', 'zero_half_range': 3.0, **(params or {})}},
        'vocs': {
            'variables': {v: window(v, (fractions or {}).get(v)) for v in variables},
            'objectives': {objective: {'type': 'MinimizeObjective'}},
            'constraints': {**STABLE, **(constraints or {})},
            'observables': {o: {'type': 'Observable'} for o in (observables or [])},
            'constants': {}}})
    named = [*t['vocs']['objectives'], *t['vocs']['constraints'], *t['vocs']['observables']]
    extras = [n for n in named if n not in deduced]  # the GUI offers only what is advertised
    if extras:
        t['environment']['params']['extra_observables'] = extras
    path = f'tuning_templates/simulation/DR_{name}_sim_VirtualAccelerator_MADXSuite.yaml'
    with open(path, 'w') as f:
        yaml.safe_dump(t, f, sort_keys=False, width=100)
    print('wrote', path)

ORBIT_ERRORS = {'q_dq303.shift_x': 2e-4, 'q_dq215.shift_x': -3e-4, 'q_dq418.shift_x': 2.5e-4, 'q_dq511.shift_x': -2e-4,
                'q_dq306.shift_y': 2e-4, 'q_dq212.shift_y': -2.5e-4, 'q_dq410.shift_y': 3e-4, 'q_dq608.shift_y': -2e-4}
for plane, trims, reading, other in (('H', 'i_dht', 'rms(x@^p_dhp)', 'rms(y@^p_dvp)'), ('V', 'i_dvt', 'rms(y@^p_dvp)', 'rms(x@^p_dhp)')):
    knobs = sorted(v for v in bounds if v.startswith(trims))
    word = {'H': 'horizontal', 'V': 'vertical'}[plane]
    template(f'Orbit{plane}', (
        f'Goal: flatten the {word} closed orbit (base orbit) with the {word} trim dipoles.\n'
        f'Objective: {reading} MINIMIZE, the RMS orbit at the {word} BPMs (m).\n'
        f'Variables: the {len(knobs)} {word} trims {trims}*, -3 to 3 A.\n'
        'Machine errors: eight quads offset 0.2-0.3 mm (shift_x, shift_y), giving 0.62 mm (x) and 1.27 mm (y)\n'
        '  RMS orbit. The trims cannot cancel quad offsets exactly: least squares reaches 0.21 mm (x),\n'
        '  0.25 mm (y), with trims within 2.6 A.\n'
        'Notes: the movable quad stands (LH_DQ*, LV_DQ*) are defined in this lattice but drive nothing,\n'
        '  so they are not offered. The other plane is recorded as an observable.'),
        knobs, reading, params={'machine_errors': ORBIT_ERRORS}, observables=[other])

CHROM_ERRORS = {'f_dsf110': 1.08, 'f_dsf215': 1.06, 'f_dsf313': 1.07, 'f_dsd412': 0.92, 'f_dsd517': 0.93, 'f_dsd611': 0.94}
template('Chromaticity', (
    'Goal: restore the design chromaticity with the main sextupole buses.\n'
    'Objective: sum(dqx-SETPOINT,dqy-SETPOINT) MINIMIZE, the summed squared errors from the targets\n'
    '  (design: dqx 2.05, dqy -1.53; set others in setpoints).\n'
    'Variables: i_dsexf, i_dsexd, design +-10%.\n'
    'Machine errors: six sextupole fudge factors off by 6-8%, giving dqx 2.14, dqy -1.62. Least squares\n'
    '  restores both to within 0.004.\n'
    'Notes: every point costs a chromatic twiss (about 0.11 s).'),
    ['i_dsexf', 'i_dsexd'], 'sum(dqx-SETPOINT,dqy-SETPOINT)',
    params={'machine_errors': CHROM_ERRORS}, observables=['dqx', 'dqy'])

QUAD_ERRORS = {'f_dq105': 1.02, 'f_dq213': 0.98, 'f_dq309': 1.025, 'f_dq416': 0.975, 'f_dq512': 1.02, 'f_dq607': 0.98}
LAT_KNOBS = ['i_dqf', 'i_dqss', 'i_dqd', 'i_dq404', 'i_dqs105', 'i_dqs605', 'i_dqs301', 'i_dqs505']
PHASE = 'phase_x(m0_dsx602,m0_dsx502)'
template('LatticeFunctions', (
    'Goal: restore the lattice functions after quad errors: even beta functions, no dispersion in the\n'
    '  straights, the harmonic-sextupole phase advance, and small beams at the kickers.\n'
    f'Objective: the sum of the RMS beta beat in x and y at the BPMs and the RMS dispersion (m) at the\n'
    f'  straight-section BPMs ({STRAIGHTS}: the 41 dispersion-free BPMs), MINIMIZE. Equal weights:\n'
    '  untested.\n'
    f'Constraints: {PHASE} within 3 deg of 1050 (35 x 30 deg; design 1051.8, 1048.1 with\n'
    '  these errors);\n'
    '  beta at the kickers d_dkk* (max betx < 11 m, max bety < 13.5 m; design 10.2, 12.7);\n'
    '  tunes within 0.01 of design.\n'
    'Variables: the 8 quad supplies most effective against these errors, by sensitivity (|J^T r|):\n'
    '  main buses i_dqf, i_dqd +-0.2%, i_dqss +-0.5% (1% moves qx by 0.1); i_dq404 +-3%;\n'
    '  i_dqs105, i_dqs605, i_dqs301, i_dqs505 +-10% (their hard limits). Windows from the least-\n'
    '  squares solution (bus changes under 0.4%, i_dq404 1.6%, two i_dqs at their limits).\n'
    'Machine errors: six quad fudge factors off by 2-2.5%: beta beat 7.1% (x), 3.4% (y); straight\n'
    '  dispersion 0.08 m RMS (design 0.017 m). Least squares on these knobs halves the beat but leaves\n'
    '  the straight dispersion: three erring quads (DQ309, DQ416, DQ512) have only main-bus power, and\n'
    '  the shunts of two others (I_DQS213, I_DQS607) are not among the knobs. The solution space is\n'
    '  degenerate; the knob choice suits this error set only.'),
    LAT_KNOBS,
    'sum(rms(bbetx@^p_d[hv]p),rms(bbety@^p_d[hv]p),rms(dx@' + STRAIGHTS + '))',
    constraints={f'{PHASE}-SETPOINT': {'type': 'LessThanConstraint', 'value': 9.0},
                 'max(betx@^d_dkk)': {'type': 'LessThanConstraint', 'value': 11.0},
                 'max(bety@^d_dkk)': {'type': 'LessThanConstraint', 'value': 13.5},
                 'qx-SETPOINT': {'type': 'LessThanConstraint', 'value': 1.0e-4},
                 'qy-SETPOINT': {'type': 'LessThanConstraint', 'value': 1.0e-4}},
    params={'machine_errors': QUAD_ERRORS, 'setpoints': {PHASE: 1050.0}},
    fractions={'i_dqf': 0.002, 'i_dqss': 0.005, 'i_dqd': 0.002, 'i_dq404': 0.03})

TRUTH = {'f_dq105': 1.02, 'f_dq309': 0.975, 'f_dq512': 1.015}
FIT_KNOBS = ['f_dq105', 'f_dq106', 'f_dq213', 'f_dq309', 'f_dq310', 'f_dq416', 'f_dq512', 'f_dq607']
template('ModelFit', (
    'Goal: find lattice-model errors by matching the measured orbit response.\n'
    'Objective: orm_rms MINIMIZE, the RMS difference (mm/A) between the model\'s orbit response to\n'
    '  each trim (i_dht*, i_dvt*; 0.1 A each) and the "measured" one.\n'
    'Measured: a hidden copy of the lattice with truth_errors plays the real machine: f_dq105 1.02,\n'
    '  f_dq309 0.975, f_dq512 1.015 (design 1.0136, 0.9866, 0.9993).\n'
    'Variables: 8 candidate quad fudge factors f_dq*, design +-10%, the 3 true ones among them.\n'
    'Notes: least squares recovers all three to 0.001 (orm_rms 0.0052 -> 0.0003). Each point costs\n'
    '  about 0.5 s (19 orbit solutions). A real-machine version would read a measured response\n'
    '  instead of truth_errors.'),
    FIT_KNOBS, 'orm_rms', params={'truth_errors': TRUTH})
