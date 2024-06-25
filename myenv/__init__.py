import numpy as np
from badger import environment

class Environment(environment.Environment):

    name = 'myenv'

    variables = {
        'Z:CUBE_X': [0, 1],
        'Z:CUBE_Y': [0, 1]
    }
    
    observables = ['Z:CUBE_X', 'Z:CUBE_Y', 'Z:CUBE_Z', 'G:AMANDA']


    def get_variables(self, variable_names: list[str]) -> dict:
        variable_outputs = {v: self.interface.get_values(variable_names) for v in variable_names}
        return variable_outputs

    def set_variables(self, variable_inputs: dict[str, float]):
        self.interface.set_values(variable_inputs, settings_role='testing')

    def get_observables(self, observable_names: list[str]) -> dict:
        """
        x = self._variables['x']
        y = self._variables['y']
        z = self._variables['z']

        observable_outputs = {}
        for obs in observable_names:
            if obs == 'norm':
                observable_outputs[obs] = (x ** 2 + y ** 2 + z ** 2) ** 0.5
            elif obs == 'mean':
                observable_outputs[obs] = (x + y + z) / 3

        return observable_outputs"""