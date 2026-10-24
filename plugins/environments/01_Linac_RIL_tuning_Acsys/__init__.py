from badger import environment
from badger.errors import BadgerNoInterfaceError
from typing import Dict
from periodic import unwrap
from supply_limits import (BulkPSLimits, OBSERVABLE_PREFIX as BULK_PS_PREFIX, bulk_ps_observable,
                           bulk_ps_observables, clip_to_bulk_ps_limits)
from mults import Mult, expand_mults, is_mult, mult_name, mult_members, OOB_PREFIX
from pydantic import PrivateAttr

# Bulk power supplies: each feeds a few trims and trips off if they draw too much
# together. Sources A and B and MEBT Q1 and Q2 each have their own bulk supply; the two
# sources must not interfere. Source A's supply limits the sum of the positive currents
# and, separately, the magnitude of the sum of the negative ones, to 8 A each; the
# others limit the sum of |I|. TODO: their 7.0 A is a stand-in pending expert
# confirmation of each bulk supply's rating. Module level so the observables below
# can be listed from it.
_BULK_PS = {
    'SourceATrims': {'positive': 8.0, 'negative': 8.0,
                     'devices': ['L:ATRMHU', 'L:ATRMVU', 'L:ATRMHD', 'L:ATRMVD']},
    'SourceBTrims': {'limit': 7.0, 'devices': ['L:BTRMHU', 'L:BTRMVU', 'L:BTRMHD', 'L:BTRMVD']},
    'MEBTQ1trims':  {'limit': 7.0, 'devices': ['L:MUQ1H', 'L:MUQ1V', 'L:MDQ1H', 'L:MDQ1V']},
    'MEBTQ2trims':  {'limit': 7.0, 'devices': ['L:MUQ2H', 'L:MUQ2V', 'L:MDQ2H', 'L:MDQ2V']},
}


class Environment(environment.Environment):
    name = "01_Linac_RIL_tuning_Acsys"
    variables = { # Also may be taken as Observables
        "L:ATRMHU": [-4.0, 4.0],
        "L:ATRMVU": [-4.0, 4.0],
        "L:ATRMHD": [-4.0, 4.0],
        "L:ATRMVD": [-4.0, 4.0],
        "L:LTRMH" : [-4.0, 4.0],
        "L:LTRMV" : [-4.0, 4.0],

        "L:ASOL" : [300.0, 500],
        "L:LSOL" : [300.0, 500],

        "L:BTRMHU": [-4.0, 4.0],
        "L:BTRMVU": [-4.0, 4.0],
        "L:BTRMHD": [-4.0, 4.0],
        "L:BTRMVD": [-4.0, 4.0],

        "L:BSOL" : [300.0, 500],

        "L:MUQ1" : [ 250.0, 300.0],
        "L:MUQ2" : [ 225.0, 275.0],
        "L:MDQ1" : [ 200.0, 250.0],
        "L:MDQ2" : [ 150.0, 180.0],
        # Mults (console-style knobs): integer step count in the knob's range; each member quad is
        # written as as_found + coefficient * step * steps (see mults).
        "mult:MUQ": [-10, 10],
        "mult:MDQ": [-10, 10],


        "L:MUQ1H" : [-4.0, 4.0],
        "L:MUQ1V" : [-4.0, 4.0],

        "L:MUQ2H" : [-4.0, 4.0],
        "L:MUQ2V" : [-4.0, 4.0],

        "L:MDQ1H" : [-4.0, 4.0],
        "L:MDQ1V" : [-4.0, 4.0],

        "L:MDQ2H" : [-4.0, 4.0],
        "L:MDQ2V" : [-4.0, 4.0],

        # RF phases. Periodic (see periods below) but with deliberate operating limits,
        # so the bounds stay tight rather than two periods wide.
        "L:RFQPAH" : [ 185.0, 225.0],
        "L:RFBPAH" : [ 100.0, 300.0],
        "L:V5QSET": [-40.0, -30.0],

        "L:D72TMH": [-4.5, 4.0],
        "L:D72TMV": [-4.5, 4.0],
        "L:D73TMH": [-4.5, 4.0],
        "L:D73TMV": [-4.5, 4.0],
        "L:D74TMH": [-4.5, 4.0],
        "L:D74TMV": [-4.5, 4.0],
         
    }
    observables = [ # Also used as Constraints and Observables
        "L:TUNRAD",
        "L:TK1RAD", "L:TK4RAD", "L:D7LMSM",
        "G:LINEFF",
        "L:ATOR", "L:BTOR" ,"L:TO1IN", "L:TO3IN","L:TO5OUT" ,"L:D7TOR",
        "B:BLMLAM", "B:BLMQ3",
        "B:BLMS06", "B:BLMS13", "B:BLM125",
        "B:BOOEFF", "B:BLM011",
        
        "L:D73BPV-SETPOINT", "L:D74BPV-SETPOINT", "B:VPQ2-SETPOINT", # for the live data.
        "L:D73VPA", "L:D74VPA", "L:Q2VPA", # for integrated data, updated each SC.

        "L:DELM18", "L:D00LM", "L:D0VLM",
        "L:D11LM", "L:D12LM", "L:D13LM", "L:D14LM",
        "L:D21LM", "L:D22LM", "L:D23LM", "L:D24LM",
        "L:D31LM", "L:D32LM", "L:D33LM", "L:D34LM",
        "L:D41LM", "L:D42LM", "L:D43LM", "L:D44LM",
        "L:D51LM", "L:D52LM", "L:D53LM", "L:D54LM",
        "L:D61LM", "L:D62LM", "L:D63LM", "L:D64LM",
        "L:D71LM", "L:D72LM", "L:D73LM", "L:D74LM",
        "L:DELM15", "L:DELM13", "L:DELM1", "L:DELM12", "L:DELM11", "L:DELM5", "L:DELM6", "L:DELM7",
        "L:DELM8", "L:DELM2", "L:DELM3", "L:DELM9", "L:DELM4",
        "VTrajError_SumSqBPM_calc", 
        "W_SumLosses", 
        "DummySumSq",
        # Each bulk supply's budget(s): BulkPS_<group> (sum |I|), or BulkPS_<group>_Pos and
        # _Neg for one with separate + and - limits. Listed from the defaults in _BULK_PS.
        *bulk_ps_observables(_BULK_PS),
        # fraction of the last mult step lost to a member's hard bounds (0 good, 1 = member could not move)
        "MultOOB_MUQ", "MultOOB_MDQ",
    ]
    #sample_event:  str = '@e,52,e,0'
    sample_events: Dict[str, str] = {'default':'@e,52,e,0', 'B:BOOEFF': '@e,1f,e,0'}
    settings_role: str = 'ril_tuning_fake'
    debug:         bool= False
    # {reading device: period} for phase-like devices, in the device's own units.
    periods:       Dict[str, float] = {'L:RFQPAH': 360.0, 'L:RFBPAH': 360.0, 'L:V5QSET': 360.0}
    # Bulk power supplies (see _BULK_PS above). set_variables clips the largest current in a
    # budget toward zero to stay under its limit; each budget is also an observable.
    BulkPS_Limit: BulkPSLimits = _BULK_PS
    # Mults: {name: {step: size, members: {DEV: coefficient}}}. Variable mult:<name> is the integer
    # step count; member = as_found + coefficient * step * steps, clipped to the member's bounds with
    # the lost fraction reported as MultOOB_<name>. Operators adjust steps and members here.
    # Coefficients 20.0 and step size 0.05 confirmed by the user on 2026-10-08.
    mults: Dict[str, Mult] = {
        'MUQ': {'step': 0.05, 'members': {'L:MUQ1': 20.0, 'L:MUQ2': 20.0}},
        'MDQ': {'step': 0.05, 'members': {'L:MDQ1': 20.0, 'L:MDQ2': 20.0}}}
    _as_found:   dict = PrivateAttr(default_factory=dict)   # member settings at first touch of a mult (run start)
    _mult_steps: dict = PrivateAttr(default_factory=dict)   # {name: int} last step count applied
    _mult_oob:   dict = PrivateAttr(default_factory=dict)   # {name: lost fraction} from the last step
    #setpoints:     Dict[str, float] = {'defaults': None}
    setpoints:     Dict[str, float | None] = {'defaults': None,
                           'L:D73BPH':  1.2,
                           'L:D73BPV': -0.53,
                           'L:D74BPH':  0.341,
                           'L:D74BPV': -1.7,
                           'B:HPQ2':    1.348,
                           'B:VPQ2':  16.2}
    w_sumsq:       Dict[str, float] = {"L:DELM18": 1., "L:D00LM": 1., "L:D0VLM": 1.,
                           "L:D11LM": 1., "L:D12LM": 1., "L:D13LM": 1., "L:D14LM": 1.,
                           "L:D21LM": 1., "L:D22LM": 1., "L:D23LM": 1., "L:D24LM": 1.,
                           "L:D31LM": 1., "L:D32LM": 1., "L:D33LM": 1., "L:D34LM": 1.,
                           "L:D41LM": 1., "L:D42LM": 1., "L:D43LM": 1., "L:D44LM": 1.,
                           "L:D51LM": 1., "L:D52LM": 1., "L:D53LM": 1., "L:D54LM": 1.,
                           "L:D61LM": 1., "L:D62LM": 1., "L:D63LM": 1., "L:D64LM": 1.,
                           "L:D71LM": 1., "L:D72LM": 1., "L:D73LM": 1., "L:D74LM": 1.,
                           "L:DELM15": 1., "L:DELM13": 1., "L:DELM1": 1., "L:DELM12": 1., "L:DELM11": 1., "L:DELM5": 1., "L:DELM6": 1., "L:DELM7": 1.,
                           "L:DELM8": 1., "L:DELM2": 1., "L:DELM3": 1., "L:DELM9": 1., "L:DELM4": 1.}

    
    def _capture_as_found(self, mult_vars):
        # as-found settings of every mult member, read once per run (first touch of any mult)
        if not mult_vars or self._as_found: return
        self._as_found = dict(self.interface.get_settings(mult_members(self.mults), debug=self.debug))

    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('RIL_tuning asking for variables:', variable_names)
        # Interface BasicAcsysInterface handles (read,set) pairs and optional tolerances.
        mult_vars = [n for n in variable_names if is_mult(n)]
        self._capture_as_found(mult_vars)
        values = {v: float(self._mult_steps.get(mult_name(v), 0)) for v in mult_vars}
        device_names = [n for n in variable_names if not is_mult(n)]
        if device_names:
            values.update(self.interface.get_settings(device_names, debug=self.debug))
        # A periodic setting may be reported on another branch (e.g. -179 for 181);
        # move it onto the branch nearest the middle of the declared bounds.
        for name in variable_names:
            if name in self.periods:
                lo, hi = self.variables[name]
                values[name] = unwrap(values[name], (lo + hi) / 2, self.periods[name])
        return values

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            if self.debug: print ("not self.interface: {self.interface}.")
            raise BadgerNoInterfaceError
        mult_vars = [n for n in settable_devices if is_mult(n)]
        if mult_vars:
            self._capture_as_found(mult_vars)
            settable_devices, steps, oob = expand_mults(settable_devices, self.mults,
                                                        self._as_found, self.variables)
            self._mult_steps.update(steps)
            self._mult_oob.update(oob)
        settable_devices = clip_to_bulk_ps_limits(settable_devices, self.BulkPS_Limit,
                                                 lambda devs: self.interface.get_settings(devs, debug=self.debug))
        # Interface BasicAcsysInterface handles (read,set) pairs and optional tolerances.
        self.interface.set_values(settable_devices, settings_role=self.settings_role,
                                  periods=self.periods, debug=self.debug)

    def get_observables(self, observable_names: list[str]) -> dict:        
        if not self.interface:
            raise BadgerNoInterfaceError
        calc_these = []
        if 'VTrajError_SumSqBPM_calc' in observable_names: # Ensure the inputs to the calc will be returned
            for input_dev in ["L:D73BPV-SETPOINT", "L:D74BPV-SETPOINT", "B:VPQ2-SETPOINT"]:
                if not input_dev in observable_names: observable_names.append(input_dev)

        if 'W_SumLosses' in observable_names: # Ensure the inputs to the calc will be returned
            for input_dev in list(self.w_sumsq.keys()):
                if not input_dev in observable_names: observable_names.append(input_dev)
            observable_names.remove('W_SumLosses') # only removes first occurrence. 

        bulk_ps_names = [n for n in observable_names if n.startswith(BULK_PS_PREFIX)]
        for n in bulk_ps_names: observable_names.remove(n)
        oob_names = [n for n in observable_names if n.startswith(OOB_PREFIX)]
        for n in oob_names: observable_names.remove(n)

        get_these_observables = []
        for observable_name in observable_names:
            if observable_name.count("_calc") > 0: calc_these.append(observable_name)
            else: get_these_observables.append(observable_name)
            
        if self.debug: print ('get_observables() will ask for values of ', get_these_observables)
        # Interface BasicAcsysInterface handles (read,set) pairs and optional tolerances.
        result = self.interface.get_values(get_these_observables,
                                           sample_events=self.sample_events,
                                           setpoints   =self.setpoints,
                                           periods     =self.periods,
                                           debug=self.debug)
        if len(calc_these)>0:
            if 'VTrajError_SumSqBPM_calc' in calc_these:
                sumsqerror = 0.0
                for sqerror in ["L:D73BPV-SETPOINT", "L:D74BPV-SETPOINT", "B:VPQ2-SETPOINT"]:
                    sumsqerror += result[sqerror]
                result['VTrajError_SumSqBPM_calc'] = sumsqerror
        if "W_SumLosses" in observable_names and len(self.w_sumsq.keys())>0:
            sumsq = 0.0
            for dev_read, weight in self.w_sumsq.items():
                if dev_read not in result.keys(): print (f'Unable to find {dev_read} among the read-back results: {list(result.keys())}')
                sumsq += pow(weight * (1.0+result[dev_read]), 2.0) # Add unity, then scale by the weight, then square and add to the sum.
            result['W_SumLosses'] = sumsq
        for name in bulk_ps_names:
            result[name] = bulk_ps_observable(self.BulkPS_Limit, name,
                                              lambda devs: self.interface.get_settings(devs, debug=self.debug))
        for name in oob_names:
            result[name] = self._mult_oob.get(name[len(OOB_PREFIX):], 0.0)

        return result







