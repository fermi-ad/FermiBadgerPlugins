# Project Context

When working with this codebase, prioritize readability over cleverness. Ask clarifying questions before making architectural changes.

## About This Project

Conda environment: FermiBadger_env

Developing a new, working functionality for Badger, the GUI frontend to Xopt, the Bayesian optimization package for particle accelerators.  
We are developing the Badger Environment in plugins/environments/VirtualAccelerator_MADXSuite and its Badger Interface in plugins/interfaces/VirtualAccelerator_MADXSuiteInterface.  The user of Badger opens a tuning template such as tuning_templates/VirtualAccelerator_MADXSuite_example where the VirtualAccelerator_MADXSuite Environment is selected, and the ```lattice_filename``` parameter is used to load the lattice file into MAD by way of XSuite, which allows rapid re-simulation of the accelerator under different parameter value combinations.  These Badger plugins automatically infer from the lattice the elements which can be varied (variables) and those which can be read out (objectives). Objectives can be combined in mathematical functions to make more sophisticated objectives. 
- Badger codebase is at https://github.com/xopt-org/Badger/, presently version 1.5.4
- Xopt codebase if needed is at https://github.com/xopt-org/Xopt
- Xsuite packages: xobjects and xtrack from https://github.com/xsuite

## Caveats

When testing for full functionality, do not set sleep or timeout limits.  The Badger GUI takes an indeterminate time to load, and longer still for the user to select and load a tuning template + Environmnent. 

## Standards

- pydantic is strictly enforced by Badger

## Session history

Running work history lives in docs/ — do NOT load these by default, only when
resuming work or when the current task needs the history:

- docs/progress.md — current phase status, verified facts, next steps
- docs/log.md — chronological session log
- memory/MEMORY.md - pointers to agentic session history and handoff guide file

Update these at the end of each work session.
