"""Badger environment for a virtual accelerator built from a MAD-X lattice.

The lattice file is parsed by MAD-X (via cpymad) and converted to an xtrack
Line, which serves as the fast re-simulatable machine model.  Tunable
variables and readable observables are deduced automatically from the loaded
lattice; the companion interface (VirtualAccelerator_MADXSuiteInterface)
translates channel names into reads/writes on the lattice and its twiss results.

IMPORTANT: MAD-X deferred expressions (e.g., constants used in calculated values)
are evaluated at lattice load time when converting to xtrack.  So when variables are
changed via set_variables(), this Environment creates a new MAD-X instance with
updated parameter values (written to a temporary lattice file) to ensure functional
expressions are re-evaluated correctly.  The xtrack Line is then rebuilt from this
updated MAD-X sequence.
"""

import logging
import re
from pathlib import Path
from typing import Any, Optional

import numpy as np
import xtrack as xt
import yaml
from cpymad.madx import Madx

from badger import environment
from badger.errors import BadgerEnvVarError, BadgerNoInterfaceError

logger = logging.getLogger(__name__)

# Element strength attributes considered tunable knobs (when not driven by a
# deferred expression -- see _deduce_variables).
TUNABLE_ELEMENT_ATTRS = ['k0', 'k1', 'k2', 'k3', 'k4']

# MAD-X predefined global constants (pi, particle masses, the MAD-X version
# number, ...).  cpymad/xtrack carry them into line.vars, but they are physics
# constants, not machine knobs.
MADX_PREDEFINED_CONSTANTS = frozenset([
    'version', 'pi', 'twopi', 'degrad', 'raddeg', 'e',
    'emass', 'pmass', 'nmass', 'mumass', 'amass',
    'clight', 'qelect', 'hbar', 'erad', 'prad', 'true', 'false',
])

# Ring-wide optics quantities the interface can read from the twiss results.
GLOBAL_OPTICS_OBSERVABLES = [
    'qx', 'qy',            # betatron tunes
    'dqx', 'dqy',          # chromaticities
    'beta_x', 'beta_y',    # beta functions at s=0
    'alpha_x', 'alpha_y',  # alpha functions at s=0
    'disp_x', 'disp_y',    # dispersion at s=0
    'dpx', 'dpy',          # dispersion derivative at s=0
]


class Environment(environment.Environment):
    name = 'VirtualAccelerator_MADXSuite'

    # Populated IN PLACE by create_VA() once the lattice is loaded.  Badger
    # 1.5.4's factory.load_plugin binds aliases to these exact objects before
    # instantiating the environment, so they must be mutated (clear/update,
    # slice assignment), never re-bound.
    variables = {}
    observables = []

    debug: bool = False
    lattice_filename: str = ''
    sequence_name: str = 'full'
    # Reference momentum fallback, used only if the lattice's BEAM statement
    # does not define one.  Default: Mu2e Delivery Ring protons.
    beam_p0c_eV: float = 8.89e9
    # Variable bounds: value * (1 +/- rel_range) around the current value,
    # or +/- zero_half_range for knobs currently at zero.
    rel_range: float = 0.1
    zero_half_range: float = 0.1
    # Case-insensitive regex that marks beam position monitor elements.
    bpm_name_pattern: str = 'bpm'
    # '<observable>-SETPOINT' targets as an inline-YAML mapping string,
    # e.g. '{"qx": 9.65, "qy": 9.74}'.  Design values recorded at load time are
    # used for any observable not listed here.  This is a string (not a
    # dict) because the Badger 1.5.4 GUI param editor rebuilds param types
    # from the values and crashes on dict- or list-valued params.
    setpoints: str = ''

    # Runtime state (pydantic private attributes, not settable via config)
    # Note: xtrack's deferred_expressions=True evaluates MAD-X expressions at
    # conversion time and doesn't maintain dynamic dependencies.  When variables
    # change, we re-load the lattice into MAD-X with updated parameter values
    # (via a temporary file) to ensure deferred expressions are re-evaluated.
    _line: Optional[Any] = None  # xtrack Line for fast twiss calculations
    _madx: Optional[Any] = None  # cpymad Madx object (re-created on variable changes)
    _particle_ref: Optional[Any] = None  # xtrack reference particle (stored for re-conversion)
    _twiss: Optional[Any] = None  # cached twiss results
    _sequence_name_matched: Optional[str] = None  # MAD-X sequence name (case-insensitive match)
    _setpoints: Optional[dict] = None  # parsed from the 'setpoints' string

    def __init__(self, **data):
        # Badger's factory (badger.factory.load_plugin) instantiates
        # environments as Environment(interface=intf, params=configs), where
        # configs is the whole plugin configs.yaml dict and the field values
        # live in configs['params'].  Badger routines instead pass the field
        # values directly as keyword arguments.
        factory_configs = data.pop('params', None)
        if isinstance(factory_configs, dict):
            for key, value in factory_configs.get('params', {}).items():
                if key in type(self).model_fields:
                    data.setdefault(key, value)

        super().__init__(**data)
        self._setpoints = self._parse_setpoints(self.setpoints)
        self.create_VA()

    @staticmethod
    def _parse_setpoints(setpoints_str: str) -> dict[str, float]:
        """Parse the 'setpoints' param (inline-YAML mapping string)."""
        if not setpoints_str.strip():
            return {}
        parsed = yaml.safe_load(setpoints_str)
        if not isinstance(parsed, dict):
            raise ValueError(
                "The 'setpoints' parameter must be an inline-YAML mapping, "
                f"e.g. '{{qx: 9.65, qy: 9.74}}'; got: {setpoints_str!r}"
            )
        return {str(name): float(value) for name, value in parsed.items()}

    # ------------------------------------------------------------------ #
    # Lattice loading and deduction
    # ------------------------------------------------------------------ #

    def create_VA(self):
        """Load the MAD-X lattice and build the xtrack Line virtual machine.

        The lattice is loaded into MAD-X (via cpymad), a beam is attached,
        and the sequence is applied.  The MAD-X sequence is converted to an
        xtrack Line for fast twiss calculations.  The MAD-X object is stored
        for later use in re-loading the lattice with updated parameter values.
        """
        if not self.lattice_filename:
            raise ValueError(
                "The 'lattice_filename' parameter is required "
                "(path to a MAD-X lattice file)."
            )
        lattice_path = Path(self.lattice_filename)
        if not lattice_path.is_file():
            raise FileNotFoundError(f'MAD-X lattice file not found: {lattice_path}')

        logger.info(f'Loading MAD-X lattice {lattice_path}')
        mad = Madx(stdout=None if self.debug else False)
        mad.call(str(lattice_path))

        # Look up the requested sequence, case-insensitively.
        available = list(mad.sequence.keys())
        matched = next(
            (s for s in available if s.lower() == self.sequence_name.lower()), None
        )
        if matched is None:
            raise ValueError(
                f"Sequence '{self.sequence_name}' not found in {lattice_path}. "
                f'Available sequences: {available}'
            )
        self._sequence_name_matched = matched

        # Ensure a beam is attached before USE.  A bare BEAM command keeps the
        # values from any BEAM statement in the lattice file.
        mad.beam()
        mad.use(sequence=matched)

        # Store the cpymad Madx object for proper deferred expression handling.
        # xtrack's deferred_expressions=True evaluates expressions at conversion
        # time and doesn't maintain dependencies, so we need MAD-X for variable
        # changes that affect optics.
        self._madx = mad

        self._line = xt.Line.from_madx_sequence(
            mad.sequence[matched], deferred_expressions=True
        )

        # Reference particle from the lattice's BEAM when it defines a
        # momentum (cpymad reports mass/pc in GeV); otherwise the field default.
        beam = mad.sequence[matched].beam
        if beam.pc > 0:
            self._line.particle_ref = xt.Particles(
                mass0=beam.mass * 1e9, q0=beam.charge, p0c=beam.pc * 1e9
            )
        else:
            logger.info(
                f'Lattice defines no beam momentum; using p0c = {self.beam_p0c_eV} eV protons'
            )
            self._line.particle_ref = xt.Particles(
                mass0=xt.PROTON_MASS_EV, q0=1, p0c=self.beam_p0c_eV
            )
        # Store particle reference for later restoration after re-conversion
        self._particle_ref = self._line.particle_ref

        # In-place population of the class-level lists (see comment at the
        # class attributes above).
        type(self).variables.clear()
        type(self).variables.update(self._deduce_variables())
        type(self).observables[:] = self._deduce_observables()

        # Twiss of the pristine lattice: its optics are the design values,
        # recorded as default setpoints for '<name>-SETPOINT' observables.
        design_twiss = self._compute_twiss()
        self._record_default_setpoints(design_twiss)

        self._twiss = self._compute_twiss()

    def _update_madx_variables(self, variable_inputs: dict[str, float]):
        """Update MAD-X variables by creating a temporary lattice file with updated values.

        xtrack's deferred_expressions=True evaluates MAD-X expressions at conversion
        time and doesn't maintain dynamic dependencies. To ensure deferred expressions
        are re-evaluated when variables change, we:

        1. Read the original lattice file
        2. Replace each variable's definition with the new value
        3. Create a temporary MAD-X file with the updated values
        4. Create a new MAD-X instance from the temp file
        5. Rebuild the xtrack Line from the updated MAD-X sequence

        Args:
            variable_inputs: Dict mapping variable names to their new values.
        """
        import tempfile
        import os
        import re

        # Read the original lattice file
        with open(self.lattice_filename, 'r') as f:
            lines = f.readlines()

        # For each variable to change, find its definition and replace the value
        modified_lines = []
        changed_vars = set()

        for line in lines:
            modified_line = line
            # Try to match variable definitions like "I_DQD = 240.6;"
            for var_name, new_value in variable_inputs.items():
                # Pattern: variable_name = <old_value>;
                pattern = rf'^\s*{re.escape(var_name)}\s*=\s*[\d.\-eE+]+\s*;'
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    # Replace with the new value, preserving format
                    # Find the old value and replace it
                    old_value = match.group(0).split('=')[1].strip().rstrip(';')
                    modified_line = line.replace(old_value, str(new_value))
                    changed_vars.add(var_name)
                    break
            modified_lines.append(modified_line)

        # Write to temp file
        temp_lattice_path = os.path.join(
            tempfile.gettempdir(),
            f'madx_lattice_{os.getpid()}_{id(self)}.madx'
        )

        with open(temp_lattice_path, 'w') as f:
            f.writelines(modified_lines)

        logger.info(f'Created temporary MAD-X file with updated variables: {temp_lattice_path}')
        if changed_vars:
            logger.info(f'Changed variables: {changed_vars}')
        else:
            logger.warning(f'No variables found in lattice file: {variable_inputs.keys()}')

        # Create a new MAD-X instance from the temporary file
        mad = Madx(stdout=None if self.debug else False)
        mad.call(temp_lattice_path)

        # Re-apply the sequence
        mad.use(sequence=self._sequence_name_matched)

        # Store the new cpymad Madx object
        self._madx = mad

        # Rebuild xtrack Line from the updated MAD-X sequence
        self._line = xt.Line.from_madx_sequence(
            mad.sequence[self._sequence_name_matched], deferred_expressions=True
        )

        # Restore the reference particle (lost during re-conversion)
        self._line.particle_ref = self._particle_ref

        # Clean up the temporary file
        try:
            os.remove(temp_lattice_path)
        except OSError:
            logger.warning(f'Could not remove temporary file: {temp_lattice_path}')

    def _compute_twiss(self):
        """Compute periodic 4d twiss of the ring using the xtrack Line.

        Returns None if the optics are unstable or twiss fails.
        """
        try:
            return self._line.twiss(method='4d')
        except Exception as e:
            logger.warning(f'Twiss failed (unstable optics?): {e}')
            return None

    @staticmethod
    def _is_internal_var(name: str) -> bool:
        """True for line.vars entries that are not physical knobs.

        't_turn_s' is the simulation clock (time within the turn, written by
        tracking itself); names like '__0__' or '__vary_default' are internals
        of xtrack's deferred-expression engine; names starting with '__' are
        xtrack bookkeeping; the rest are MAD-X predefined constants carried
        along by the conversion (pi, particle masses, etc.).
        """
        return (
            name.startswith('__')
            or name == 't_turn_s'
            or name in MADX_PREDEFINED_CONSTANTS
        )

    def _bounds_around(self, value: float) -> list[float]:
        """Bounds centered on the current value, ordered low-to-high."""
        if value == 0.0:
            return [-self.zero_half_range, self.zero_half_range]
        lo = value * (1 - self.rel_range)
        hi = value * (1 + self.rel_range)
        # For negative values the products come out swapped.
        return [min(lo, hi), max(lo, hi)]

    def _deduce_variables(self) -> dict:
        """Infer the tunable knobs from the loaded lattice.

        Knobs come from two sources:
        - line.vars entries (MAD-X global variables like I_DQD, I_DQF, etc.).
          These may be power supply currents, fudge factors, or other parameters
          that control element strengths via deferred expressions.
        - element strength attributes (k0..k4) that are NOT driven by a
          deferred expression.  Expression-driven attributes are excluded
          because the controlling variable is already exposed as a knob.

        Note: Variables that control element strengths through MAD-X deferred
        expressions (e.g., G_DQ206 = ... * I_DQD * ...) are included here.
        When such a variable is changed, the environment re-loads the lattice
        with the updated value to ensure MAD-X re-evaluates all dependent expressions.
        """
        variables = {}

        for var_name in self._line.vars.keys():
            if self._is_internal_var(var_name):
                continue
            value = self._line.vars.val[var_name]
            if not isinstance(value, (int, float, np.integer, np.floating)):
                continue
            variables[var_name] = self._bounds_around(float(value))

        element_refs = self._line.element_refs
        for element_name, element in self._line.element_dict.items():
            for attr in TUNABLE_ELEMENT_ATTRS:
                if not hasattr(element, attr):
                    continue
                value = getattr(element, attr)
                if not isinstance(value, (int, float, np.integer, np.floating)):
                    continue
                if getattr(element_refs[element_name], attr)._expr is not None:
                    continue
                variables[f'{element_name}.{attr}'] = self._bounds_around(float(value))

        logger.info(f'Deduced {len(variables)} variables from the lattice')
        return variables

    def _deduce_observables(self) -> list:
        """Infer the readable observables from the loaded lattice."""
        observables = list(GLOBAL_OPTICS_OBSERVABLES)
        observables += [f'{name}-SETPOINT' for name in GLOBAL_OPTICS_OBSERVABLES]

        pattern = re.compile(self.bpm_name_pattern, re.IGNORECASE)
        monitor_names = [
            name for name in self._line.element_names if pattern.search(name)
        ]
        for name in monitor_names:
            observables.append(f'{name}.x')
            observables.append(f'{name}.y')

        logger.info(
            f'Deduced {len(observables)} observables from the lattice '
            f'({len(monitor_names)} monitors matched pattern '
            f'{self.bpm_name_pattern!r})'
        )
        return observables

    def _record_default_setpoints(self, design_twiss):
        """Record design optics as fallback '<name>-SETPOINT' targets.

        Setpoints supplied via the 'setpoints' parameter take precedence.
        The design values from the pristine lattice (after load, before any
        changes) are used as default targets for '<name>-SETPOINT' observables.
        """
        if not self.interface or design_twiss is None:
            return
        design_values = self.interface.get_values(
            GLOBAL_OPTICS_OBSERVABLES, self._line, design_twiss, debug=self.debug
        )
        for name, value in design_values.items():
            if value is not None:
                self._setpoints.setdefault(name, float(value))

    # ------------------------------------------------------------------ #
    # Badger environment API
    # ------------------------------------------------------------------ #

    def get_variables(self, variable_names: list[str]) -> dict[str, float]:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_settings(
            variable_names, self._line, debug=self.debug
        )

    def set_variables(self, variable_inputs: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError

        # When we have a MAD-X object, update it directly for proper deferred
        # expression handling. xtrack's deferred_expressions=True evaluates
        # expressions at conversion time and doesn't maintain dynamic dependencies.
        # We create a new MAD-X instance with updated parameters via a temporary
        # lattice file to ensure all deferred expressions are re-evaluated.
        if self._madx is not None:
            self._update_madx_variables(variable_inputs)

        # Update the xtrack Line via the interface (for element attributes that
        # are not driven by deferred expressions, and to keep line.vars in sync)
        self.interface.set_values(variable_inputs, self._line, debug=self.debug)

        # The optics change whenever a knob moves; refresh the cached twiss.
        self._twiss = self._compute_twiss()

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        if self._twiss is None:
            self._twiss = self._compute_twiss()
        return self.interface.get_values(
            observable_names,
            self._line,
            self._twiss,
            setpoints=self._setpoints,
            debug=self.debug,
        )

    def get_bounds(self, variable_names: list[str]) -> dict[str, list[float]]:
        """Bounds for deduced variables, plus on-the-fly bounds for valid
        channels the user adds in the GUI variable table."""
        bounds = {}
        for name in variable_names:
            if name not in type(self).variables:
                value = self._read_channel_value(name)
                if value is None:
                    raise BadgerEnvVarError(
                        f'{name} is not a tunable variable of this lattice'
                    )
                type(self).variables[name] = self._bounds_around(value)
            bounds[name] = type(self).variables[name]
        return bounds

    def _read_channel_value(self, name: str) -> Optional[float]:
        """Current value of a line variable or element attribute channel;
        None if the name does not refer to one."""
        if name in self._line.vars.keys():
            if self._is_internal_var(name):
                return None
            value = self._line.vars.val[name]
            if isinstance(value, (int, float, np.integer, np.floating)):
                return float(value)
            return None

        if '.' in name:
            element_name, attr = name.split('.', 1)
            element = self._line.element_dict.get(element_name)
            if element is not None and hasattr(element, attr):
                value = getattr(element, attr)
                if isinstance(value, (int, float, np.integer, np.floating)):
                    return float(value)
        return None

    # ------------------------------------------------------------------ #
    # End of Environment class
    # ------------------------------------------------------------------ #
