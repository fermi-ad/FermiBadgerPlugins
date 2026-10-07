"""Headless lint for every tuning template, mirroring what Badger's GUI does
when you load one (badger/gui/components/routine_page.py:set_options_from_template)
so a broken template fails here instead of as a dialog box in the control room.

Run from the repo root:
    python tests/template_lint_test.py
"""
import glob
import os
import re
import sys

import yaml
from badger.gui.utils import filter_generator_config
from xopt import VOCS

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENVS = set(os.listdir(os.path.join(REPO, 'plugins', 'environments')))
# Every key set_options_from_template reads unconditionally.
REQUIRED = ['name', 'description', 'relative_to_current', 'generator',
            'environment', 'vrange_limit_options', 'initial_point_actions',
            'critical_constraint_names', 'vocs']

failures = []
for path in sorted(glob.glob(os.path.join(REPO, 'tuning_templates', '**', '*.yaml'), recursive=True)):
    fname = os.path.basename(path)
    try:
        t = yaml.safe_load(open(path))
        missing = [k for k in REQUIRED if k not in t]
        assert not missing, f'missing keys {missing}'
        assert 'params' in t['environment'], 'missing environment.params'
        env = t['environment']['name']
        assert env in ENVS, f'environment {env!r} is not in plugins/environments'
        vocs = VOCS(variables=t['vocs']['variables'], objectives=t['vocs']['objectives'],
                    constraints=t['vocs']['constraints'], constants={},
                    observables=t['vocs']['observables'])
        filter_generator_config(t['generator']['name'], t['generator'])
        # README "For Developers": <region>_<task>_<env core>[_Acsys|_Pacsys].yaml,
        # or just <env>.yaml. Core = env name minus region prefix and suffix.
        if t['relative_to_current']:
            # Windows are built around the live readback per variable (calc_auto_bounds):
            # idx 1 = +-ratio_full/2 of hard range, idx 2 = +-delta in engineering units.
            # A variable missing here silently falls back to idx 0 (ratio of current
            # value), which collapses to zero width when the readback is 0.0.
            opts = t['vrange_limit_options']
            bad = [v for v in vocs.variables if opts.get(v, {}).get('limit_option_idx', 0) == 0]
            assert not bad, f'variables on unsafe limit_option_idx 0 (or missing): {bad}'
        if fname != f'{env}.yaml':
            r1, r2, core = env.split('_', 2)
            suffix = next((s for s in ('_Acsys', '_Pacsys') if core.endswith(s)), '')
            core = core.removesuffix(suffix)
            # Templates under simulation/ drop the region prefix: the directory says it.
            # Top-level (operations) templates drop the interface suffix: operators need not know it.
            tier = os.path.basename(os.path.dirname(path))
            region = '' if tier == 'simulation' else f'{r1}_{r2}_'
            if tier == 'tuning_templates':
                suffix = ''
            if not re.fullmatch(rf'{region}(.+_)?{core}{suffix}\.yaml', fname):
                # Advisory only: readability beats the convention when the full form is clunky.
                print(f'warn  {fname}: name does not follow {region}<task>_{core}{suffix}.yaml')
        print(f'ok    {fname}  ({len(vocs.variables)} vars, {len(vocs.objectives)} obj)')
    except Exception as e:  # noqa: BLE001 - report every template, then fail once
        failures.append(fname)
        print(f'FAIL  {fname}: {e}')

print(f'\n{len(failures)} failing template(s)')
sys.exit(1 if failures else 0)
