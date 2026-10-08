from badger import interface
import pacsys
from pacsys import KerberosAuth
from pacsys.backends import Backend
from pacsys.errors import DeviceError
from pacsys.exp import read_fresh
import math
import re
import numpy as np
from time import sleep, monotonic
from periodic import unwrap

# Array observables: "<DRF>|<reduce>" reads the (optionally ranged) array DRF and returns
# one number. '|' cannot occur in a DRF, so the split is unambiguous.
REDUCTIONS = {
    'mean':   lambda a: float(np.mean(a)),
    'rms':    lambda a: float(np.sqrt(np.mean(np.square(a)))),
    'std':    lambda a: float(np.std(a)),
    'min':    lambda a: float(np.min(a)),
    'max':    lambda a: float(np.max(a)),
    'sum':    lambda a: float(np.sum(a)),
    'absmax': lambda a: float(np.max(np.abs(a))),
}

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
    _unwrap_ref: dict
    _timeout: float
    _warned_pairs: set
    # Test-only seam: set to a pacsys.testing.FakeBackend() to avoid the real
    # control network. Left None in production, in which case every call goes
    # through the module-level pacsys.* functions (global default backend).
    _backend_override: Backend
    # ponytail: readback tolerance for a bare device's stored SETTING vs the value sent.
    # Only quantisation or front-end clipping can differ; widen if a device class needs it.
    _readback_rtol = 1e-3
    _readback_atol = 1e-6

    def __init__(self, **data):
        super().__init__(**data)
        self._states = {}
        self._current_sumsq = 0.0
        self._debug = False
        self._read_set_pair_pattern = re.compile("^.:.+,.:.+")
        self._read_set_pair_settle_tol_pattern = re.compile("^.:.+,.:.+,tol.+@*")
        self._setpoint_pattern = re.compile("^.:.+-SETPOINT")
        self._regulate_to = None
        self._unwrap_ref = {}
        self._timeout = 15.0
        self._backend_override = None
        self._warned_pairs = set()

    # "<DRF>|<reduce>" -> (DRF, reduce); anything else -> (name, None)
    def split_reduction(self, name):
        if '|' not in name: return name, None
        drf, reduce = name.rsplit('|', 1)
        if reduce not in REDUCTIONS:
            raise ValueError(f'{name}: unknown reduction {reduce!r}; choose from {sorted(REDUCTIONS)}')
        return drf, reduce

    # Handle read/set/[settling tolerance] devices, getting just the reading
    def extract_reading_devices(self, device_list):
        ret_list = []
        for device in device_list:
            device, _ = self.split_reduction(device)
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

    # Which DRF tells us a setting landed. A read/set pair's readback is its READING device,
    # a different physical quantity (e.g. measured phase L:CDPHAS for the adjust L:LDPADJ),
    # so it is never compared to the value sent: the settle loop (tolN@T) verifies pairs.
    # A bare device's readback is its stored setting. -SETPOINT names are never written.
    def readback_drf(self, name):
        if self._setpoint_pattern.match(name): return None
        if self._read_set_pair_pattern.fullmatch(name): return name.split(',')[0]
        return f'{name}.SETTING@I'

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

    @staticmethod
    def _reduce(value, reduce):
        if reduce is None: return value
        if np.ndim(value) == 0:
            raise ValueError(f'reduction {reduce!r} needs an array reading, got scalar {value!r}')
        return REDUCTIONS[reduce](np.asarray(value, dtype=float))

    # Read one value per DRF: a single reading (count 1, via get_many) or the mean of
    # `count` fresh events (via a temporary subscription). Array readings are reduced
    # per event before averaging.
    def _read_values(self, event_drfs, counts, reduces, debug=False):
        values = [None] * len(event_drfs)
        single = [i for i, n in enumerate(counts) if n <= 1]
        if single:
            for i, v in zip(single, self._get_many([event_drfs[i] for i in single], debug=debug)):
                values[i] = self._reduce(v, reduces[i])
        for n in sorted({n for n in counts if n > 1}):
            idx = [i for i, c in enumerate(counts) if c == n]
            for i in idx:
                if '@' not in event_drfs[i] or event_drfs[i].lower().endswith('@i'):
                    raise ValueError(f'{event_drfs[i]}: averaging {n} events needs a streaming event, not @i')
            results = read_fresh([event_drfs[i] for i in idx], count=n, timeout=self._timeout,
                                 backend=self._backend_override)
            for i, res in zip(idx, results):
                per_event = []
                for r in res.readings:
                    if not r.ok:
                        raise DeviceError(r.drf, r.facility_code, r.error_code, r.message)
                    per_event.append(self._reduce(r.value, reduces[i]))
                values[i] = float(np.mean(per_event))
                if debug: print (f'{event_drfs[i]}: mean of {n} events {per_event} = {values[i]}')
        return values

    # Read values from devices
    # Use the reading device, not the setting device, if they have different names.
    # If a setpoint exists, instead of the readback, return squared difference of readback-setpoint.
    # periods: {reading device: period} for phase-like devices (e.g. {'L:CDPHAS': 360.0}).
    # Their readbacks are unwrapped onto the branch nearest the first reading of this run
    # (or nearest the setpoint, for -SETPOINT devices), so a wrap through 0 is not a jump.
    # average_events: {reading device or 'default': N} -- N > 1 returns the mean of N fresh events.
    # Observable names may carry "|<reduce>" (see REDUCTIONS) to turn an array reading into a number.
    def get_values(self, drf_list, sample_events={}, setpoints={}, periods={}, average_events={}, debug=False):
        readings_list = self.extract_reading_devices(drf_list)
        reduces = [self.split_reduction(name)[1] for name in drf_list]
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
            counts = [int(average_events.get(name, average_events.get('default', 1))) for name in readings_list]
            if debug: print (f'About to read {event_drfs} (events to average: {counts}).  setpoint_devs was :{setpoint_devs}.')
            readbacks = self._read_values(event_drfs, counts, reduces, debug=debug)
            if debug: print (f'readbacks: {readbacks}.')
            for i, name in enumerate(drf_list):
                if debug: print (f'drf_list[{i}] == {name}. Storing value as readbacks[i]={readbacks[i]}')
                valdict_to_return[name] = readbacks[i]
            readbacks = list(readbacks)
            for i, name in enumerate(readings_list):
                if name in periods:
                    self._unwrap_ref.setdefault(name, readbacks[i])
                    readbacks[i] = unwrap(readbacks[i], self._unwrap_ref[name], periods[name])
                    valdict_to_return[drf_list[i]] = readbacks[i]
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

                    reading = readbacks[dev_index]
                    if clean_device_name in periods: reading = unwrap(reading, setpoint, periods[clean_device_name])
                    if debug: print (f'{setpoint_dev} will be measured as ({reading} - {setpoint}) squared.')
                    valdict_to_return[setpoint_dev] = (reading-setpoint)**2.0
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

    # After a batch write: a bare device's stored SETTING must match what was sent (warn
    # only -- quantisation and front-end clipping are legitimate); a pair's readback is
    # its READING device, verified by the settle loop, so no value comparison here.
    def _check_readbacks(self, drf_dict, debug=False):
        bare = [(name, val) for name, val in drf_dict.items()
                if self.readback_drf(name) == f'{name}.SETTING@I']
        if bare:
            stored = self._get_many([self.readback_drf(name) for name, _ in bare], debug=debug)
            for (name, sent), got in zip(bare, stored):
                if not math.isclose(got, sent, rel_tol=self._readback_rtol, abs_tol=self._readback_atol):
                    print(f'BasicPacsysInterface: {name} stored setting {got} differs from the {sent} sent.')
        for name in drf_dict:
            if (self._read_set_pair_pattern.fullmatch(name)
                    and not self._read_set_pair_settle_tol_pattern.fullmatch(name)
                    and name not in self._warned_pairs):
                self._warned_pairs.add(name)
                print(f'BasicPacsysInterface: {name} has no tolN@T spec, so its reading is not verified after a setting.')

    # Set devices to values settable_devices: dict[str, float]
    def set_values(self, drf_dict, settings_role, dont_set=False, periods={}, debug=False):
        # Need a list of settings devices. Handle any devices with regex-enabled handling.
        setdevs = self.extract_setting_devices(list(drf_dict.keys()))
        setvals = list(drf_dict.values())

        if debug: print(f' OK set_values() will send\n * setdevs:{setdevs}\n * setvals:{setvals}')
        # Send the setting values to their devices.
        if not dont_set and settings_role != 'nosettings':
            backend = self._backend_override
            opened_backend = False
            if backend is None:
                backend = pacsys.dpm(auth=KerberosAuth(), role=settings_role, timeout=self._timeout)
                opened_backend = True
            try:
                # Explicit .SETTING: identical on the wire (pacsys retargets a bare name to SETTING)
                # and it keeps pacsys.testing.FakeBackend's stored SETTING in step with the write.
                results = backend.write_many([(f'{d}.SETTING', v) for d, v in zip(setdevs, setvals)],
                                             timeout=self._timeout)
                failed = [f'{setdev}: error {result.error_code} {result.message}'
                          for setdev, result in zip(setdevs, results) if not result.ok]
                if failed:
                    # Never carry on optimizing with the machine in an unknown state.
                    raise RuntimeError('BasicPacsysInterface.set_values() failed to set ' + '; '.join(failed))
                if debug: print(f'BasicPacsysInterface.set_values() set {setdevs}.')
                self._check_readbacks(drf_dict, debug=debug)
            finally:
                if opened_backend: backend.close()

        # Check that any specified tolerances have been met
        settled_tols, circ_buffers = self.extract_PID_tolerances(drf_dict) # JMSJ Set a unitory-sized buffer for non-toleranced devices?
        deadline = monotonic() + self._timeout
        while len(circ_buffers)>0:
            if monotonic() > deadline:
                raise RuntimeError('BasicPacsysInterface.set_values(): readings did not settle within '
                                   f'{self._timeout} s: ' + '; '.join(f'{d} last {b}' for d, b in circ_buffers.items()))
            if debug: print ('BasicPacsysInterface.set_values() has circ_buffers: ',circ_buffers)
            settling_devs = list(circ_buffers.keys())
            newvals = self.get_values(settling_devs, periods=periods)
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
