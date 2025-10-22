from badger import environment
from badger.errors import BadgerNoInterfaceError
from typing import Any, Optional
import numpy as np
import xobjects as xo
import xtrack as xt  # tracking module of Xsuite
from pydantic import ConfigDict

class Environment(environment.Environment):
    name = "SimpleVirtualAccelerator"

    variables = { # Also may be taken as Observables
        "qd01" = [],
        "qf05" = [],
        "qd11" = [],
        "qf15" = [],
        "qd21" = [],
        "qf25" = [],
        "qd31" = [],
        "qf35" = [],
        "qd41" = [],
        "qf45" = [],
        "qd51" = [],
        "qf55" = [],
        "qd61" = [],
        "qf65" = [],
        "qd71" = [],
        "qf75" = [],
    }
    observables = [ # elements to be used as Constraints or Observables
        "Q_X",
        "Q_Y"
    ]
    debug:         bool= False

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
        # ...and then the ring of cells:
        self.xt_env['kqf']=0.8
        self.xt_env['kqd']=-0.8
        self.ring=self.xt_env['n_bends']//2* self.cell
        
        # Use 1 GeV protons, and some initial spread of phase space for them
        self.ring.particle_ref=xt.Particles(mass0=xt.PROTON_MASS_EV, p0c=1e9)  # Mass eV/c^2 Momentum in eV/c
        self.p0=self.ring.build_particles(x=np.linspace(-0.001,0.001,11),y=np.linspace(-0.001,0.001,11)) # Should take these from named class parameters at initialization.
        
        # # Get the initial Twiss parameters
        self.init_twiss = self.ring.twiss4d(init='periodic')
        return 

    def set_quads(self, quad_settings_dict = {}):
        for i, element in enumerate(self.ring.elements):
            element_name = self.ring.element_names[i]    # declared/auto name in the line
            element_type = type(element).__name__        # class name (Drift, Quadrupole, etc.)
            if isinstance(element, xt.Quadrupole):
                print (f'{element_name}{i:0>2d}')
    
    
    def __init__(self, interface=None, params=None):
        super().__init__()
        self.create_VA()
        self.set_quads()
        # Inspect the virtual accelerator
        #print (self.init_twiss)
        #for name, element in self.ring.element_dict.items():
        #    print(f'Element name: {name}, Element type: {type(element)}, Element: {element}')
        
        
    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self.debug: print ('SimpleVirtualAccelerator asking for variables:', variable_names)
        # Interface SimpleVirtualAccelerator handles reading out the values of lattice elements' properties. 
        return self.interface.get_settings(variable_names, debug=self.debug) 

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            if self.debug: print ("not self.interface: {self.interface}.")
            raise BadgerNoInterfaceError
        # Interface SimpleVirtualAccelerator handles setting the values of lattice elements' properties.
        self.interface.set_values(settable_devices, debug=self.debug)

    def get_observables(self, observable_names: list[str]) -> dict:        
        if not self.interface:
            raise BadgerNoInterfaceError

        if self.debug: print ('get_observables() will ask for values of ', get_these_observables)
        # Interface SimpxleVirtualAccelerator runs XSuite.
        result = self.interface.get_values(get_these_observables,
                                           debug=self.debug)
        return result







