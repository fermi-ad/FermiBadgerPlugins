"""The two load-time caches of 99_Sim_VirtualAccelerator_MADXSuite, on the Delivery Ring:

- the verified-rewrite stamp: once the ':=' rewrite of a lattice has passed its
  check, a later cold load (a new process; here the in-process caches are cleared)
  skips the check, and a changed stamp (an edited lattice, rewriter, or cpymad)
  runs it again;
- the deduced-list cache: a second environment in the same process reuses the
  deduced variables, observables, monitors, and design twiss, unless a param that
  shapes them differs.

Counts calls, not seconds. Run from the repo root:
    pixi run python tests/VA_load_caches_test.py
"""
import importlib
import json
import os
import sys

os.environ.setdefault('TQDM_DISABLE', '1')
sys.path.insert(0, 'plugins')
va = importlib.import_module('environments.99_Sim_VirtualAccelerator_MADXSuite')
from interfaces.VirtualAccelerator_MADXSuiteInterface import Interface  # noqa: E402

Env = va.Environment
LATTICE = 'sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx'
calls = {'_verify_rewrite': 0, '_deduce_observables': 0}
for name in calls:
    orig = getattr(Env, name)

    def counted(*a, _orig=orig, _name=name, **kw):
        calls[_name] += 1
        return _orig(*a, **kw)
    setattr(Env, name, staticmethod(counted) if isinstance(Env.__dict__[name], staticmethod) else counted)


def cold(**params):
    """A load as a new process sees it: no in-process caches."""
    va._LATTICE_CACHE.clear()
    va._DEDUCED_CACHE.clear()
    env = Env(interface=Interface(), lattice_filename=LATTICE, **params)
    env._ensure_lattice()
    return env


stamp_path = va.Path(LATTICE).resolve().with_name(va.Path(LATTICE).name + va.VERIFIED_SUFFIX)
stamp_path.unlink(missing_ok=True)

# --- verified-rewrite stamp
env1 = cold()
assert env1._use_deferred and calls['_verify_rewrite'] == 1, calls
assert stamp_path.is_file(), 'a passed check was not recorded'
qx1 = env1.get_observables(['qx'])['qx']

env2 = cold()
assert calls['_verify_rewrite'] == 1, 'the check ran again on an unchanged lattice'
assert env2._use_deferred and env2.get_observables(['qx'])['qx'] == qx1

stamp = json.loads(stamp_path.read_text())
stamp_path.write_text(json.dumps({**stamp, 'sha1': 'an edited lattice'}))
cold()
assert calls['_verify_rewrite'] == 2, 'a changed stamp did not run the check'
assert json.loads(stamp_path.read_text()) == stamp, 'the passed check was not re-recorded'
print('verified-rewrite stamp: skips an unchanged lattice, rechecks a changed one: ok')

# --- deduced-list cache (same process)
n = calls['_deduce_observables']
env3 = Env(interface=Interface(), lattice_filename=LATTICE)
env3._ensure_lattice()
assert calls['_deduce_observables'] == n, 'a second environment deduced the lists again'
assert env3._monitor_planes == env1._monitor_planes and env3._monitor_planes is not env1._monitor_planes
assert 'qx' in Env.observables and 'i_dqd' in Env.variables
env3.set_variables({'i_dqd': Env.variables['i_dqd'][0]})  # moving one copy...
assert env3.get_observables(['qx'])['qx'] != qx1
env4 = Env(interface=Interface(), lattice_filename=LATTICE)  # ...leaves the next at design
env4._ensure_lattice()
assert env4.get_observables(['qx'])['qx'] == qx1, 'the shared design twiss was disturbed'

Env(interface=Interface(), lattice_filename=LATTICE, bpm_name_pattern='^p_d[hv]p')._ensure_lattice()
assert calls['_deduce_observables'] == n + 1, 'a different monitor pattern reused the old lists'
print('deduced-list cache: reused in-process, separate per param set: ok')
print('VA LOAD CACHES TEST PASSED')
