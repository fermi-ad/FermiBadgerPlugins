from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "LinacEnergyStabilization"
    variables = {
        "L:V5QSET": [ -38., -32.],
        "L:CDPHAS,L:LDPADJ,tol2@0.1": [0., 360.],
        "L:C7PHAS,L:L7PADJ,tol3@0.45": [0., 360.],
    }
    observables = [
        "B:400DFT",
        "B:400DFT-SETPOINT",
        "B:400DF2",
        "B:400DF2-SETPOINT",
        "DummySumSq"
    ]
    sample_event:  str = 'E,15,E,0'
    settings_role: str = 'nosettings'
    debug:         bool= False
    setpoint:      str = 'hold'
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('LinacEnergyStabilization asking for variables:', variable_names)
        # Interface LinacEnergyStabilization handles (read,set) pairs and optional tolerances.
        return self.interface.get_values(variable_names, sample_event=self.sample_event, debug=self.debug) 

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            if self.debug: print ("not self.interface: {self.interface}.")
            raise BadgerNoInterfaceError
        self.interface.set_values(settable_devices, settings_role=self.settings_role, debug=self.debug)

    #def get_observables(self, observable_names: list[str], sample_event=sample_event) -> dict:
    def get_observables(self, observable_names: list[str]) -> dict:        
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug or True: print ('get_observables() will ask for values of ', observable_names)
        return self.interface.get_values(observable_names, sample_event=self.sample_event, setpoint_str=self.setpoint, debug=self.debug)







