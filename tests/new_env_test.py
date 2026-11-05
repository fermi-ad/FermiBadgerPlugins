"""Check scripts/new_env.py (`pixi run new-env`): it copies the archetype (or another
environment) and its template, renamed and read only, strips the archetype-only blocks,
and refuses a bad name or an existing target.

ponytail: writes into the real plugins/ and tuning_templates/ trees (the lint and
smoke tests read from there); the finally block removes them, a hard crash may not.

Run from the repo root:
    pixi run python tests/new_env_test.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

NEW = '01_Linac_ZzNewEnvTest_Pacsys'
ENV, TEMPLATE = Path(f'plugins/environments/{NEW}'), Path(f'tuning_templates/development/{NEW}.yaml')
TEST = Path(f'tests/{NEW}_test.py')  # made only from the archetype


def run(*args):
    return subprocess.run([sys.executable, 'scripts/new_env.py', *args], capture_output=True, text=True)


assert not (ENV.exists() or TEMPLATE.exists() or TEST.exists()), 'leftovers from an earlier run: remove them'
try:
    for bad in ('1_Linac_X_Pacsys', '42_Linac_X_Pacsys', '01_Linac_X_Acsys'):
        r = run(bad)
        assert r.returncode and 'does not follow' in r.stderr, (bad, r.stderr)
    assert not ENV.exists()

    for src in ('01_Linac_RIL_tuning_Pacsys', '01_Linac_EnergyStabilization_Pacsys'):
        r = run(NEW, '--from', src, '--no-check')
        assert r.returncode == 0, r.stderr
        init, cfg, tpl = (ENV / '__init__.py').read_text(), (ENV / 'configs.yaml').read_text(), TEMPLATE.read_text()
        assert f'name = "{NEW}"' in init and f'name: "{NEW}"' in cfg, src
        assert "settings_role: str = 'nosettings'" in init.replace('  ', ' '), src
        assert f'  name: {NEW}\n' in tpl and f'\nname: {NEW}\n' in tpl, src
        assert 'settings_role: nosettings' in tpl and src not in tpl + init + cfg, src
        assert not (ENV / '__pycache__').exists()
        assert not TEST.exists(), 'a feature test is copied only from the archetype'

        r = run(NEW, '--from', src, '--no-check')  # never overwrites
        assert r.returncode and 'already exists' in r.stderr, r.stderr
        shutil.rmtree(ENV)
        TEMPLATE.unlink()

    # The default source, the archetype, with the lint and smoke checks: its never-write
    # guard and archetype notes are stripped, so the copy can be given a real role.
    r = run(NEW)
    assert r.returncode == 0 and 'ENV SMOKE TEST PASSED' in r.stdout, r.stdout[-2000:] + r.stderr
    assert 'from ZZ_Archetype_Pacsys' in r.stdout and 'never writes' not in r.stdout, r.stdout
    assert f'{NEW} TEST PASSED' in r.stdout, r.stdout[-2000:]  # its copy of the feature test
    for f in (ENV / '__init__.py', ENV / 'README.md', TEMPLATE, TEST):
        text = f.read_text()
        assert not any(w in text for w in ('ARCHETYPE', 'field_validator', 'ValidationError', 'archetype_test', '\n\n\n\n')), f
    check = ("import sys; sys.path.insert(0, 'plugins'); import importlib; "
             f"E = importlib.import_module('environments.{NEW}').Environment; "
             "assert E(settings_role='testing').settings_role == 'testing'")
    assert subprocess.run([sys.executable, '-c', check]).returncode == 0, 'copy still refuses a role'
finally:
    shutil.rmtree(ENV, ignore_errors=True)
    TEMPLATE.unlink(missing_ok=True)
    TEST.unlink(missing_ok=True)
print('NEW ENV TEST PASSED')
