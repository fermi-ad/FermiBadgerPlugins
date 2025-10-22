from badger import interface
import numpy as np
import xtrack as xt  # tracking module of Xsuite
from time import sleep

class Interface(interface.Interface):
    name = 'SimpleVirtualAcceleratorInterface'
    """
    variables =
    observables =
    _variables =
    _observations ="""
    # If params not specified, it would be an empty dict
    # Private variables
    _states: dict
    _current_sumsq: float
    _debug: bool
    _regulate_to: float

    
    
    def __init__(self, **data):
        super().__init__(**data)
        self._states = {}
        self._current_sumsq = 0.0
        self._debug = False
        
    def meets_tolerance(self, buff, tol, debug=False):
        spread = max(buff) - min(buff)
        if spread <= tol:
            if debug: print (f'Spread of {buff} is {spread} <= {tol}.')
            return True
        else:
            if debug: print (f'Spread of {buff} is {spread} but greater than {tol}.')
            return False

    # Read values from devices
    def get_values(self, drf_list, debug=False):
        readbacks = []
        for i, name in enumerate(drf_list):
            if debug: print (f'drf_list[{i}] == {name}. Storing value as readbacks[i]={readbacks[i]}')
            valdict_to_return[name] = readbacks[i]
        if debug: print (f'BasicAcsysInterface.get_values() will return: {valdict_to_return}')
        return valdict_to_return

    def get_settings(self, drf_list, debug=True):
        for set_name, set_val in zip(drf_list, setting_values):
            settings_dict[set_name] = set_val
        if debug: print (f'SimpleVirtualAcceleratorInterface.get_settings() returning settings_dict: {settings_dict}')
        return settings_dict
    
    # Set devices to values settable_devices: dict[str, float]
    def set_values(self, drf_dict, dont_set=False, debug=False):
        # Implement all settings and return nothing
        return
