from typing import Dict
from badger import environment
from badger.errors import BadgerNoInterfaceError
from periodic import unwrap

class Environment(environment.Environment):
    name = "01_Linac_EnergyStabilization_Pacsys"
    # The phase settings are periodic: L:LDPADJ at x and at x + 360 are the same
    # physics, and the device accepts settings past the wrap. Their bounds are
    # declared two periods wide so Badger's set_variables bounds check and the
    # GUI's window clipping never bite at the wrap; get_variables keeps the
    # current value near the middle of that range.
    variables = {
        "L:V5QSET": [-38., -32.],
        "L:CDPHAS,L:LDPADJ,tol2@0.1": [0., 720.],
        "L:C7PHAS,L:L7PADJ,tol3@0.45": [0., 720.],
    }
    observables = [
        "B:400DFT",
        "B:400DFT-SETPOINT",
        "B:400DF2",
        "B:400DF2-SETPOINT",
        "DummySumSq",
    ]
    sample_events: Dict[str, str] = {'default': '@e,15,e,0'}
    # 'hold' regulates to the first readback of the run; a number is an explicit target.
    setpoints:     Dict[str, float | str | None] = {'defaults': None, 'B:400DFT': 'hold', 'B:400DF2': 'hold'}
    # {reading device: period} for phase-like devices, in the device's own units.
    periods:       Dict[str, float] = {'L:CDPHAS': 360.0, 'L:C7PHAS': 360.0}
    settings_role: str = 'nosettings'
    debug:         bool = False

    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        # The current value of a read/set pair is its live reading (L:CDPHAS for
        # L:LDPADJ). A periodic reading arrives wrapped into one period; move it
        # onto the branch nearest the middle of the declared bounds so a window
        # around it never straddles a bound.
        values = self.interface.get_values(variable_names, periods=self.periods, debug=self.debug)
        for name in variable_names:
            reading = self.interface.extract_reading_devices([name])[0]
            if reading in self.periods:
                lo, hi = self.variables[name]
                values[name] = unwrap(values[name], (lo + hi) / 2, self.periods[reading])
        return values

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        self.interface.set_values(settable_devices, settings_role=self.settings_role,
                                  periods=self.periods, debug=self.debug)

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_values(observable_names, sample_events=self.sample_events,
                                         setpoints=self.setpoints, periods=self.periods,
                                         debug=self.debug)
