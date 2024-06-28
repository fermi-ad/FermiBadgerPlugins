from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "myenv"
    variables = {
        "Z:CUBE_X": [ 0, 100],
        "Z:CUBE_Y": [ 0,  90]
    }
    observables = [
        # "Z:CUBE_X",
        # "Z:CUBE_Y",
        "Z:CUBE_Z",
        "G:AMANDA"
    ]
    testparam: int=42
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_values(variable_names)

    def set_variables(self, variable_inputs: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        self.interface.set_values(variable_inputs, settings_role="testing")

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        # return self.interface.get_values(observable_names)
        observable_outputs = {}
        for obs in observable_names:
            if obs == 'Z:CUBE_Z':
                value = self.interface.get_value('Z:CUBE_X')**2 + self.interface.get_value('Z:CUBE_Y')**2
                self.interface.set_values({'Z:CUBE_Z': value}, settings_role='testing')
                value = self.interface.get_value('Z:CUBE_Z')
            else:
                value = self.interface.get_value(obs)
            print(obs)
            print(value)
            observable_outputs[obs] = value
        return observable_outputs







