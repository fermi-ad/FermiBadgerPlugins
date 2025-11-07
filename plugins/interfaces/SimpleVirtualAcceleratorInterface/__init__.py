from badger import interface
import numpy as np
#import xtrack as xt  # tracking module of Xsuite
from time import sleep
import re

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
        self._setpoint_pattern = re.compile(".+-SETPOINT") # For regulation-to-setpoint objectives

    def meets_tolerance(self, buff, tol, debug=False):
        spread = max(buff) - min(buff)
        if spread <= tol:
            if debug: print (f'Spread of {buff} is {spread} <= {tol}.')
            return True
        else:
            if debug: print (f'Spread of {buff} is {spread} but greater than {tol}.')
            return False

    # Handle keywords in given device list, returning lists of clean_device_names, setpoint_devs
    def extract_reading_devices(self, device_list, debug=False):
        ret_list = []
        with_setpoints = []
        for device in device_list:
            if debug: print (f'extract_reading_devices() found device {device} in device_list.')
            issetpoint_dev = self._setpoint_pattern.match(device)
            if issetpoint_dev: # Clean off keyword
                if debug: print (f'...and it is a setpoint device...')
                with_setpoints.append(device)
                reading_device = device.replace('-SETPOINT','').strip()
                if debug: print (f'...whose real name is {reading_device}.')
                ret_list.append(reading_device)
                if debug: print (f'{device} is a setpoint device for {reading_device}.')
            else: ret_list.append(device)
        if debug: print (f'Interface extract_reading_devices() will return {ret_list} and\n{with_setpoints}.')
        return ret_list, with_setpoints
        
    # Read values from devices
    def get_values(self, device_list, twiss, setpoints={}, debug=True):
        if debug: print(f'Interface get_values() was passed device_list:\n{device_list}\n and setpoints:\n{setpoints}')
        readbacks = {}
        clean_device_list, setpoint_devs = self.extract_reading_devices(device_list, debug=debug)
        for rawdevname in device_list:
            # Establish whether it's a setpoint observable, and if so, a clean name so we can get the twiss parameter to begin the calculation
            issetpoint_dev = self._setpoint_pattern.match(rawdevname)
            if issetpoint_dev: clean_dev_name = rawdevname.replace('-SETPOINT','').strip()
            else: clean_dev_name = rawdevname

            # Get the related twiss parameter value
            tempval = None
            if   clean_dev_name == 'qx': tempval = float(twiss.qx)
            elif clean_dev_name == 'qy': tempval = float(twiss.qy)

            # Value to return goes in the dictionary
            readbacks[rawdevname] = tempval
            if issetpoint_dev: #...but update accordingly if it's a squared setpoint disregulation we want
                print (f'Interface get_values() working on setpoint device {clean_dev_name}.')
                disreg = tempval - setpoints[clean_dev_name]
                readbacks[rawdevname] = disreg ** 2.0
                if debug: print(f"Interface get_values(): disreg={disreg} and squared that's {readbacks[rawdevname]}")

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
