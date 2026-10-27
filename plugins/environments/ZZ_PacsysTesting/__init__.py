"""Harmless live-network exercise for BasicPacsysInterface.

G:AMANDA, Z:CUBE_X, Z:CUBE_Y, Z:CUBE_Z are Fermilab ACNET test/scratch
devices with no real hardware behind them -- safe to vary freely. This
environment's only purpose is to put a real Kerberos-authenticated
pacsys write, and a real pacsys read, on the wire (see
memory/basic-pacsys-interface-port.md: that was the one thing the port
couldn't verify offline).
"""
import numpy as np
from badger import environment
from badger.errors import BadgerNoInterfaceError

_RAW_DEVICES = ("G:AMANDA", "Z:CUBE_X", "Z:CUBE_Y", "Z:CUBE_Z")
_DERIVED = ("AbsProduct", "CombineObjective", "TwoWells")
# Nonzero offset so each (value - offset)**2 curve bottoms out away from
# value=0, rather than right at it.
_SQ_OFFSET = 0.5
_SQ_NAMES = {f"{dev.split(':')[1]}_sq": dev for dev in _RAW_DEVICES}
# {'AMANDA_sq': 'G:AMANDA', 'CUBE_X_sq': 'Z:CUBE_X', 'CUBE_Y_sq': 'Z:CUBE_Y', 'CUBE_Z_sq': 'Z:CUBE_Z'}

# TwoWells: a demonstration objective over all four devices (minimize). A tilted
# bowl (the cross terms of _TW_A couple the knobs: the best value of one depends
# on the others), with a deep well at _TW_BEST (-6.0, the global minimum) and a
# shallower decoy at _TW_DECOY (about -3.06), so a run started anywhere in
# [-10, 10]^4 has somewhere to go and something to explore. Order: G:AMANDA,
# Z:CUBE_X, Z:CUBE_Y, Z:CUBE_Z.
_TW_BEST = np.array([3.0, -4.0, 2.0, 5.0])
_TW_DECOY = np.array([-6.0, 5.0, -5.0, -3.0])
_TW_A = np.array([
    [1.0, 0.6, 0.0, 0.0],
    [0.6, 1.0, 0.3, 0.0],
    [0.0, 0.3, 1.0, -0.4],
    [0.0, 0.0, -0.4, 1.0],
])


def two_wells(x):
    """The TwoWells objective at device values x (in _RAW_DEVICES order)."""
    d = np.asarray(x, dtype=float) - _TW_BEST
    e = np.asarray(x, dtype=float) - _TW_DECOY
    return float(
        0.01 * d @ _TW_A @ d
        - 6.0 * np.exp(-(d @ d) / (2 * 2.5**2))
        - 4.0 * np.exp(-(e @ e) / (2 * 2.0**2))
    )


class Environment(environment.Environment):
    name = "ZZ_PacsysTesting"
    # Generous placeholder hard bounds -- these are scratch devices with no
    # physical safety limit to respect, unlike real accelerator hardware.
    variables = {
        "G:AMANDA": [-100.0, 100.0],
        "Z:CUBE_X": [-100.0, 100.0],
        "Z:CUBE_Y": [-100.0, 100.0],
        "Z:CUBE_Z": [-100.0, 100.0],
    }
    observables = [
        "G:AMANDA",
        "Z:CUBE_X",
        "Z:CUBE_Y",
        "Z:CUBE_Z",
        "AbsProduct",        # |G:AMANDA * Z:CUBE_X * Z:CUBE_Y * Z:CUBE_Z|
        "CombineObjective",  # sign(G:AMANDA) * Z:CUBE_X * Z:CUBE_Y * Z:CUBE_Z
        "TwoWells",          # demo objective: global min -6 at (3, -4, 2, 5), a decoy
        *_SQ_NAMES,          # (device - _SQ_OFFSET)**2, one per variable
    ]
    settings_role: str = 'testing'
    debug: bool = False

    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_settings(variable_names, debug=self.debug)

    def set_variables(self, variable_inputs: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        self.interface.set_values(variable_inputs, settings_role=self.settings_role, debug=self.debug)

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        derived = [n for n in observable_names if n in _DERIVED or n in _SQ_NAMES]
        # Fetch the raw devices needed to compute any requested derived
        # observable, plus whichever raw devices were directly requested.
        raw_needed = [n for n in observable_names if n not in derived]
        if derived:
            raw_needed += [d for d in _RAW_DEVICES if d not in raw_needed]

        result = self.interface.get_values(raw_needed, debug=self.debug)

        if 'AbsProduct' in derived:
            result['AbsProduct'] = abs(
                result['G:AMANDA'] * result['Z:CUBE_X'] * result['Z:CUBE_Y'] * result['Z:CUBE_Z']
            )
        if 'CombineObjective' in derived:
            result['CombineObjective'] = (
                np.sign(result['G:AMANDA']) * result['Z:CUBE_X'] * result['Z:CUBE_Y'] * result['Z:CUBE_Z']
            )
        if 'TwoWells' in derived:
            result['TwoWells'] = two_wells([result[d] for d in _RAW_DEVICES])
        for name, dev in _SQ_NAMES.items():
            if name in derived:
                result[name] = (result[dev] - _SQ_OFFSET) ** 2

        # Drop raw values that were only fetched to feed a derived observable,
        # not actually requested.
        for dev in _RAW_DEVICES:
            if dev not in observable_names and dev in result:
                del result[dev]
        return result
