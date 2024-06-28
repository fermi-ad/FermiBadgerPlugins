from badger import interface
import acsys.dpm
from acsys.dpm import ItemData
class Interface(interface.Interface):
    name = 'myintf'
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
    def get_values(self, drf_list):
        readings = {}
        async def wrapper(con):
            async with acsys.dpm.DPMContext(con, dpm_node='DPM09') as dpm:
                for i in range(len(drf_list)):
                    await dpm.add_entry(i, drf_list[i]+'@i')
                    await dpm.start()
                async for reply in dpm:
                    readings[reply.meta['name']]=reply.data
                    if sorted(readings.keys()) == sorted(drf_list):
                        break
                print(readings)
                return readings
        return acsys.run_client(wrapper)

    def set_values(self, drf_dict, settings_role): #DICT ?
        async def wrapper(con):
            #async def set_once(con,drf_list,value_list,settings_role):
            async with acsys.dpm.DPMContext(con) as dpm:
                await dpm.enable_settings(role=settings_role)
                for i, key in enumerate(drf_dict.keys()):
                    await dpm.add_entry(i, key+'@n')
                await dpm.start()
                setpairs = list(enumerate(drf_dict.values()))
                await dpm.apply_settings(setpairs)
                print('settings applied: ',setpairs)
            return None
        return acsys.run_client(wrapper)
