import acsys.dpm
import threading
import asyncio
import time
import os
import pandas as pd
from functools import reduce
import datetime as dt

async def set_many(con,thread_context):
    async with acsys.dpm.DPMContext(con) as dpm:
        await dpm.enable_settings(role=thread_context['role'])
        
        await dpm.add_entries(list(enumerate(thread_context['param_list'])))

        await dpm.start()
        print("Start ramp")
        for rr in thread_context['ramp_list']:
            one_data = [None]*len(thread_context['param_list'])
            setpairs = list(enumerate([n for n in rr if isinstance(n,float)]))
            await dpm.apply_settings(setpairs)

            try:
                async for reply in dpm.replies(tmo=float(thread_context['timeout'])):
                    if thread_context['stop'].is_set():
                        break
                    thread_context["pause"].wait()
                    if reply.isReading:
                        one_data[reply.tag]= reply.data
                        with thread_context['lock']:
                            thread_context['data'].append({'tag':reply.tag,'stamp':reply.stamp,'data': reply.data,
                                                           'name':thread_context['param_list'][reply.tag].split('@')[0]})
                    if one_data.count(None)==0:
                        break                    

            except Exception as e:
                print(repr(e))
                
        print("Ended ramp")
        
    return None

async def set_once(con,drf_list,value_list,settings_role):
    #settings = [None]*len(drf_list)
    async with acsys.dpm.DPMContext(con) as dpm:
        await dpm.enable_settings(role=settings_role)
        for i, dev in enumerate(drf_list):
            #await dpm.add_entry(i, dev+'@i')
            await dpm.add_entry(i, dev+'@N')
        await dpm.start()
        '''
        async for reply in dpm.replies():
            if reply.isReading:
                settings[reply.tag]= reply.data + value_list[reply.tag]
            if settings.count(None)==0:
                break

        setpairs = list(enumerate(settings))
        '''
        setpairs = list(enumerate(value_list))
        await dpm.apply_settings(setpairs)
        print('settings applied: ',value_list)

    return None

async def read_many(con, thread_context):
    """Read many values from the DPM."""
    async with acsys.dpm.DPMContext(con) as dpm:
        #thread_context['daq_task'] = dpm
        await dpm.add_entries(list(enumerate(thread_context['param_list'])))

        it = int(thread_context['Nmeas'])*len(thread_context['param_list'])
        await dpm.start()
        try:
            async for reply in dpm.replies(tmo=float(thread_context['timeout'])):

                if thread_context['stop'].is_set():
                    break
                thread_context["pause"].wait()
                if reply.isReading:
                    it = it-1
                    with thread_context['lock']:

                        thread_context['data'].append({'tag':reply.tag,'stamp':reply.stamp,'data': reply.data,
                                                   'name':thread_context['param_list'][reply.tag].split('@')[0]})
                        if (len(thread_context['data'])>5000000):
                            print("Buffer overflow, deleting",thread_context['data'][0]['name'],thread_context['data'][0]['name'])
                            thread_context['data'].pop(0)
                elif reply.isStatus:
                    print(f'Status: {reply}')
                else:
                    print(f'Unknown response: {reply}')
                if it==0:
                    thread_context['stop'].set()

                
            print('Ending read_many loop')
        except Exception as e:
            print(repr(e))


async def read_once(con,drf_list):

    settings = [None]*len(drf_list)
    async with acsys.dpm.DPMContext(con, dpm_node='DPM09') as dpm:
        for i in range(len(drf_list)):
            await dpm.add_entry(i, drf_list[i]+'@i')

            await dpm.start()

        async for reply in dpm:
            settings[reply.tag]=reply.data
            if settings.count(None) ==0:
                break
    return settings

class scanner:
    def __init__(self,role):
        self.thread_dict = {}

        
    def _acnet_daq_scan(self,thread_name):
        devs = [s for s in self.thread_dict[thread_name]['ramp_list'][0] if str(s).find(':')!=-1]
        nominals = self.get_settings_once(devs)
        
        event_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(event_loop)
            if len(self.thread_dict[thread_name]['ramp_list'])==0:
                acsys.run_client(read_many, thread_context=self.thread_dict[thread_name])
            else:
                acsys.run_client(set_many, thread_context=self.thread_dict[thread_name])
        finally:
            if event_loop.is_running():
                event_loop.close()
            #write data
            timestr = time.strftime("%Y%m%d_%H%M%S")
            self.fill_write_dataframe_oneTS(self.thread_dict[thread_name]['data'],
                                            [par.split('@')[0] for par in self.thread_dict[thread_name]['param_list']],
                                            os.path.join(os.getcwd(),'%s.csv'%(timestr)))
            self.thread_dict[thread_name]['stop'].set()
            #Return to nominals    
            self.apply_settings_once(devs,nominals, self.thread_dict[thread_name]['role'])

            
    def get_thread_data(self, thread_name):
        """Get the data from the thread."""
        with self.thread_dict[thread_name]['lock']:
            data=self.thread_dict[thread_name]['data'].copy()
            self.thread_dict[thread_name]['data'].clear()
            return data

    def start_thread(self, thread_name, timeout, param_list, ramp_list, role, Nmeas):
        """Start the thread."""
        print('Starting thread', thread_name)
        daq_thread = threading.Thread(
            target=self._acnet_daq_scan,
            args=(thread_name,)
        )

        self.thread_dict[thread_name] = {
            'thread': daq_thread,
            'lock': threading.Lock(),
            'timeout': timeout,
            'data': [],
            'param_list': param_list,
            'ramp_list':ramp_list,
            'role':role,
            'Nmeas':Nmeas,
            'pause': threading.Event(),
            'stop': threading.Event()
        }
        self.thread_dict[thread_name]['pause'].set() #not paused when set

        daq_thread.start()

    def stop_thread(self, thread_name):
        """Stop the thread."""
        print('Stopping thread', thread_name)
        self.thread_dict[thread_name]['pause'].set() #make sure not paused
        self.thread_dict[thread_name]['stop'].set()
        # Close the DPM context.
        #self.thread_dict[thread_name]['daq_task'].cancel()
        # Clean up the thread.
        self.thread_dict[thread_name]['thread'].join()

    def pause_thread(self,thread_name):
        print("Pause thread",thread_name)
        self.thread_dict[thread_name]['pause'].clear()

    def resume_thread(self,thread_name):
        print("Resume thread",thread_name)
        self.thread_dict[thread_name]['pause'].set()

    def stop_all_threads(self):
        for t in self.thread_dict:
            self.stop_thread(t)

    def get_list_of_threads(self):
        return [key for key in self.thread_dict.keys() if not self.thread_dict[key]['stop'].is_set()]
    
    def build_set_device_list(self,devlist):
        drf_list=[]
        for dev in devlist:
            drf = f'{dev}.SETTING'
            drf_list.append(drf)
            
        return drf_list

    def get_settings_once(self,paramlist):
        if paramlist and len(paramlist)!=0:
            drf_list = self.build_set_device_list(paramlist)
        else:
            print('Device list empty - abort')
            return
        nominals= acsys.run_client(read_once, drf_list=drf_list)
        return nominals
    
    def apply_settings_once(self,paramlist,values,role):
        if paramlist and len(paramlist)!=0:
            drf_list = self.build_set_device_list(paramlist)
        else:
            print('Device list empty. Abort')
            return

        acsys.run_client(set_once, drf_list=drf_list, value_list=values,settings_role=role) 

    def readList(self,filename):
        try:
            file = open(r'%s'%filename)
            lines = file.readlines()
            read_list = []
            for line in lines:
                if line.find('//') !=-1:
                    continue
                devs = [dev.strip('\n') for dev in line.split(',') if (dev.find(':')!=-1 or dev.find('_')!=-1) and isinstance(dev,str)] 
                [read_list.append(dev) for dev in devs]

        except:
            read_list = []
            print('Read device list empty')
        return read_list
        

    def fill_write_dataframe(self,data,read_list,filename):
        df = pd.DataFrame.from_records(data)
        devlist = df.name.unique()
        dflist=[]
        for dev in read_list:
            if dev in devlist:
                dfdev= df[df.name==dev][['stamp','data']]
                dfdev['stamp']= pd.to_datetime(dfdev['stamp'])
                dfdev['TS']=dfdev['stamp']
                dfdev.rename(columns={'data':dev, 'TS':'%s Timestamp'%dev},inplace=True)
                dfdev.set_index('stamp').reset_index(drop=False, inplace=True)
                dflist.append(dfdev)        
        
        ddf = reduce(lambda  left,right: pd.merge_asof(left,right,on=['stamp'],direction='nearest',tolerance=pd.Timedelta('10ms')), dflist)
        ddf.drop(columns=['stamp'], inplace=True)
        print( ddf.head() )
        
        #today = date.today().isoformat()
        ddf.to_csv('%s'%(filename),index_label='idx')

    def fill_write_dataframe_oneTS(self,data,read_list,filename):
        df = pd.DataFrame.from_records(data)
        devlist = df.name.unique()
        
        dflist=[]
        for dev in read_list:
            if dev in devlist:
                dfdev= df[df.name==dev][['stamp','data']]
                dfdev['stamp']= pd.to_datetime(dfdev['stamp'])
                #dfdev['stamp'] = dfdev['stamp'].dt.strftime('%d%m%Y')
                dfdev.rename(columns={'data':dev,'stamp':'Time'},inplace=True)
                dfdev.set_index('Time').reset_index(drop=False, inplace=True)
                dflist.append(dfdev)        
        
        ddf = reduce(lambda  left,right: pd.merge_asof(left,right,on=['Time'],direction='nearest',tolerance=pd.Timedelta('10ms')), dflist)
        print( ddf.head() )
        
        #today = date.today().isoformat()
        ddf.to_csv('%s'%(filename),index=False)
