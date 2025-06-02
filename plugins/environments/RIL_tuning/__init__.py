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
        "L:MDQ2" : [ 150.0, 200.0],

        "L:RFQPAH" : [ 210.0, 215.0], # Or are there reading,setting,(optional)setting? Like "L:C7PHAS,L:L7PADJ,tol3@0.45"?
        "L:RFBPAH" : [ 226.0, 227.0],

        "L:MUQ1H" : [-5.0, 0.0],
        "L:MUQ1V" : [-5.0, 0.0],

        "L:MUQ2H" : [-1.5,-0.5],
        "L:MUQ2V" : [-0.5, 0.1],

        "L:MDQ2H" : [-0.5, 0.5],
        "L:MDQ2V" : [ 0.3, 0.7]
        
    }
    observables = [ # Also used as Constraints and Observables
        "L:TUNRAD",
        "L:TK1RAD", "L:TK4RAD", "L:D7LMSM",
        "L:DELM5",# top of the DS face of the Lambertson
        "L:D23LM","L:D34LM","L:D72LM", # These sum in quadr.?
        "G:LINEFF",
        "B:BLMS06", "B:BLMS13", "B:BLM125",
        "L:ATOR", "L:TO1IN", "L:TO3IN", "L:D7TOR",
        "DummySumSq"
    ]
    sample_event:  str = '@e,52,e,0'
    settings_role: str = 'ril_tuning_fake'
    debug:         bool= False
    setpoint:      str = 'hold'
    #mults:         str = 'multL:MUQ1*20,L:MUQ2*20;'
    
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('RIL_tuning asking for variables:', variable_names)
        # Interface BasicAcsysInterface handles (read,set) pairs and optional tolerances.
        #return self.interface.get_values(variable_names, sample_event=self.sample_event, debug=self.debug)
        return self.interface.get_settings(variable_names, debug=self.debug) # sample_event=self.sample_event,

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            if self.debug: print ("not self.interface: {self.interface}.")
            raise BadgerNoInterfaceError
        self.interface.set_values(settable_devices, settings_role=self.settings_role, debug=self.debug)

    #def get_observables(self, observable_names: list[str], sample_event=self.sample_event) -> dict:
    def get_observables(self, observable_names: list[str]) -> dict:        
        if not self.interface:
            raise BadgerNoInterfaceError
        modified_observables = observable_names #[x+self.sample_event for x in observable_names]
        if self.debug: print ('get_observables() will ask for values of ', modified_observables)
        return self.interface.get_values(modified_observables, sample_event=self.sample_event, setpoint_str=self.setpoint, debug=self.debug)
        







