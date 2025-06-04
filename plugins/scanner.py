import acsys.dpm
import threading
import asyncio
import time
import os
import pandas as pd
from functools import reduce
import datetime as dt


async def set_once(con,drf_list,value_list,settings_role, debug=False):
    #settings = [None]*len(drf_list)
    if debug: print (f'set_once() was passed drf_list: {drf_list}\n, value_list:{value_list}')

    async with acsys.dpm.DPMContext(con) as dpm:
        await dpm.enable_settings(role=settings_role)
        for i, dev in enumerate(drf_list):
            await dpm.add_entry(i, dev+'@N')
        await dpm.start()
        setpairs = list(enumerate(value_list))
        await dpm.apply_settings(setpairs)

        replies = []
        async for reply in dpm.replies():
            if reply.isReading :
                print (f'Setting reply: {reply.data}.')
                replies.append(reply)
            elif reply.isStatus:
                print(f'Status: {reply}')
                replies.append(reply)
            if len(replies) == len(drf_list):
                break

        if debug: print('settings applied: ',value_list)

    return None

async def read_once(con,drf_list, sample_events={'default':'@i'}, debug=False):
    if debug: print (f'read_once() was passed list:{drf_list} and sample_event:{sample_event}.')
    readings = [None]*len(drf_list)
    # Optional DPMContext kwarg: dpm_node='DPM09'
    async with acsys.dpm.DPMContext(con) as dpm:
        for i in range(len(drf_list)):
            devname = drf_list[i]
            if devname in list(sample_events.keys()):
                sample_event = sample_events[devname]
            else: sample_event = sample_events['default']
            if debug: print(f'Will add dpm entry {drf_list[i]+sample_event}.')
            await dpm.add_entry(i, drf_list[i]+sample_event)
            await dpm.start()

        async for reply in dpm:
            if reply.isStatus: print(f'Status: {reply}')
            else:  readings[reply.tag]=reply.data
            if readings.count(None) ==0:
                if debug: print ('readings.count(None) ==0. Breaking out of read_once()')
                break
    return readings

