from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "LinacEnergyStabilization"
    variables = {
        "L:V5QSET": [ -38., -32.],
        "L:CDPHAS,L:LDPADJ,tol2@0.1": [0., 360.]
        #"L:400DFT": [-1,1],
        #"(L:CDPHAS,L:LDPADJ)": [],
    }
    observables = [
        "B:400DFT",
        "B:400DFT-SETPOINT",
        "B:400DF2",
        "B:400DF2-SETPOINT",
        "DummySumSq"
    ]
    sample_event: str='E,15,E,0'
    settings_role: str='testing' #'nosettings'
    debug: bool=False
    setpoint: str='-0.09'
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('LinacEnergyStabilization asking for variables:', variable_names)
        return self.interface.get_values(variable_names, self.sample_event) # Interface LinacEnergyStabilization handles (read,set) pairs and optional tolerances.

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            if self.debug: print ("not self.interface: {self.interface}.")
            raise BadgerNoInterfaceError
        self.interface.set_values(settable_devices, settings_role=self.settings_role)

    def get_observables(self, observable_names: list[str], sample_event=sample_event) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug or True: print ('get_observables() will ask for values of ', observable_names)
        return self.interface.get_values(observable_names, sample_event=sample_event, setpoint_str=self.setpoint)







