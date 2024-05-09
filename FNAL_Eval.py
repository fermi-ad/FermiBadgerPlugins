from xopt import VOCS, Evaluator, Xopt
from xopt.generators.bayesian import UpperConfidenceBoundGenerator

import math
from scanner import scanner
import argparse
import requests


devs = ['Z:CUBE_X', 'Z:CUBE_Y', 'Z:CUBE_Z', 'Z:CUBE']

# define variables and function objectives
vocs = VOCS(
    variables={devs[0]: [-3, 3],
               devs[1]: [-3, 3]
               },
    objectives={"Z:CUBE": "MAXIMIZE"},
)

def gauss2D (input_dict):
    x0sq = math.pow( 0.5 - input_dict['Z:CUBE_X'], 2.)
    x1sq = math.pow(-0.7 - input_dict['Z:CUBE_Y'], 2.)
    sig = 1.0
    g= 1./(sig * math.sqrt(2.0 * math.pi))*math.exp( (x0sq + x1sq)/ (2.0*math.pow(sig, 2.0)))
    g= math.exp( -(x0sq + x1sq) / (2.0*math.pow(sig, 2.0)))
    print (input_dict['Z:CUBE_X'],' and ',input_dict['Z:CUBE_Y'],'  got us to ',g)
    return {'Z:CUBE': g}

def sq2D (input_dict):
    x0sq = math.pow( 0.5 - input_dict['Z:CUBE_X'], 2.)
    x1sq = math.pow(-0.7 - input_dict['Z:CUBE_Y'], 2.)
    g= x0sq * x1sq
    print (input_dict['Z:CUBE_X'],' and ',input_dict['Z:CUBE_Y'],'  got us to ',g)
    return {'Z:CUBE': g}


# Does this get the VOCS as an input?  What is the dictionary my evaluate method should expect? {}
# Innputs: a dict of variables (as the VOCS has)
# Outputs: a dict of the result returned (VOCS objective)
def set_and_get(inputs):
    role='testing' #'settings' #
    sc = scanner(role)

    # apply settings for all variables
    sc.apply_settings_once(list(inputs.keys()), list(inputs.values()), role=role)

    ### SNEAKY PART ###
    # Read back what we set...
    set_vals = sc.get_settings_once(list(inputs.keys()))
    print (f'set_and_get found values: {set_vals}')
    compute_me = {}
    for i, key in enumerate (inputs.keys()):
        compute_me[key] = set_vals[i]
    # ...and compute what we should get, from those input values.
    found_result = sq2D(compute_me) # gauss2D(compute_me)
    # Now sneak that value into the objective device
    sc.apply_settings_once(list(found_result.keys()), list(found_result.values()), role=role)
    ### END SNEAKY PART
    
    results = {
        "Z:CUBE": sc.get_settings_once(["Z:CUBE"])
    }
    
    return results

evaluator = Evaluator(function=set_and_get)
generator = UpperConfidenceBoundGenerator(vocs=vocs)
X = Xopt(evaluator=evaluator, generator=generator, vocs=vocs, dump_file='dump_file.yml')


print (f'Acquire some random points to initialize')
X.random_evaluate(5)
print (X.data)

nsteps = 15
for i in range(nsteps):
    # do the optimization step
    X.step()
    model = X.generator.train_model()
    fig, ax = X.generator.visualize_model(n_grid=100)
