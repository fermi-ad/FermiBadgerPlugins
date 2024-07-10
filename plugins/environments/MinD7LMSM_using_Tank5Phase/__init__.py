from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "MinD7LMSM_using_Tank5Phase"
    variables = {
        "Z:CUBE_X": [ -1.0, 1.0],
        "Z:CUBE_Y": [  0.0, 1.0],
        "L:V5QSET": [ -34.51, -32.51]
    }
    observables = [
        # "Z:CUBE_X",
        # "Z:CUBE_Y",
        "L:D7LMSM",
        "Z:CUBE_Z",
        "G:AMANDA"
    ]
    sample_event: str='E,15,E,0'
    settings_role: str='fake'
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_values(variable_names, self.sample_event)

    def set_variables(self, variable_inputs: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        self.interface.set_values(variable_inputs, settings_role=self.settings_role)

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        # return self.interface.get_values(observable_names)
        observable_outputs = {}
        for obs in observable_names:
            if obs == 'Z:CUBE_Z':
                value = self.interface.get_value('Z:CUBE_X', sample_event=self.sample_event)**2 + self.interface.get_value('Z:CUBE_Y', sample_event=self.sample_event)**2
                self.interface.set_values({'Z:CUBE_Z': value}, settings_role='testing')
                value = self.interface.get_value('Z:CUBE_Z')
            else:
                value = self.interface.get_value(obs)
            observable_outputs[obs] = value
        return observable_outputs







