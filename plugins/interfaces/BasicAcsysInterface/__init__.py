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

    read_set_pair_pattern = re.compile("^\(.\:.+,.\:.+\)$")#, aix)
    
    def __init__(self, **data):
        super().__init__(**data)
        self._states = {}
    
    def extract_reading_devices(device_list):
        ret_list = []
        for device in device_list:
            isreadsetpair = self.read_set_pair_pattern.fullmatch(device)
            if isreadsetpair: print (f'Found read/set pair: {device} ({isreadsetpair})')
            
        
    def get_values(self, drf_list, sample_event='i'):
        readings = {}
        results = acsys.run_client(read_once, drf_list=drf_list)
        for i, name in enumerate(drf_list):
            readings[name] = results[i]
        return readings

    def set_values(self, drf_dict, settings_role): #DICT ?
        drf_list = []
        value_list = []
        for key, val in drf_dict.items():
            drf_list.append(key)
            value_list.append(val)
        acsys.run_client(set_once, drf_list=drf_list, value_list=value_list,
                         settings_role=settings_role) 
