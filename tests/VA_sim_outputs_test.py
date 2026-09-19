"""Checks that MAD-X's own output files (TWISS/TRACK/PLOT, checkpoint_restart.dat)
land in sim_outputs/ instead of the repo root.

The Xfer400MeV lattice is the one with TWISS/TRACK/PLOT statements that write
relative-named files, which is what makes this worth checking.

Run from the repo root:
    ~/miniconda3/envs/FermiBadger_env/bin/python tests/VA_sim_outputs_test.py
"""
import importlib
import sys

sys.path.insert(0, 'plugins')

va = importlib.import_module('environments.99_Sim_VirtualAccelerator_MADXSuite')
Environment = va.Environment
from interfaces.VirtualAccelerator_MADXSuiteInterface import Interface

STRAY_NAMES = ['checkpoint_restart.dat', 'madx.ps', 'optics_400mev.dat',
               'sectormap', 'l400mevtrackoneone']

for name in STRAY_NAMES:
    stray = va.REPO_ROOT / name
    assert not stray.exists(), f'stray output file at repo root: {stray}'

env = Environment(
    interface=Interface(),
    lattice_filename='sim_configs/Xfer400MeV/B400tracking.madx',
    sequence_name='l400mev',
    twiss_init={'alfx': -0.89649, 'alfy': 0.49047, 'betx': 1.113092, 'bety': 5.6787},
)
env._ensure_lattice()

for name in STRAY_NAMES:
    stray = va.REPO_ROOT / name
    assert not stray.exists(), f'stray output file leaked to repo root: {stray}'
    written = va.SIM_OUTPUT_DIR / name
    assert written.exists(), f'expected MAD-X output missing: {written}'

print('SIM_OUTPUTS TEST PASSED')
