import numpy as np
from badger import environment

class Environment(environment.Environment):

    name = 'myenv'

    variables = {
        'Z:CUBE_X': [],
        'Z:CUBE_Y': [],
    }
    
    observables = ['Z:CUBE_Z']

    # Internal variables start with a single underscore
    _variables = {
        'Z:CUBE_X': self.interface.get_values(drf_list=['Z:CUBE_X']),
        'Z:CUBE_Y': self.interface.get_values(drf_list=['Z:CUBE_Y'])
    }

    _observations = {
        'Z:CUBE_Z': self.interface.get_values(drf_list=['Z:CUBE_X'])
    }

    def get_variables(self, variable_names: list[str]) -> dict:
        variable_outputs = {v: self._variables[v] for v in variable_names}
        return variable_outputs

    def set_variables(self, variable_inputs: dict[str, float]):
        for var, x in variable_inputs.items():
            self._variables[var] = x
        #set_values(drf_list=['Z:CUBE_Z'], value_list=[12], settings_role='testing')

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