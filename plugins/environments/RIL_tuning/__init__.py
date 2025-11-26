from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "RIL_tuning"
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

        #"multL:MUQ1*20,L:MUQ2*20",
        "L:MUQ1" : [ 250.0, 300.0],
        "L:MUQ2" : [ 225.0, 275.0],
        "L:MDQ1" : [ 200.0, 250.0],
        "L:MDQ2" : [ 150.0, 180.0],


        "L:MUQ1H" : [-4.0, 4.0],
        "L:MUQ1V" : [-4.0, 4.0],

        "L:MUQ2H" : [-4.0, 4.0],
        "L:MUQ2V" : [-4.0, 4.0],

        "L:MDQ1H" : [-4.0, 4.0],
        "L:MDQ1V" : [-4.0, 4.0],

        "L:MDQ2H" : [-4.0, 4.0],
        "L:MDQ2V" : [-4.0, 4.0],

        "L:RFQPAH" : [ 185.0, 225.0], # Or are there reading,setting,(optional)setting? Like "L:C7PHAS,L:L7PADJ,tol3@0.45"?
        "L:RFBPAH" : [ 210.0, 230.0],
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
        "DummySumSq"
    ]
    #sample_event:  str = '@e,52,e,0'
    sample_events: dict = {'default':'@e,52,e,0', 'B:BOOEFF': '@e,1f,e,0'}
    settings_role: str = 'ril_tuning_fake'
    debug:         bool= False
    #setpoints:     dict = {'defaults': None}
    setpoints:     dict = {'defaults': None,
                           'L:D73BPH':  1.2,
                           'L:D73BPV': -0.53,
                           'L:D74BPH':  0.341,
                           'L:D74BPV': -1.7,
                           'B:HPQ2':    1.348,
                           'B:VPQ2':  16.2}
    w_sumsq:       dict = {"L:DELM18": 1., "L:D00LM": 1., "L:D0VLM": 1.,
                           "L:D11LM": 1., "L:D12LM": 1., "L:D13LM": 1., "L:D14LM": 1.,
                           "L:D21LM": 1., "L:D22LM": 1., "L:D23LM": 1., "L:D24LM": 1.,
                           "L:D31LM": 1., "L:D32LM": 1., "L:D33LM": 1., "L:D34LM": 1.,
                           "L:D41LM": 1., "L:D42LM": 1., "L:D43LM": 1., "L:D44LM": 1.,
                           "L:D51LM": 1., "L:D52LM": 1., "L:D53LM": 1., "L:D54LM": 1.,
                           "L:D61LM": 1., "L:D62LM": 1., "L:D63LM": 1., "L:D64LM": 1.,
                           "L:D71LM": 1., "L:D72LM": 1., "L:D73LM": 1., "L:D74LM": 1.,
                           "L:DELM15": 1., "L:DELM13": 1., "L:DELM1": 1., "L:DELM12": 1., "L:DELM11": 1., "L:DELM5": 1., "L:DELM6": 1., "L:DELM7": 1.,
                           "L:DELM8": 1., "L:DELM2": 1., "L:DELM3": 1., "L:DELM9": 1., "L:DELM4": 1.}

    #mults:         str = 'multL:MUQ1*20,L:MUQ2*20;'
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('RIL_tuning asking for variables:', variable_names)
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
        if 'VTrajError_SumSqBPM_calc' in observable_names: # Ensure the inputs to the calc will be returned
            for input_dev in ["L:D73BPV-SETPOINT", "L:D74BPV-SETPOINT", "B:VPQ2-SETPOINT"]:
                if not input_dev in observable_names: observable_names.append(input_dev)

        if 'W_SumLosses' in observable_names: # Ensure the inputs to the calc will be returned
            for input_dev in list(self.w_sumsq.keys()):
                if not input_dev in observable_names: observable_names.append(input_dev)
            observable_names.remove('W_SumLosses') # only removes first occurrence. 

        get_these_observables = []
        for observable_name in observable_names:
            if observable_name.count("_calc") > 0: calc_these.append(observable_name)
            else: get_these_observables.append(observable_name)
            
        if self.debug: print ('get_observables() will ask for values of ', get_these_observables)
        # Interface BasicAcsysInterface handles (read,set) pairs and optional tolerances.
        result = self.interface.get_values(get_these_observables,
                                           sample_events=self.sample_events,
                                           setpoints   =self.setpoints,
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

        return result







