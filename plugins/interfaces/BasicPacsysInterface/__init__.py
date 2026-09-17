from badger import interface
import pacsys
from pacsys import KerberosAuth
from pacsys.backends import Backend
from pacsys.errors import DeviceError
import re
import numpy as np
from time import sleep

class Interface(interface.Interface):
    name = 'BasicPacsysInterface'
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
    _timeout: float
    # Test-only seam: set to a pacsys.testing.FakeBackend() to avoid the real
    # control network. Left None in production, in which case every call goes
    # through the module-level pacsys.* functions (global default backend).
    _backend_override: Backend

    def __init__(self, **data):
        super().__init__(**data)
        self._states = {}
        self._current_sumsq = 0.0
        self._debug = False
        self._read_set_pair_pattern = re.compile("^.:.+,.:.+")
        self._read_set_pair_settle_tol_pattern = re.compile("^.:.+,.:.+,tol.+@*")
        self._setpoint_pattern = re.compile("^.:.+-SETPOINT")
        self._regulate_to = None
        self._timeout = 15.0
        self._backend_override = None

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

    # Handle read/set/[settling tolerance] devices, getting just the settable device names.
    # Bare names -- pacsys.write()/write_many() append .SETTING automatically.
    def extract_setting_devices(self, drf_list):
        if self._debug: print (f'extract_setting_devices() was passed {drf_list}.')
        ret_list = []
        for device in drf_list:
            if self._read_set_pair_pattern.fullmatch(device):
                ret_list.append(device.split(',')[1])
            else: ret_list.append(device)
        return ret_list

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

    # Batch read through pacsys, raising a clear DeviceError on the first bad reading
    # instead of silently handing back an unusable value (pacsys.get_many gives us the
    # per-device status for free -- acsys-py's read_once() had no equivalent check).
    def _get_many(self, drfs, debug=False):
        if self._backend_override is not None:
            readings = self._backend_override.get_many(drfs, timeout=self._timeout)
        else:
            readings = pacsys.get_many(drfs, timeout=self._timeout)
        if debug: print (f'_get_many({drfs}) got readings: {readings}')
        for r in readings:
            if not r.ok:
                raise DeviceError(r.drf, r.facility_code, r.error_code, r.message)
        return [r.value for r in readings]

    # Read values from devices
    # Use the reading device, not the setting device, if they have different names.
    # If a setpoint exists, instead of the readback, return squared difference of readback-setpoint.
    def get_values(self, drf_list, sample_events={}, setpoints={}, debug=False):
        readings_list = self.extract_reading_devices(drf_list)
        if debug: print (f'BasicPacsysInterface.get_values() got readings_list: {readings_list} and sample_events: {sample_events}.')
        # List of the one with -SETPOINT keyword in the device name
        setpoint_devs = self.get_setpoints(drf_list)
        if 'DummySumSq' in readings_list:
            if debug: print ('About to ask pacsys to get readings of ',readings_list, ' but return only DummySumSq.')
            valdict_to_return = {'DummySumSq': self._current_sumsq}
        else:
            valdict_to_return = {} # Final dict of read & calculated values to return
            # sample_events values already carry their leading '@' (e.g. '@e,52,e,0'), matching
            # the environments' own sample_events dicts. .get(...) with a fallback -- rather than
            # sample_events['default'] -- means an empty/no sample_events dict (the common case for
            # a plain current-value read, e.g. Environment.get_variables()) uses '@i' instead of
            # raising KeyError.
            event_drfs = [name + sample_events.get(name, sample_events.get('default', '@i')) for name in readings_list]
            if debug: print (f'About to run get_many().  setpoint_devs was :{setpoint_devs}.')
            readbacks = self._get_many(event_drfs, debug=debug)
            if debug: print (f'get_many returned readbacks: {readbacks}.')
            for i, name in enumerate(drf_list):
                if debug: print (f'drf_list[{i}] == {name}. Storing value as readbacks[i]={readbacks[i]}')
                valdict_to_return[name] = readbacks[i]
            if len(setpoint_devs)>0: # When there's a device (or more) to regulate
                if setpoints=={} or list(setpoints.values()) == []: exit(f'Please give setpoint(s) parameter value(s) for {setpoint_devs}.')
                if debug: print(f'setpoint_devs: {setpoint_devs}')
                # Interface's private variable: First readback value for these devices from this run.
                if self._regulate_to is None:
                    if debug:
                        print (f'self._regulate_to was None. Setting to read-back values for {setpoint_devs}:')
                    # Get the indices of the devices with setpoints
                    self._regulate_to = {}
                    for setpoint_dev in setpoint_devs:
                        dev_index = readings_list.index(self.extract_reading_devices([setpoint_dev,])[0])
                        if debug: print (f'{setpoint_dev}: {readbacks[dev_index]}')
                        self._regulate_to[setpoint_dev] = readbacks[dev_index]
                # Ready to calculate square error for each setpoint device.
                for setpoint_dev in setpoint_devs:
                    clean_device_name = self.extract_reading_devices([setpoint_dev,])[0]
                    dev_index = readings_list.index(clean_device_name)
                    if not clean_device_name in setpoints.keys(): exit (f'{clean_device_name} not found in {setpoints}. Please check Badger Environment parameters.')
                    if setpoints[clean_device_name]=='hold': setpoint = self._regulate_to[setpoint_dev]
                    else: setpoint = float(setpoints[clean_device_name])

                    if debug: print (f'{setpoint_dev} will be measured as ({readbacks[dev_index]} - {setpoint}) squared.')
                    valdict_to_return[setpoint_dev] = (readbacks[dev_index]-setpoint)**2.0
        if debug: print (f'BasicPacsysInterface.get_values() will return: {valdict_to_return}')
        return valdict_to_return

    def get_settings(self, drf_list, debug=True):
        if debug: print (f'BasicPacsysInterface.get_settings() was passed drf_list: {drf_list}')
        setting_names = self.extract_setting_devices(drf_list)
        setting_drfs = [f'{name}.SETTING@I' for name in setting_names]
        setting_values = self._get_many(setting_drfs, debug=debug)
        if debug: print (f'BasicPacsysInterface.get_settings() got back setting_values: {setting_values}')
        assert (len(setting_values) == len(setting_names))
        # package it up in a dictionary with the drf_list we we started from
        settings_dict = {}
        for set_name, set_val in zip(drf_list, setting_values):
            settings_dict[set_name] = set_val
        if debug: print (f'BasicPacsysInterface.get_settings() returning settings_dict: {settings_dict}')
        return settings_dict

    # Set devices to values settable_devices: dict[str, float]
    def set_values(self, drf_dict, settings_role, dont_set=False, debug=False):
        # Need a list of settings devices. Handle any devices with regex-enabled handling.
        setdevs = self.extract_setting_devices(list(drf_dict.keys()))
        setvals = list(drf_dict.values())

        if debug: print(f' OK set_values() will send\n * setdevs:{setdevs}\n * setvals:{setvals}')
        # Send the setting values to their devices.
        if not dont_set and settings_role != 'nosettings':
            backend = self._backend_override
            opened_backend = False
            if backend is None:
                backend = pacsys.dpm(auth=KerberosAuth(), role=settings_role)
                opened_backend = True
            try:
                results = backend.write_many(list(zip(setdevs, setvals)), timeout=self._timeout)
                for setdev, result in zip(setdevs, results):
                    if not result.success:
                        print(f'BasicPacsysInterface.set_values() failed to set {setdev}: {result.message}')
                    elif debug:
                        print(f'BasicPacsysInterface.set_values() set {setdev}.')
            finally:
                if opened_backend: backend.close()

        # Check that any specified tolerances have been met
        settled_tols, circ_buffers = self.extract_PID_tolerances(drf_dict) # JMSJ Set a unitory-sized buffer for non-toleranced devices?
        while len(circ_buffers)>0:
            if debug: print ('BasicPacsysInterface.set_values() has circ_buffers: ',circ_buffers)
            settling_devs = list(circ_buffers.keys())
            newvals = self.get_values(settling_devs)
            for i, setdev in enumerate(settling_devs):
                found_buff = circ_buffers[setdev]
                NaNs_here = np.where(np.isnan(found_buff))
                if np.array(NaNs_here).size > 0: # Buffer not full yet? Add the new value just read back for this device.
                    if debug: print (f'Could write new value {newvals[setdev]} to buffer location: {NaNs_here[0][0]}')
                    circ_buffers[setdev][NaNs_here[0][0]] = newvals[setdev]
                    # If buffer is full now, do the check for being in tolerance.
                    buffer_full = not np.isnan(circ_buffers[setdev]).any()
                    if buffer_full and self.meets_tolerance(circ_buffers[setdev], settled_tols[setdev], debug=True):
                        del circ_buffers[setdev] # Ok to do in these loops?
                else: # no NaNs; buffer was already full; move in newest value and recheck tolerance
                    circ_buffers[setdev] = np.roll(circ_buffers[setdev], -1) # move oldest entry to the end, and...
                    circ_buffers[setdev][-1] = newvals[setdev] #...overwrite with newest value
                    if self.meets_tolerance(circ_buffers[setdev], settled_tols[setdev], debug=True):
                        del circ_buffers[setdev] # Ok to do in these loops?
                sleep(0.7)
        return
