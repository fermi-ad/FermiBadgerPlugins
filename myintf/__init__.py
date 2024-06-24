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
        readings = [None]*len(drf_list)
        async def wrapper(con):
            async with acsys.dpm.DPMContext(con, dpm_node='DPM09') as dpm:
                for i in range(len(drf_list)):
                    await dpm.add_entry(i, drf_list[i]+'@i')
                    await dpm.start()

                async for reply in dpm:
                    readings[reply.tag]=reply.data
                    if readings.count(None) ==0:
                        break
            return readings
        return acsys.run_client(wrapper)
            
        

    def set_values(self, drf_list, value_list, settings_role): #DICT ?
        async def wrapper(con):
            #async def set_once(con,drf_list,value_list,settings_role):
            async with acsys.dpm.DPMContext(con) as dpm:
                await dpm.enable_settings(role=settings_role)
                for i, dev in enumerate(drf_list):
                    #await dpm.add_entry(i, dev+'@i')
                    await dpm.add_entry(i, dev+'@N')
                await dpm.start()
       
                setpairs = list(enumerate(value_list))
                await dpm.apply_settings(setpairs)
                print('settings applied: ',value_list)

            return None
        return acsys.run_client(wrapper)
    
##Testing acsys-python code   
#my = Interface()
#my.set_values(drf_list=['Z:CUBE_Z'], value_list=[12], settings_role='testing')
#print(my.get_values(drf_list=['Z:CUBE_Z','Z:CUBE_X', 'Z:CUBE_Y']))