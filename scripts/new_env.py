"""Make a new Pacsys environment and its development template by copying a working
pair, then check both offline. Nothing is read from or written to ACNET.

    pixi run new-env 01_Linac_MyTask_Pacsys
    pixi run new-env 01_Linac_MyTask_Pacsys --from 01_Linac_EnergyStabilization_Pacsys

Creates plugins/environments/<NEW>/ and tuning_templates/development/<NEW>.yaml,
renamed throughout and read only (settings_role 'nosettings'). Never overwrites.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REGIONS = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '99']  # README naming table
NAME = re.compile(r'(\d\d)_[A-Za-z0-9]+_\w+_Pacsys')
ENVS = Path('plugins/environments')
TEMPLATES = Path('tuning_templates/development')


def sub(path, pattern, repl, flags=0):
    path.write_text(re.sub(pattern, repl, path.read_text(), flags=flags))


def source_template(env):
    """The development template named after `env`, else the first that uses it."""
    named = TEMPLATES / f'{env}.yaml'
    if named.exists():
        return named
    for p in sorted(TEMPLATES.glob('*.yaml')):
        if yaml.safe_load(p.read_text()).get('environment', {}).get('name') == env:
            return p
    sys.exit(f'no template in {TEMPLATES} uses {env}; copy one by hand.')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('new', help='<region>_<Descriptive>_Pacsys, e.g. 01_Linac_MyTask_Pacsys')
    ap.add_argument('--from', dest='src', default='01_Linac_RIL_tuning_Pacsys',
                    help='environment to copy (default: %(default)s)')
    ap.add_argument('--no-check', action='store_true', help='skip the lint and smoke tests')
    a = ap.parse_args(argv)

    m = NAME.fullmatch(a.new)
    if not m or m.group(1) not in REGIONS:
        sys.exit(f'{a.new!r} does not follow <region>_<Descriptive>_Pacsys, region one of '
                 f'{", ".join(REGIONS)} (README: "Environment and template naming convention").')
    env_dir, template = ENVS / a.new, TEMPLATES / f'{a.new}.yaml'
    src_dir = ENVS / a.src
    if not src_dir.is_dir():
        sys.exit(f'{src_dir} not found: run from the repo root, and --from an existing environment.')
    src_template = source_template(a.src)
    for p in (env_dir, template):
        if p.exists():
            sys.exit(f'{p} already exists; not overwriting.')

    shutil.copytree(src_dir, env_dir, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy(src_template, template)
    for p in [*env_dir.iterdir(), template]:
        if p.suffix in ('.py', '.yaml', '.md'):
            sub(p, re.escape(a.src), a.new)
    # Read only until the developer sets a real role, in both places it is set.
    sub(env_dir / '__init__.py', r"settings_role:(\s*)str(\s*)=.*", r"settings_role:\1str\2= 'nosettings'")
    sub(template, r'settings_role: .*', 'settings_role: nosettings')
    sub(template, r'^name: .*', f'name: {a.new}', flags=re.M)
    print(f'Made {env_dir}/ and {template} (from {a.src}; settings_role nosettings).')

    if not a.no_check:
        for test in (['tests/template_lint_test.py'], ['tests/env_smoke_test.py', a.new]):
            if subprocess.run([sys.executable, *test]).returncode:
                sys.exit(f'{test[0]} failed: fix that before editing further.')
    print(f'\nNext, edit (docs/developer-guide.md, "Quickstart"):\n'
          f'  {env_dir}/__init__.py   variables, observables, and their limits\n'
          f'  {env_dir}/README.md     what operators see under Open Docs\n'
          f'  {template}   description, environment.params, vocs')


if __name__ == '__main__':
    main()
