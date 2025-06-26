from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "RIL_tuning"
    variables = { # Also may be taken as Observables
        "L:ATRMHU": [ 0.0, 4.0],
        "L:ATRMVU": [-4.0, 1.0],
        "L:ATRMHD": [ 0.0, 2.0],
        "L:ATRMVD": [ 0.0, 1.0],
        "L:LTRMH" : [-1.0, 1.0],
        "L:LTRMV" : [-1.0, 1.0],

        "L:ASOL" : [410.0, 430],
        "L:LSOL" : [450.0, 480],

        #"multL:MUQ1*20,L:MUQ2*20",
        "L:MUQ1" : [ 250.0, 300.0],
        "L:MUQ2" : [ 225.0, 275.0],
        "L:MDQ1" : [ 200.0, 250.0],
        "L:MDQ2" : [ 150.0, 180.0],

        "L:RFQPAH" : [ 185.0, 225.0], # Or are there reading,setting,(optional)setting? Like "L:C7PHAS,L:L7PADJ,tol3@0.45"?
        "L:RFBPAH" : [ 210.0, 230.0],

        "L:MUQ1H" : [-5.0, 0.0],
        "L:MUQ1V" : [-5.0, 0.0],

        "L:MUQ2H" : [-1.5,-0.5],
        "L:MUQ2V" : [-0.5, 0.1],

        "L:MDQ2H" : [-0.5, 0.5],
        "L:MDQ2V" : [ 0.3, 0.7],
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
        "L:DELM5",# top of the DS face of the Lambertson
        "L:D23LM","L:D34LM","L:D72LM", # These sum in quadr.?
        "G:LINEFF",
        "L:ATOR", "L:TO1IN", "L:TO3IN", "L:D7TOR",
        "B:BLMLAM", "B:BLMQ3",
        "B:BLMS06", "B:BLMS13", "B:BLM125",
        "B:BOOEFF", "B:BLM011",
        
        "L:D73BPV-SETPOINT", "L:D74BPV-SETPOINT", "B:VPQ2-SETPOINT", # for the live data.
        "L:D73VPA", "L:D74VPA", "L:Q2VPA", # for integrated data, updated each SC.
        "VTrajError_SumSqBPM_calc", 
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

        get_these_observables = []
        for observable_name in observable_names:
            if observable_name.count("_calc") > 0: calc_these.append(observable_name)
            else: get_these_observables.append(observable_name)
            
        if self.debug: print ('get_observables() will ask for values of ', get_these_observables)
        # Interface BasicAcsysInterface handles (read,set) pairs and optional tolerances.
        result = self.interface.get_values(get_these_observables,
                                           #sample_event =self.sample_event ,
                                           sample_events=self.sample_events,
                                           #setpoint_str=self.setpoint,
                                           setpoints   =self.setpoints,
                                           debug=self.debug)
        if len(calc_these)>0:
            if 'VTrajError_SumSqBPM_calc' in calc_these:
                sumsqerror = 0.0
                for sqerror in ["L:D73BPV-SETPOINT", "L:D74BPV-SETPOINT", "B:VPQ2-SETPOINT"]:
                    sumsqerror += result[sqerror]
                result['VTrajError_SumSqBPM_calc'] = sumsqerror
        return result







