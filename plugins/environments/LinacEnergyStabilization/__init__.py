from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "LinacEnergyStabilization"
    variables = {
        "L:V5QSET": [ -34., -32.],
        "L:CDPHAS,L:LDPADJ": [90., 360.]
        #"(L:CDPHAS,L:LDPADJ)": [],
    }
    observables = [
        "B:400DFT",
        "B:400DF2",
        #"SumSq B:400DFTs"
    ]
    sample_event: str='E,15,E,0'
    settings_role: str='testing'
    PID_disables: str='L:KDPHGN'
    #regulate_point_DFT: float=
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_values(variable_names, self.sample_event) # Interface LinacEnergyStabilization handles (read,set) pairs. 

    def set_variables(self, variable_inputs: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        set_dict = {}
        for k in variable_inputs.keys():
            set_dict[f'{k}.SETTING'] = variable_inputs[k]
        self.interface.set_values(set_dict, settings_role=self.settings_role)

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        # return self.interface.get_values(observable_names)
        observable_outputs = {}
        for obs in observable_names:
            value = self.interface.get_value(obs)
            observable_outputs[obs] = value
        return observable_outputs







