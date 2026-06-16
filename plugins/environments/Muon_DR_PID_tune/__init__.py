import numpy as np
from badger import environment
from badger.errors import BadgerNoInterfaceError

class Environment(environment.Environment):
    name = "Muon_DR_PID_tune"
    variables = { # Also may be taken as Observables
        "Z:QDPID_P_SRS": [-.10, 0.10],
        "Z:QDPID_I_SRS": [-.10, 0.10],
        "Z:QDPID_D_SRS": [-.10, 0.10],
         
    }
    observables = [ # Also used as Constraints and Observables
        "DR_SDF_calc",
    ]
    spill_length: int = 430
    sample_events: dict = {'default':'@e,83,e,0', 'DR_SDF': '@e,83,e,2000'}
    settings_role: str = 'fake'
    debug:         bool= False
    #setpoints:     dict = {'defaults': None}
    setpoints:     dict = {'defaults': None}
    w_sumsq:       dict = {}

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
        if 'DR_SDF' in observable_names: # Ensure the inputs to the calc will be returned
            for observable_name in ['Z:INSPLL_1_SRS[:]', 'Z:ITGSIG_1_SRS[:]']: 
                if not observable_name in observable_names:
                    observable_names.append(observable_name)

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
            if 'DR_SDF_calc' in calc_these:
                # Calculate the SDF from the ITGSIG_1_SRS values
                # First use Z:INSPLL_1_SRS[:] to determine the first and last samples in the sum
                # Get the index of the firrst non-zero sample in Z:INSPLL_1_SRS[:]
                i_begin_spill = 0
                for i, sample in enumerate(result['Z:INSPLL_1_SRS[:]']):
                    if sample != 0:
                        i_begin_spill = i
                        break
                # Get the slice of the ITGSIG_1_SRS values that correspond to the spill
                = result['Z:ITGSIG_1_SRS[:]'][i_begin_spill-1:i_begin_spill+self.spill_length]
                # Calculate the variance of the ITGSIG_1_SRS values in the spill using numpy, and the SDF from that
                result['DR_SDF_calc'] = 1.0 / (1.0 + np.var(itgsig_spill))
    
        return result







