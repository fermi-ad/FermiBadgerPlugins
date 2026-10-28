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
    sample_events: dict = {'default': '@e,15,e,0'}
    settings_role: str='testing'
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_settings(variable_names)

    def set_variables(self, variable_inputs: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        # bare names: the interface writes .SETTING itself
        self.interface.set_values(variable_inputs, settings_role=self.settings_role)

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_values(list(observable_names), sample_events=self.sample_events)







