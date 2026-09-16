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

    # Same empty-list guard as read_once() -- see comment there. A settings
    # session with zero entries would otherwise hang the same way.
    if not drf_list:
        if debug: print('set_once() called with an empty drf_list; doing nothing.')
        return None

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

async def read_once(con,drf_list, sample_events={'default':'@i'}, debug=False, timeout=15.0):
    if debug: print (f'read_once() was passed list:{drf_list} and sample_events:{sample_events}.')

    # GUARD: an empty drf_list means "nothing was actually selected/checked
    # yet" -- this happens routinely, e.g. when Badger's full GUI calls
    # set_vrange() -> update_init_table() -> fill_curr_in_init_table() right
    # after an environment is (re)selected but before any variables have
    # been chosen into the routine. A DPM session opened with zero entries
    # never gets a reply (nothing was requested), so without this guard the
    # code below would open the session anyway and hang until our timeout,
    # surfacing a confusing "timed out waiting for DPM replies for: []"
    # error for what is actually a normal, expected empty-selection state.
    if not drf_list:
        if debug: print('read_once() called with an empty drf_list; returning [] with no DPM session.')
        return []

    readings = [None]*len(drf_list)
    # Optional DPMContext kwarg: dpm_node='DPM09'

    async def _do_read():
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
                    if debug: print (f'readings.count(None) ==0. Breaking out of read_once() and returning {readings}')
                    break

    # DIAGNOSTIC/SAFETY NET (added while chasing the "Automatic mode hangs
    # forever" bug): without a timeout, a DPM session that never gets a
    # reply blocks this coroutine -- and therefore the whole Qt GUI thread,
    # since acsys.run_client() runs this via loop.run_until_complete() on
    # the calling thread -- with no way to recover short of force-quitting.
    # Bounding it turns a silent, unkillable freeze into a clear, timed-out
    # exception naming exactly which device(s) never answered, which is
    # our next real diagnostic signal if the hang recurs.
    try:
        await asyncio.wait_for(_do_read(), timeout=timeout)
    except asyncio.TimeoutError:
        missing = [drf_list[i] for i in range(len(drf_list)) if readings[i] is None]
        got = {
            drf_list[i]: readings[i]
            for i in range(len(drf_list))
            if readings[i] is not None
        }
        print(
            f"read_once() TIMED OUT after {timeout}s waiting on DPM replies. "
            f"No reply received for: {missing}. Replies received before timeout: {got}"
        )
        raise TimeoutError(
            f"BasicAcsysInterface.read_once() timed out after {timeout}s waiting "
            f"for DPM replies for: {missing}"
        )

    return readings

