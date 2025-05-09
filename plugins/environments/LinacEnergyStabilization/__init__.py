from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "LinacEnergyStabilization"
    variables = {
        "L:V5QSET": [ -38., -32.],
        "L:CDPHAS,L:LDPADJ,tol2@0.0001": [90., 360.],
        "L:400DFT": [-1,1],
        #"(L:CDPHAS,L:LDPADJ)": [],
    }
    observables = [
        "B:400DFT",
        "B:400DF2",
        "DummySumSq"
    ]
    sample_event: str='E,15,E,0'
    settings_role: str='testing' #'nosettings'
    PID_disables: str='L:KDPHGN'
    debug: bool=False
    #regulate_point_DFT: float=
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('LinacEnergyStabilization asking for variables:', variable_names)
        return self.interface.get_values(variable_names, self.sample_event) # Interface LinacEnergyStabilization handles (read,set) pairs and optional tolerances.

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            if self.debug: print ("not self.interface: {self.interface}.")
            raise BadgerNoInterfaceError
        #set_dict = {}
        #for k in variable_inputs.keys():
        #    set_dict[f'{k}.SETTING'] = variable_inputs[k] # JMSJ is this really always the right diction? If so it should move to the Interface.
        #self.interface.set_values(set_dict, settings_role=self.settings_role)
        self.interface.set_values(settable_devices, settings_role=self.settings_role)

    def get_observables(self, observable_names: list[str], sample_event=sample_event) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('get_observables() will ask for values of ', observable_names)
        return self.interface.get_values(observable_names, sample_event=sample_event)
        # observable_outputs = {}
        # for obs in observable_names:
        #     if self.debug: print (f'get_observables)_ will get value for {obs}')
        #     if obs == 'DummySumSq': value = 23.
        #     else: value = self.interface.get_value(obs)
        #     observable_outputs[obs] = value
        # return observable_outputs







