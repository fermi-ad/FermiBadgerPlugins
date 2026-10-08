"""Offline lint of every *_Pacsys environment's device names, no control network needed.

Builds exactly the DRFs BasicPacsysInterface would send for each variable and observable
(reading name + its sample event; <setting>.SETTING@I; pairs, tolN@T, -SETPOINT and
|<reduce> stripped the way the interface strips them) and parses each through
pacsys.testing.FakeBackend, which rejects bad fields, clock events and ranges before
any I/O. Device-name typos cannot be caught offline: ACNET names are only checked on
the wire.

Run from the repo root:
    conda run -n FermiBadger_env python tests/pacsys_drf_lint_test.py
"""
import glob
import importlib
import os
import sys

sys.path.insert(0, 'plugins')

from pacsys.testing import FakeBackend
from interfaces.BasicPacsysInterface import Interface

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {'DummySumSq'}  # interface-internal pseudo device

intf = Interface()
fb = FakeBackend()
failures = []

for path in sorted(glob.glob(os.path.join(REPO, 'plugins', 'environments', '*_Pacsys'))):
    env_name = os.path.basename(path)
    mod = importlib.import_module(f'environments.{env_name}')
    Env = mod.Environment
    sample_events = getattr(Env, 'sample_events', {}) or {}
    names = list(Env.variables) + list(Env.observables)
    drfs = []
    for name in names:
        if (name in SKIP or name.endswith('_calc') or name.startswith('SumAbs_') or name == 'W_SumLosses'
                or name.startswith('mult:') or name.startswith('MultOOB_')):
            continue
        try:
            reading = intf.extract_reading_devices([name])[0]
        except ValueError as e:  # unknown |reduce
            failures.append(f'{env_name}: {name}: {e}')
            continue
        drfs.append(reading + sample_events.get(reading, sample_events.get('default', '@i')))
        if name in Env.variables:
            drfs.append(f'{intf.extract_setting_devices([name])[0]}.SETTING@I')
            rb = intf.readback_drf(name)
            if rb: drfs.append(rb)
    bad = 0
    for drf in drfs:
        try:
            fb.get(drf)  # "No reading configured" is fine; a ValueError is a malformed DRF
        except ValueError as e:
            failures.append(f'{env_name}: {drf}: {e}')
            bad += 1
    print(f'{"FAIL" if bad else "ok  "}  {env_name}  ({len(drfs)} DRFs, {bad} malformed)')

print()
for f in failures: print('  ' + f)
assert not failures, f'{len(failures)} malformed DRF(s)'
print('PACSYS DRF LINT PASSED')
