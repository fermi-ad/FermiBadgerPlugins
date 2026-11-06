# ARCHETYPE-ONLY (scripts/new_env.py removes each such block from copies)
# The archetype: every feature the Pacsys environments here use, in one place, as the
# pattern `pixi run new-env <name>` copies. The device names are real (from the RIL,
# EnergyStabilization and DeliveryRing environments) so each feature reads naturally.
# Keep it complete: a feature added to any environment belongs here too, tested in
# tests/archetype_test.py.
# END ARCHETYPE-ONLY
# Each feature here is explained in docs/developer-guide.md, "Conventions in the code
# you copied". Swap the devices for yours, and delete what you don't need.
import re
from typing import Dict

import numpy as np
from badger import environment
from badger.errors import BadgerNoInterfaceError
from pydantic import AliasChoices, Field, PrivateAttr
# ARCHETYPE-ONLY
from pydantic import field_validator
# END ARCHETYPE-ONLY

from periodic import unwrap
from supply_limits import (BulkPSLimits, OBSERVABLE_PREFIX as BULK_PS_PREFIX, bulk_ps_observable,
                           bulk_ps_observables, clip_to_bulk_ps_limits)
from mults import Mult, expand_mults, is_mult, mult_name, mult_members, OOB_PREFIX

# 'READ,SET' or 'READ,SET,tolN@T': a read/set pair (see the interface)
_PAIR = re.compile(r'^.:.+,.:.+')

# Bulk power supplies: trims fed by one supply, which trips if they draw too much together.
# Either 'limit' (sum of |I|) or 'positive' and 'negative' (each sign's sum), in amps.
# Module level so the observables below can be listed from it.
_BULK_PS = {
    'SourceATrims': {'positive': 8.0, 'negative': 8.0,
                     'devices': ['L:ATRMHU', 'L:ATRMVU', 'L:ATRMHD', 'L:ATRMVD']},
    'MEBTQ1trims':  {'limit': 7.0, 'devices': ['L:MUQ1H', 'L:MUQ1V', 'L:MDQ1H', 'L:MDQ1V']},
}

# Loss monitors summed, weighted, into the computed observable W_SumLosses.
_LOSSES = {'L:D71LM': 1.0, 'L:D72LM': 1.0, 'L:D73LM': 1.0, 'L:D74LM': 1.0}

# BPM errors from their setpoints, summed into VTrajError_SumSqBPM_calc.
_TRAJ_ERRORS = ['L:D73BPV-SETPOINT', 'L:D74BPV-SETPOINT']


class Environment(environment.Environment):
    name = "ZZ_Archetype_Pacsys"
    # Variables: {name: [lo, hi]}, the hard limits. Badger never sets a value outside them.
    variables = {
        # Plain devices: Badger sets each and reads back its SETTING.
        # These four share a bulk supply (BulkPS_Limit below).
        "L:ATRMHU": [-4.0, 4.0],
        "L:ATRMVU": [-4.0, 4.0],
        "L:ATRMHD": [-4.0, 4.0],
        "L:ATRMVD": [-4.0, 4.0],
        "L:MUQ1H": [-4.0, 4.0],
        "L:MUQ1V": [-4.0, 4.0],
        "L:MDQ1H": [-4.0, 4.0],
        "L:MDQ1V": [-4.0, 4.0],
        # Mult members: plain variables too, for their own hard limits and safe-badger.
        "L:MUQ1": [250.0, 300.0],
        "L:MUQ2": [225.0, 275.0],
        # A mult: an integer step count; each member moves by coefficient * step * steps.
        "mult:MUQ": [-10, 10],
        # A periodic plain device with tight operating limits (see periodic_devices).
        "L:RFQPAH": [185.0, 225.0],
        # A settle triplet: read L:CDPHAS, set L:LDPADJ, then wait until 2 readings agree
        # within 0.1. Periodic and free-running, so declared two periods wide.
        # (A bare pair 'READ,SET' also works, but its reading is never verified.)
        "L:CDPHAS,L:LDPADJ,tol2@0.1": [0.0, 720.0],
    }
    # Observables: any of these can be an objective, a constraint, or recorded.
    observables = [
        # Plain readings
        "G:LINEFF", "L:D7TOR", "L:TK1RAD",
        "B:BOOEFF",                          # read on its own event (sample_events)
        # Squared error from a setpoint ('hold' = the first reading of the run)
        "B:400DFT-SETPOINT",
        *_TRAJ_ERRORS,                       # explicit numeric setpoints
        # An array reduced to one number by the interface: mean, rms, std, min, max, sum, absmax
        "Z:ITGSIG_1_SRS[:]|std",
        # Computed here, from readings
        "W_SumLosses",                       # weighted sum of loss monitors
        "VTrajError_SumSqBPM_calc",          # sum of the BPM errors
        "SpillDutyFactor_calc",              # from a whole array, with numpy
        # Computed from settings: each bulk supply's budget(s), and each mult's lost step
        *bulk_ps_observables(_BULK_PS),
        "MultOOB_MUQ",
    ]

    # --- Parameters: pydantic fields, edited in the GUI's Machine Interface panel and
    # overridable in a template's environment.params. Every default must be safe.
    settings_role: str = 'nosettings'
    debug: bool = False
    # {device or 'default': '@e,<event>,e,<delay>'}: when each reading is taken
    sample_events: Dict[str, str] = {'default': '@e,52,e,0', 'B:BOOEFF': '@e,1f,e,0',
                                     'Z:ITGSIG_1_SRS[:]': '@e,83,e,0',
                                     'Z:INSPLL_1_SRS[:]': '@e,83,e,0'}
    # {device or 'default': N}: the mean of N fresh events (N > 1 needs an event, not @i)
    average_events: Dict[str, int] = {'default': 1, 'L:D7TOR': 3}
    # {reading device: period} for phases, in the device's own units
    # Renamed from 'periods' 2026-11-05; the old name still loads (saved templates, past runs).
    periodic_devices: Dict[str, float] = Field({'L:RFQPAH': 360.0, 'L:CDPHAS': 360.0},
        validation_alias=AliasChoices('periodic_devices', 'periods'))
    # Targets for the -SETPOINT observables: a number, or 'hold'
    setpoints: Dict[str, float | str | None] = {'B:400DFT': 'hold',
                                                'L:D73BPV': -0.53, 'L:D74BPV': -1.7}
    BulkPS_Limit: BulkPSLimits = _BULK_PS
    # {name: {step: size, members: {DEV: coefficient}}}; variable mult:<name>
    mults: Dict[str, Mult] = {'MUQ': {'step': 0.05, 'members': {'L:MUQ1': 20.0, 'L:MUQ2': 20.0}}}
    w_sumsq: Dict[str, float] = _LOSSES
    spill_length: int = 430              # samples per spill, for SpillDutyFactor_calc

    # Run state, not parameters
    _as_found: dict = PrivateAttr(default_factory=dict)    # mult members' settings at first touch
    _mult_steps: dict = PrivateAttr(default_factory=dict)  # {mult: steps} last applied
    _mult_oob: dict = PrivateAttr(default_factory=dict)    # {mult: lost fraction} of the last step

    # ARCHETYPE-ONLY: the archetype is a pattern, never a live environment: it refuses
    # any role that could write.
    @field_validator('settings_role')
    @classmethod
    def _archetype_never_writes(cls, role):
        if role != 'nosettings':
            raise ValueError("ZZ_Archetype_Pacsys never writes: copy it with "
                             "`pixi run new-env <name>` and give the copy a role")
        return role
    # END ARCHETYPE-ONLY

    def _settings(self, names):
        return self.interface.get_settings(names, debug=self.debug)

    def _capture_as_found(self, mult_vars):
        # mult members' settings, read once per run (at the first touch of any mult)
        if mult_vars and not self._as_found:
            self._as_found = dict(self._settings(mult_members(self.mults)))

    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        mult_vars = [n for n in variable_names if is_mult(n)]
        pairs = [n for n in variable_names if _PAIR.fullmatch(n)]
        plain = [n for n in variable_names if n not in mult_vars and n not in pairs]
        self._capture_as_found(mult_vars)
        values = {n: float(self._mult_steps.get(mult_name(n), 0)) for n in mult_vars}
        if plain:   # a plain device's value is its SETTING
            values.update(self._settings(plain))
        if pairs:   # a pair's value is its live READING (the first name)
            values.update(self.interface.get_values(pairs, periods=self.periodic_devices, debug=self.debug))
        # A periodic value may arrive on another branch (-179 for 181): move it to the
        # branch nearest the middle of the hard limits.
        for name in plain + pairs:
            reading = name.split(',')[0]
            if reading in self.periodic_devices:
                lo, hi = self.variables[name]
                values[name] = unwrap(values[name], (lo + hi) / 2, self.periodic_devices[reading])
        return values

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        mult_vars = [n for n in settable_devices if is_mult(n)]
        if mult_vars:   # a mult step becomes settings of its members
            self._capture_as_found(mult_vars)
            settable_devices, steps, oob = expand_mults(settable_devices, self.mults,
                                                        self._as_found, self.variables)
            self._mult_steps.update(steps)
            self._mult_oob.update(oob)
        # Keep every bulk supply within its limit (clips the largest current toward zero)
        settable_devices = clip_to_bulk_ps_limits(settable_devices, self.BulkPS_Limit, self._settings)
        self.interface.set_values(settable_devices, settings_role=self.settings_role,
                                  periods=self.periodic_devices, debug=self.debug)

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        requested = list(observable_names)  # never change the caller's list
        computed = {'W_SumLosses', 'VTrajError_SumSqBPM_calc', 'SpillDutyFactor_calc'}
        from_settings = [n for n in requested if n.startswith((BULK_PS_PREFIX, OOB_PREFIX))]
        to_read = [n for n in requested if n not in computed and n not in from_settings]
        # add the inputs of the computed observables
        inputs = []
        if 'W_SumLosses' in requested:
            inputs += list(self.w_sumsq)
        if 'VTrajError_SumSqBPM_calc' in requested:
            inputs += _TRAJ_ERRORS
        if 'SpillDutyFactor_calc' in requested:
            inputs += ['Z:INSPLL_1_SRS[:]', 'Z:ITGSIG_1_SRS[:]']
        to_read += [n for n in inputs if n not in to_read]

        result = self.interface.get_values(to_read, sample_events=self.sample_events,
                                           setpoints=self.setpoints, periods=self.periodic_devices,
                                           average_events=self.average_events, debug=self.debug)

        if 'W_SumLosses' in requested:
            result['W_SumLosses'] = sum((w * (1.0 + result[d])) ** 2 for d, w in self.w_sumsq.items())
        if 'VTrajError_SumSqBPM_calc' in requested:
            result['VTrajError_SumSqBPM_calc'] = sum(result[n] for n in _TRAJ_ERRORS)
        if 'SpillDutyFactor_calc' in requested:
            # the spill starts at the first nonzero sample of the spill gate
            gate = np.asarray(result['Z:INSPLL_1_SRS[:]'])
            start = int(np.argmax(gate != 0))
            spill = np.asarray(result['Z:ITGSIG_1_SRS[:]'])[max(start - 1, 0):start + self.spill_length]
            result['SpillDutyFactor_calc'] = 1.0 / (1.0 + np.var(spill))
        for n in from_settings:
            if n.startswith(BULK_PS_PREFIX):
                result[n] = bulk_ps_observable(self.BulkPS_Limit, n, self._settings)
            else:
                result[n] = self._mult_oob.get(n[len(OOB_PREFIX):], 0.0)

        # only what was asked for: inputs read for a calculation would become columns
        return {n: result[n] for n in requested}
