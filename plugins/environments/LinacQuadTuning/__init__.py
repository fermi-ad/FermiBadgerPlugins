from badger import environment
from badger.errors import BadgerNoInterfaceError

# LinacLMs = ["L:DELM18", "L:D00LM", "L:D00VLM",
#             "L:D11LM", "L:D12LM", "L:D13LM", "L:D14LM",
#             "L:D21LM", "L:D22LM", "L:D23LM", "L:D24LM",
#             "L:D31LM", "L:D32LM", "L:D33LM", "L:D34LM",
#             "L:D41LM", "L:D42LM", "L:D43LM", "L:D44LM",
#             "L:D51LM", "L:D52LM", "L:D53LM", "L:D54LM",
#             "L:D61LM", "L:D62LM", "L:D63LM", "L:D64LM",
#             "L:D71LM", "L:D72LM", "L:D73LM", "L:D74LM",
#             "L:DELM15", "L:DELM13", "L:DELM1", "L:DELM12", "L:DELM11", "L:DELM5", "L:DELM6", "L:DELM7",
#             "L:DELM8", "L:DELM2", "L:DELM3", "L:DELM9", "L:DELM4"]
# 

class Environment(environment.Environment):
    name = "LinacQuadTuning"
    variables = { # Also may be taken as Observables

        "L:Q01": [45.0, 185.0],
        "L:Q02": [45.0, 185.0],
        "L:Q03": [45.0, 185.0],
        "L:Q04": [45.0, 185.0],
        "L:Q11": [45.0, 185.0],
        "L:Q12": [45.0, 185.0],
        "L:Q13": [45.0, 185.0],
        "L:Q14": [45.0, 185.0],
        "L:Q21": [45.0, 185.0],
        "L:Q22": [45.0, 185.0],
        "L:Q23": [45.0, 185.0],
        "L:Q24": [45.0, 185.0],
        "L:Q31": [45.0, 185.0],
        "L:Q32": [45.0, 185.0],
        "L:Q33": [45.0, 185.0],
        "L:Q34": [45.0, 185.0],
        "L:Q41": [45.0, 185.0],
        "L:Q42": [45.0, 185.0],
        "L:Q43": [45.0, 185.0],
        "L:Q44": [45.0, 185.0],
        
        "L:QPS501": [60.0, 200.0], #- powers single quad
        "L:QPS502": [60.0, 200.0], #- powers single quad
        "L:QPS503": [60.0, 200.0], #
        "L:QPS504": [60.0, 200.0], #
        "L:QPS505": [60.0, 200.0], #
        "L:QPS506": [60.0, 200.0], #
        "L:QPS507": [60.0, 200.0], #
        "L:QPS508": [60.0, 200.0], #- failed, now running on an isolation transformer.  Should not go too high. 
        "L:QPS509": [60.0, 200.0], #
        "L:QPS510": [60.0, 200.0], #
        "L:QPS511": [60.0, 200.0], #
        "L:QPS512": [60.0, 200.0], #
        "L:QPS513": [60.0, 200.0], #- powers  single quad

    }
    observables = [ # Also used as Constraints and Observables
        "L:400SCA",
        "L:TUNRAD",
        "L:TK1RAD", "L:TK4RAD", "L:D7LMSM",
        "L:DELM5",# top of the DS face of the Lambertson
        "L:D23LM","L:D34LM","L:D72LM", # These sum in quadr.?
        "G:LINEFF",
        "L:ATOR", "L:TO1IN", "L:TO3IN", "L:D7TOR",
        "B:BLMLAM", "B:BLMQ3",
        "B:BLMS06", "B:BLMS13", "B:BLM125",
        "B:BOOEFF", "B:BLM011",
        
        #"L:D73BPV-SETPOINT", "L:D74BPV-SETPOINT", "B:VPQ2-SETPOINT", # for the live data.
        "L:D73VPA", "L:D74VPA", "L:Q2VPA", # for integrated data, updated each SC.
        #"VTrajError_SumSqBPM_calc",
        "W_SumLosses", #

        "DummySumSq"
    ]
    # Various other parameters
    sample_events: dict = {'default':'@e,0A,e,0'}
    settings_role: str = 'linac_quads'
    debug:         bool= False
    w_sumsq:       dict = {"L:DELM18": 10., "L:D00LM": 10., "L:D0VLM": 10.,
                           "L:D11LM": 10., "L:D12LM": 10., "L:D13LM": 10., "L:D14LM": 10.,
                           "L:D21LM": 10., "L:D22LM": 10., "L:D23LM": 10., "L:D24LM": 10.,
                           "L:D31LM": 10., "L:D32LM": 10., "L:D33LM": 10., "L:D34LM": 10.,
                           "L:D41LM": 10., "L:D42LM": 10., "L:D43LM": 10., "L:D44LM": 10.,
                           "L:D51LM": 10., "L:D52LM": 10., "L:D53LM": 10., "L:D54LM": 10.,
                           "L:D61LM": 10., "L:D62LM": 10., "L:D63LM": 10., "L:D64LM": 10.,
                           "L:D71LM": 10., "L:D72LM": 10., "L:D73LM": 10., "L:D74LM": 10.,
                           "L:DELM15": 10., "L:DELM13": 10., "L:DELM1": 10., "L:DELM12": 10., "L:DELM11": 10., "L:DELM5": 10., "L:DELM6": 10., "L:DELM7": 10.,
                           "L:DELM8": 10., "L:DELM2": 10., "L:DELM3": 10., "L:DELM9": 10., "L:DELM4": 10.}

    #mults:         str = 'multL:MUQ1*20,L:MUQ2*20;'
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('LinacQuadTuning asking for variables:', variable_names)
        # Interface BasicAcsysInterface handles (read,set) pairs and optional tolerances.
        return self.interface.get_settings(variable_names, debug=self.debug) # sample_event=self.sample_event,

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            if self.debug: print ("not self.interface: {self.interface}.")
            raise BadgerNoInterfaceError
        # Interface BasicAcsysInterface handles (read,set) pairs and optional tolerances.
        self.interface.set_values(settable_devices, settings_role=self.settings_role, debug=self.debug)

    def get_observables(self, observable_names: list[str]) -> dict:        
        if not self.interface:
            raise BadgerNoInterfaceError
        calc_these = []
        if 'W_SumLosses' in observable_names: # Ensure the inputs to the calc will be returned
            for input_dev in list(self.w_sumsq.keys()):
                if not input_dev in observable_names: observable_names.append(input_dev)
            observable_names.remove('W_SumLosses') # only removes first occurrence. 

        get_these_observables = [] # The list of actual devices to be read
        for observable_name in observable_names:
            if observable_name.count("_calc") > 0: calc_these.append(observable_name)
            if observable_name == 'W_SumLosses': continue # Not a real device, after all 
            else: get_these_observables.append(observable_name)
            
        if self.debug: print ('get_observables() will ask for values of ', get_these_observables)
        # Interface BasicAcsysInterface handles (read,set) pairs and optional tolerances.
        result = self.interface.get_values(get_these_observables,
                                           sample_events=self.sample_events,
                                           debug=self.debug)
        if len(self.w_sumsq.keys())>0:
            sumsq = 0.0
            for dev_read, weight in self.w_sumsq.items():
                sumsq += pow(weight * result[dev_read], 2.0)
            result['W_SumLosses'] = sumsq
        return result


