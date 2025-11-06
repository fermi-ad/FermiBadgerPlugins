from badger import environment
from badger.errors import BadgerNoInterfaceError
from typing import Any, Optional
import numpy as np
import xobjects as xo
import xtrack as xt  # tracking module of Xsuite
from pydantic import ConfigDict
from pathlib import Path
import yaml

class Environment(environment.Environment):
    name = "SimpleVirtualAccelerator"
    variables = { # Also may be taken as Observables
        "kqd" : [-1, 1],
        "kqf" : [-1, 1],
    }
    observables = [ # elements to be used as Constraints or Observables
        "qx",
        "qy"
    ]
    debug:            bool = True
    quad_randomness: float = 0.01
    quad_k_list:      list = ['kqd', 'kqf']
    settings_filename:  str = 'SimpleVirtualAccelerator_settings.yaml'
    randomize_settings: bool = True

    xt_env:     Optional[Any] = None 
    cell:       Optional[Any] = None 
    ring:       Optional[Any] = None 
    p0:         Optional[Any] = None 
    init_twiss: Optional[Any] = None 
    

    def create_VA (self):
        # Toy ring segment
        self.xt_env=xt.Environment()
        self.xt_env.vars.default_to_zero = True
        self.xt_env['pi']= np.pi
        self.xt_env['n_bends']= 16
        self.xt_env['ang_mb'] = '2*pi/n_bends'
        self.xt_env['l_mb'] = 1.2
        self.xt_env['l_mq'] = 0.4
        
        #Dipoles
        self.xt_env.new('mb', xt.Bend, length='l_mb', angle='ang_mb', k0_from_h=True) # k0 scaled magnetic field k_0 = q/P B_y 
        # Quadrupole families with different strengths
        self.xt_env.new('mq', xt.Quadrupole, length='l_mq')
        self.xt_env.new('qf', 'mq', k1='kqf') # Focusing quadrupole  k1>0
        self.xt_env.new('qd', 'mq', k1='kqd') # De-focusing quadrupole k1<0
        #Markers
        self.xt_env.new("start_cell",xt.Marker)
        self.xt_env.new("end_cell",xt.Marker);
        # Build the cell
        self.cell = self.xt_env.new_line(
            length=6, # 6 m length
            components=[
                self.xt_env.place('start_cell', at=0),
                self.xt_env.place('qd', at=0.2),   # refer to the center by default
                self.xt_env.place('mb', at=1.7),
                self.xt_env.place('qf', at=3.2),
                self.xt_env.place('mb', at=4.7),
                self.xt_env.place('end_cell',at=6),
            ]
        )
        # Load settings from the settings file into self.xt_env
        if Path(self.settings_filename).is_file(): 
            self.load_settings_from_file()
        else: # or, set them in xt_env, and save to the (new) file
            self.xt_env['kqf']=0.8
            self.xt_env['kqd']=-0.8
        if self.randomize_settings:
            self.randomize_quad_settings()
        self.save_settings_to_file(set_random=False)

        # ...and then build the ring of cells:
        self.ring=self.xt_env['n_bends']//2 * self.cell
        
        # Use 1 GeV protons, and some initial spread of phase space for them
        self.ring.particle_ref=xt.Particles(mass0=xt.PROTON_MASS_EV, p0c=1e9)  # Mass eV/c^2 Momentum in eV/c
        self.p0=self.ring.build_particles(x=np.linspace(-0.001,0.001,11),y=np.linspace(-0.001,0.001,11)) # Should take these from named class parameters at initialization.
        
        # # Get the initial Twiss parameters
        self.init_twiss = self.ring.twiss4d(init='periodic')
        return 

    def get_quad_k1_vals_from_xt_env(self):
        quad_settings = {}
        for quadvar in self.quad_k_list:
            quad_settings[quadvar] = self.xt_env[quadvar]
        return quad_settings

    #def set_quads(self, quad_k_settings):
    #    #assert (sorted(list(quad_settings.keys())) ==
    #    for quad_k1_name, k1_val in quad_k_settings.items():
    #        self.xt_env[quad_k1_name] = k1_val
    #        #if self.debug: print (f'Set {quad_k1_name} to {k1_val}.')
    
    def print_quads(self):
        for i, element in enumerate(self.ring.elements):
            element_name = self.ring.element_names[i]    # declared/auto name in the line
            element_type = type(element).__name__        # class name (Drift, Quadrupole, etc.)
            if isinstance(element, xt.Quadrupole):
                print (f'{element_name}{i:0>2d}: {element.k1:.6f}')

    # Change settings randomly to new values within current value * (1+/-self.quad_randomness)
    def randomize_quad_settings(self):
        if self.debug: print ('Randomizing quad settings.')
        quad_settings = self.get_quad_k1_vals_from_xt_env()
        for quadname in self.quad_k_list: #quad_settings.keys():
            setting_val = quad_settings[quadname]
            rand_setting = np.random.uniform(setting_val*(1.0 - self.quad_randomness),
                                             setting_val*(1.0 + self.quad_randomness) )
            self.xt_env[quadname] = rand_setting
        return 

    def save_settings_to_file(self, set_random=False):
        yamldict = {}
        # if the file exists, load in its contents
        if Path(self.settings_filename).is_file():
            with open(self.settings_filename, 'r') as fyaml:
                yamldict = yaml.safe_load(fyaml)
        # Set the _randomize entry
        yamldict['_randomize'] = set_random
        # Now move over the settings from the xt_env to this dictionary
        for quad_kname in self.quad_k_list:
            yamldict[quad_kname] = float(self.xt_env[quad_kname])
        if self.debug: print (f'-- Gonna write out yamldict: ',yamldict, f'\n ....as {self.settings_filename}.')
        #...and write out the updated yaml file
        with open(self.settings_filename, 'w') as fyaml:
            yaml.dump(yamldict, fyaml)
        return

    def load_settings_from_file(self):
        with open(self.settings_filename, 'r') as fyaml:
            settings_dict = yaml.safe_load(fyaml)
        for setting_name, setting_val in settings_dict.items():
            if setting_name == '_randomize': self.randomize_settings = setting_val
            else:
                print (f'++ Want to set {setting_name} to new value {setting_val} in xt_env.')
                self.xt_env[setting_name] = setting_val
        return

    def __init__(self, **data):
        print ('Called __init__ for SimpleVirtualAccelerator environment with \ndata: ', data)
        super().__init__(**data) 
        if self.debug: print ('super.init called. About to create_VA()')
        self.create_VA()
        self.print_quads()

        
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface or self.interface is None:
            raise BadgerNoInterfaceError
        if self.debug: print ('SimpleVirtualAccelerator asking for variables:', variable_names)
        # Interface SimpleVirtualAccelerator handles reading out the values of lattice elements' properties. 
        return self.interface.get_settings(variable_names, self.xt_env, debug=self.debug) 

    def get_observables(self, observable_names: list[str]) -> dict:        
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('SimpleVirtualAccelerator.get_observables() will ask for values of ', observable_names)
        # Interface SimpxleVirtualAccelerator runs XSuite.
        tw=self.ring.twiss4d()
        result = self.interface.get_values(observable_names, tw)
        return result

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            #if self.debug: print ("not self.interface: {self.interface}.")
            raise BadgerNoInterfaceError
        # Interface SimpleVirtualAccelerator handles setting the values of lattice elements' properties.
        self.interface.set_values(settable_devices, self.xt_env)








