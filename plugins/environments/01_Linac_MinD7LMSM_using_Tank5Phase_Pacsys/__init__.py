from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "01_Linac_MinD7LMSM_using_Tank5Phase_Pacsys"
    variables = {
        "L:V5QSET": [ -34., -32.]
    }
    observables = [
        "L:D7LMSM",
    ]
    sample_event: str='E,15,E,0'
    settings_role: str='testing'
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_values(variable_names, self.sample_event)

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
        return {obs: self.interface.get_value(obs) for obs in observable_names}







