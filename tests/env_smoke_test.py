"""Offline smoke test of a Pacsys environment: pacsys's FakeBackend stands in for
ACNET, so nothing is read from or written to a real device.

For each environment: read a few plain variables, set one to its low hard limit
(checking the value written), and read a few plain observables. Mults, read/set pairs, arrays
and computed observables need their own test (see tests/mults_test.py,
tests/periodic_phase_test.py, tests/env_fixes_test.py).

Run from the repo root:
    pixi run python tests/env_smoke_test.py                          # every Pacsys environment
    pixi run python tests/env_smoke_test.py 01_Linac_MyTask_Pacsys   # just yours
"""
import contextlib
import importlib
import io
import sys
from pathlib import Path

sys.path.insert(0, "plugins")
from pacsys.testing import FakeBackend  # noqa: E402
from interfaces.BasicPacsysInterface import Interface  # noqa: E402


def plain(name):  # an ordinary device name: no pair, mult, array, reduction or -SETPOINT
    return name[1:2] == ":" and not any(c in name for c in ",[|") and "-SETPOINT" not in name


def smoke(env_name):
    E = importlib.import_module(f"environments.{env_name}").Environment
    env = E(interface=Interface(), settings_role="testing")  # any role: the fake accepts it
    fb = env.interface._backend_override = FakeBackend()
    env.interface._timeout = 1.0

    variables = [v for v in E.variables if plain(v)]
    for dev in variables:  # all of them: a BulkPS clip reads the other members
        lo, hi = E.variables[dev]
        fb.set_reading(f"{dev}.SETTING", (lo + hi) / 2)  # start mid-range; an environment
        fb.set_reading(f"{dev}@i", (lo + hi) / 2)        # may read either the setting or the reading
    variables = variables[:3]
    observables = [o for o in E.observables if plain(o)][:3]
    events = getattr(env, "sample_events", {})
    for dev in observables:
        event = events.get(dev, events.get("default", "@i"))  # the interface's default
        fb.set_reading(dev + event, 1.0)  # keyed by the DRF read, event included

    with contextlib.redirect_stdout(io.StringIO()):
        if variables:
            got = env.get_variables(variables)
            assert sorted(got) == sorted(variables), got
            lo = E.variables[variables[0]][0]
            env.set_variables({variables[0]: lo})
            written = fb.get_written_value(f"{variables[0]}.SETTING")
            assert written == lo, (variables[0], written, lo)
        if observables:
            got = env.get_observables(list(observables))
            assert got == {o: 1.0 for o in observables}, got
    print(f"ok    {env_name}  ({len(variables)} vars, {len(observables)} obs)")


names = sys.argv[1:] or sorted(p.parent.name for p in Path("plugins/environments").glob("*/configs.yaml")
                               if "BasicPacsysInterface" in p.read_text())
for n in names:
    smoke(n)
print("ENV SMOKE TEST PASSED")
