from badger import interface
import numpy as np
#import xtrack as xt  # tracking module of Xsuite
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
    def get_values(self, device_list, twiss, debug=True):
        readbacks = {}
        for name in device_list:
            if   name == 'qx':
                readbacks[name] = np.float64(twiss.qx)
            elif name == 'qy':
                readbacks[name] = np.float64(twiss.qy)
            else: readbacks[name] = None
        if debug: print (f'SimpleVirtualAcceleratorInterface.get_values() will return: {readbacks}')
        return readbacks

    # Or maybe you just want the settings
    def get_settings(self, settings_names, xt_env, debug=True):
        settings = {}
        for name in settings_names:
            if  name in ['kqd', 'kqf']:
                settings[name] = xt_env[name]
                print ('  Refraining from returning a whole: ', xt_env[name])
            else: settings[name] = None
        if debug: print (f'SimpleVirtualAcceleratorInterface.get_settings() will return: {settings}')
        return settings
    
    # Set devices to values settable_devices: dict[str, float]
    def set_values(self, settings_dict, xt_env, dont_set=False, debug=False):
        # Dry run?
        if dont_set: return
        # Implement all settings and return nothing
        for key, val in settings_dict.items():
            if key[0] == '_': continue
            xt_env[key] = val
        return
