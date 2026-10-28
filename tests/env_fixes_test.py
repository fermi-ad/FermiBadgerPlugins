"""Offline checks of three environments fixed 2026-10-28 (both twins of each, Acsys
and Pacsys), with a stub interface: no control network, no acsys/pacsys needed.

- 09_DeliveryRing_Muon_PID_tune: the Acsys twin imports (a line had lost its
  left-hand side); DR_SDF_calc reads the spill arrays it needs (it checked for
  'DR_SDF'); a spill starting at sample 0 no longer slices from the end.
- 01_Linac_AutoSteerRestore: VTrajError_SumSqBPM_calc no longer hits an
  undefined name; W_SumLosses is computed (the name was removed, then tested).
- 01_Linac_MinD7LMSM_using_Tank5Phase: uses the interfaces' current calls
  (get_settings, get_values with sample_events, bare names to set_values).
- All: the caller's list of names is left alone, and only the requested names
  come back (not the inputs read for a calculation).

Run from the repo root:
    pixi run python tests/env_fixes_test.py
"""
import importlib
import sys

import numpy as np

sys.path.insert(0, "plugins")
from badger.interface import Interface  # noqa: E402


class Stub(Interface):
    name: str = "stub"

    def model_post_init(self, _ctx):
        object.__setattr__(self, "calls", [])

    def get_values(self, names, sample_events={}, setpoints={}, **_):
        self.calls.append(("get_values", list(names), dict(sample_events)))
        out = {}
        for n in names:
            if n == "Z:INSPLL_1_SRS[:]":
                out[n] = np.array([1.0, 1, 1, 1, 0, 0, 0, 0])  # spill from sample 0
            elif n == "Z:ITGSIG_1_SRS[:]":
                out[n] = np.array([2.0, 4, 2, 4, 9, 9, 9, 9])
            elif n.endswith("-SETPOINT"):
                out[n] = 0.25  # the interface returns the squared error
            else:
                out[n] = 1.0
        return out

    def get_settings(self, names, debug=False):
        self.calls.append(("get_settings", list(names)))
        return {n: -33.0 for n in names}

    def set_values(self, values, settings_role=None, **_):
        self.calls.append(("set_values", dict(values), settings_role))


def env(name):
    return importlib.import_module(f"environments.{name}").Environment


for twin in ("Acsys", "Pacsys"):
    # --- DeliveryRing Muon PID
    E = env(f"09_DeliveryRing_Muon_PID_tune_{twin}")
    stub = Stub()
    e = E(interface=stub, spill_length=3)
    names = ["DR_SDF_calc"]
    out = e.get_observables(names)
    assert names == ["DR_SDF_calc"], names  # caller's list untouched
    assert list(out) == ["DR_SDF_calc"], out  # not the spill arrays
    read = stub.calls[-1][1]
    assert "Z:INSPLL_1_SRS[:]" in read and "Z:ITGSIG_1_SRS[:]" in read, read
    # spill begins at sample 0: samples 0..2 ([2, 4, 2]), not a wrapped slice
    assert np.isclose(out["DR_SDF_calc"], 1 / (1 + np.var([2.0, 4, 2]))), out

    # --- AutoSteerRestore
    E = env(f"01_Linac_AutoSteerRestore_{twin}")
    stub = Stub()
    e = E(interface=stub)
    names = ["W_SumLosses", "VTrajError_SumSqBPM_calc", "L:D73BPV-SETPOINT", "B:VPQ2-SETPOINT"]
    out = e.get_observables(names)
    assert names == ["W_SumLosses", "VTrajError_SumSqBPM_calc", "L:D73BPV-SETPOINT", "B:VPQ2-SETPOINT"]
    assert sorted(out) == sorted(names), sorted(out)  # not the loss monitors
    assert out["VTrajError_SumSqBPM_calc"] == 0.5, out  # 0.25 + 0.25
    n_losses = len(e.w_sumsq)
    assert np.isclose(out["W_SumLosses"], n_losses * (1.0 * (1 + 1.0)) ** 2), out
    assert len(set(e.setpoints)) == len(e.setpoints)

    # --- MinD7LMSM
    E = env(f"01_Linac_MinD7LMSM_using_Tank5Phase_{twin}")
    stub = Stub()
    e = E(interface=stub)
    assert e.get_variables(["L:V5QSET"]) == {"L:V5QSET": -33.0}
    assert stub.calls[-1] == ("get_settings", ["L:V5QSET"])
    e.set_variables({"L:V5QSET": -33.5})
    assert stub.calls[-1] == ("set_values", {"L:V5QSET": -33.5}, "testing"), stub.calls[-1]
    names = ["L:D7LMSM"]
    assert e.get_observables(names) == {"L:D7LMSM": 1.0} and names == ["L:D7LMSM"]
    assert stub.calls[-1] == ("get_values", ["L:D7LMSM"], {"default": "@e,15,e,0"}), stub.calls[-1]

print("ENV FIXES TEST PASSED")
