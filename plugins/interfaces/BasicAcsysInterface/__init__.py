from badger import interface
import acsys.dpm, acsys
from acsys.dpm import ItemData
from scanner import read_once,set_once
import re
import numpy as np
from time import sleep

class Interface(interface.Interface):
    name = 'BasicAcsysInterface'
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
        self._read_set_pair_pattern = re.compile("^.:.+,.:.+")
        self._read_set_pair_settle_tol_pattern = re.compile("^.:.+,.:.+,tol.+@*")
        self._setpoint_pattern = re.compile("^.:.+-SETPOINT")
        self._regulate_to = None
        
    # Handle read/set/[settling tolerance] devices, getting just the reading
    def extract_reading_devices(self, device_list):
        ret_list = []
        for device in device_list:
            isreadsetpair = self._read_set_pair_pattern.fullmatch(device)
            isreadsettolr = self._read_set_pair_settle_tol_pattern.fullmatch(device)
            issetpoint_dev = self._setpoint_pattern.match(device)
            if isreadsetpair or isreadsettolr: # Get just the reading device
                reading_device = device.split(',')[0]
                ret_list.append(reading_device)
            elif issetpoint_dev: # Clean off keyword
                reading_device = device.replace('-SETPOINT','').strip()
                ret_list.append(reading_device)
            else: ret_list.append(device)
        return ret_list

    # Handle read/set/[settling tolerance] devices, getting just the settable devices
    def extract_setting_devices(self, device_dict):
        ret_dict = {}
        for device,val in device_dict.items():
            isreadsetpair = self._read_set_pair_pattern.fullmatch(device)
            withSETTING = f'{val}.SETTING' # Needed to make all settings? 
            if isreadsetpair:
                setting_device = device.split(',')[1]
                ret_dict[setting_device] = withSETTING
            else: ret_dict[device] = withSETTING
        return ret_dict

    def meets_tolerance(self, buff, tol, debug=False):
        spread = max(buff) - min(buff)
        if spread <= tol:
            if debug: print (f'Spread of {buff} is {spread} <= {tol}.')
            return True
        else:
            if debug: print (f'Spread of {buff} is {spread} but greater than {tol}.')
            return False
    
    # While making settings, helper function to handle those with tolerances (because settling occurs)
    # "L:CDPHAS,L:LDPADJ,tol2@5.0": reading,setting,tol{MINCOUNT}@{TOLERANCE}
    #   returns: Dictionaries settled_tols, circ_buffers
    def extract_PID_tolerances(self, device_dict, debug=False):
        settled_tols = {} # dict to return: PID_tolerances = {settings device:'2.5', }
        circ_buffers = {} # of empty array buffers of the tailored lengths
        for device,val in device_dict.items():
            if not self._read_set_pair_settle_tol_pattern.fullmatch(device):
                if debug: print (device,"  did not match pattern; tolerance not specified correctly?")
                continue
            reading_dev = device.split(',')[0]
            #settings_dev = device.split(',')[1]
            tol = device.split(',')[2].replace('tol','')
            if debug: print (f'extract_PID_tolerances() sees tol: {tol}')
            bufferlen = int(tol.split('@')[0])
            tolerance = float(tol.split('@')[1])
            settled_tols[reading_dev] = tolerance # Use full device? Extract reading device?
            circ_buffers[reading_dev] = np.empty(bufferlen, dtype=float)
            circ_buffers[reading_dev][:] = np.nan # Initialize all to NaN
        return settled_tols, circ_buffers

    # Any SETPOINTs in the list to read?
    def get_setpoints(self, drf_list):
        setpoint_list = []
        for drf in drf_list:
            if self._setpoint_pattern.match(drf): setpoint_list.append(drf)
        return setpoint_list

    # Read values from devices
    def get_values(self, drf_list, sample_event='i', setpoint_str='', debug=False):
        readings_list = self.extract_reading_devices(drf_list)
        if self._debug: print ('BasicAcsysInterface.get_values() got readings_list: ',readings_list)
        setpoint_devs = self.get_setpoints(drf_list)
        if 'DummySumSq' in readings_list:
            if self._debug: print ('About to ask ACSYS to get readings of ',readings_list, ' but return only DummySumSq.')
            readings = {'DummySumSq': self._current_sumsq}
        else:
            readings = {} # dict of returned values
            results = acsys.run_client(read_once, drf_list=readings_list) # FIXME , sample_event=sample_event)
            for i, name in enumerate(drf_list):
                readings[name] = results[i]
            if len(setpoint_devs)>0: # When there's a device to regulate 
                if setpoint_str == '': exit(f'Please give setpoint parameter value for {setpoint_devs}.')
                # Interface's private variable: First readback value for a device.
                if self._regulate_to is None: 
                    if debug: print (f'self._regulate_to was None. Setting to read-back value for {setpoint_devs[0]}: {readings[setpoint_devs[0]]}.')
                    self._regulate_to = readings[setpoint_devs[0]] 

                if debug: print (f'setpoint_str = {setpoint_str}.')
                if setpoint_str=='hold': setpoint = self._regulate_to
                else: setpoint = float(setpoint_str)
                if debug: print (f'... and so setpoint = {setpoint}')
                for setpoints_dev in setpoint_devs:
                    if debug: print (f'{setpoints_dev} will go to value {readings[setpoints_dev]} - {setpoint} squared.')
                    readings[setpoints_dev] = (readings[setpoints_dev]-setpoint)**2.0
        if self._debug: print (f'BasicAcsysInterface.get_values() will return: {readings}')
        return readings

    # Set devices to values
    def set_values(self, drf_dict, settings_role, dont_set=False, debug=False):
        print (f'BasicAcsysInterface.set_values() was passed drf_dict: {drf_dict}')

        # Testing option, when not making settings.
        # if settings_role == 'nosettings': 
        #     self._current_sumsq = 0.0
        #     if self._debug: print ('No settings. drf_dict: ',drf_dict)
        #     read_devs = self.extract_reading_devices(drf_dict.keys())
        #     newvals = self.get_values(read_devs, sample_event='i')
        #     for drf, val in newvals.items():
        #         self._current_sumsq += float(val)**2.0
        #     if self._debug: print ('After BasicAcsysInterface.set_values() ran, now self._current_sumsq = ', self._current_sumsq)
        #     return

        # Need a list of settings devices with the .SETTING suffix appended.
        # Handle any devices with regex-enabled handling.
        setdevs = self.extract_setting_devices(drf_dict)
        setvals = []
        for key, val in drf_dict.items():
            setvals.append(val)

        # Send the setting values to their devices.
        if not dont_set and settings_role != 'nosettings': acsys.run_client(set_once, drf_list=setvals, value_list=setvals, settings_role=settings_role)

        # Check that any specified tolerances have been met
        settled_tols, circ_buffers = self.extract_PID_tolerances(drf_dict) # JMSJ Set a unitory-sized buffer for non-toleranced devices?
        while len(circ_buffers)>0:
            print ('BasicAcsysInterface.set_values() has circ_buffers: ',circ_buffers)
            settling_devs = list(circ_buffers.keys())
            newvals = self.get_values(settling_devs)
            for i, setdev in enumerate(settling_devs):
                found_buff = circ_buffers[setdev]
                NaNs_here = np.where(np.isnan(found_buff))
                if np.array(NaNs_here).size > 0: # Buffer not full yet? Add the new value just read back for this device.
                    print (f'Could write new value {newvals[setdev]} to buffer location: {NaNs_here[0][0]}')
                    circ_buffers[setdev][NaNs_here[0][0]] = newvals[setdev]
                    # If buffer is full now, do the check for being in tolerance.
                    buffer_full = np.all(np.where(~np.isnan(circ_buffers[setdev])))
                    if buffer_full and meets_tolerance(circ_buffers[setdev], settled_tols[setdev], debug=True):
                        del circ_buffers[setdev] # Ok to do in these loops?
                else: # no NaNs; buffer was already full; move in newest value and recheck tolerance
                    circ_buffers[setdev] = np.roll(circ_buffers[setdev], -1) # move oldest entry to the end, and...
                    circ_buffers[setdev][-1] = newvals[setdev] #...overwrite with newest value
                    if self.meets_tolerance(circ_buffers[setdev], settled_tols[setdev], debug=True):
                        del circ_buffers[setdev] # Ok to do in these loops?
                sleep(0.7)
        return
