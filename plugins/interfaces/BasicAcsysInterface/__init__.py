from badger import interface
import acsys.dpm, acsys
from acsys.dpm import ItemData
from scanner import read_once,set_once
import re

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
        
    def __init__(self, **data):
        super().__init__(**data)
        self._states = {}
        self._read_set_pair_pattern = re.compile("^.:.+,.:.+$")

    def extract_reading_devices(self, device_list):
        ret_list = []
        for device in device_list:
            isreadsetpair = self._read_set_pair_pattern.fullmatch(device)
            if isreadsetpair:
                reading_device = device.split(',')[0]
                ret_list.append(reading_device)
            else: ret_list.append(device)
        return ret_list

    def extract_setting_devices(self, device_dict):
        ret_dict = {}
        for device,val in device_dict.items():
            isreadsetpair = self._read_set_pair_pattern.fullmatch(device)
            if isreadsetpair:
                setting_device = device.split(',')[1]
                ret_dict[setting_device] = val
            else: ret_dict[device] = val
        return ret_dict

    def get_values(self, drf_list, sample_event='i'):
        readings_list = self.extract_reading_devices(drf_list)
        readings = {}
        results = acsys.run_client(read_once, drf_list=readings_list) # FIXME , sample_event=sample_event) 
        for i, name in enumerate(drf_list):
            readings[name] = results[i]
        print (f'get_values() will return: {readings}')
        return readings

    def set_values(self, drf_dict, settings_role):
        drf_dict = self.extract_setting_devices(drf_dict)
        drf_list = []
        value_list = []
        for key, val in drf_dict.items():
            drf_list.append(key)
            value_list.append(val)
        acsys.run_client(set_once, drf_list=drf_list, value_list=value_list,
                         settings_role=settings_role) 
