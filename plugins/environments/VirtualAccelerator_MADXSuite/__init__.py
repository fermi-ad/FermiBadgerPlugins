"""Badger environment for a virtual accelerator built from a MAD-X lattice.

The lattice file is parsed by MAD-X (via cpymad) and converted to an xtrack
Line, which serves as the fast re-simulatable machine model.  Tunable
variables and readable observables are deduced automatically from the loaded
lattice; the companion interface (VirtualAccelerator_MADXSuiteInterface)
translates channel names into reads/writes on the Line and its twiss results.
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
    # slice assignment), never rebound.
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
    # e.g. '{qx: 9.65, qy: 9.74}'.  Design values recorded at load time are
    # used for any observable not listed here.  This is a string (not a
    # dict) because the Badger 1.5.4 GUI param editor rebuilds param types
    # from the values and crashes on dict- or list-valued params.
    setpoints: str = ''
    lattice_settings_filename: str = 'VirtualAccelerator_MADXSuite_lattice_settings.yaml'
    randomize_settings: bool = False
    randomize_amount: float = 0.01  # relative half-width of the randomization

    # Runtime state (pydantic private attributes, not settable via config)
    _line: Optional[Any] = None
    _twiss: Optional[Any] = None
    _sequence_name_matched: Optional[str] = None
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
        """Load the MAD-X lattice and build the xtrack Line virtual machine."""
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

        # In-place population of the class-level lists (see comment at the
        # class attributes above).
        type(self).variables.clear()
        type(self).variables.update(self._deduce_variables())
        type(self).observables[:] = self._deduce_observables()

        # Twiss of the pristine lattice: its optics are the design values,
        # recorded as default setpoints for '<name>-SETPOINT' observables.
        design_twiss = self._compute_twiss()
        self._record_default_setpoints(design_twiss)

        # Restore machine state from a previous session, or record the
        # current (design) state for the next one.
        if Path(self.lattice_settings_filename).is_file():
            self._load_settings_from_file()
        else:
            self._save_settings_to_file()

        if self.randomize_settings:
            self._randomize_settings()
            self._save_settings_to_file()

        self._twiss = self._compute_twiss()

    def _compute_twiss(self):
        """Periodic 4d twiss of the ring; None if the optics are unstable."""
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
        of the deferred-expression engine; the rest are MAD-X predefined
        constants carried along by the conversion.
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

        Knobs come from two places:
        - line.vars entries (the lattice's deferred-expression variables),
          excluding xtrack's internal bookkeeping names;
        - element strength attributes (k0..k4) that are NOT driven by a
          deferred expression.  Expression-driven attributes are excluded
          because the controlling variable is already exposed as a knob and a
          direct write would be silently overwritten the next time the
          expression is re-evaluated.
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
    # Lattice settings persistence
    # ------------------------------------------------------------------ #

    def _save_settings_to_file(self):
        """Save the current value of every deduced knob to the settings file."""
        settings = {}
        for name in type(self).variables:
            value = self._read_channel_value(name)
            if value is not None:
                settings[name] = value

        logger.info(
            f'Saving {len(settings)} lattice settings to '
            f'{self.lattice_settings_filename}'
        )
        with open(self.lattice_settings_filename, 'w') as f:
            yaml.safe_dump(settings, f)

    def _load_settings_from_file(self):
        """Restore knob values from the settings file."""
        with open(self.lattice_settings_filename, 'r') as f:
            settings = yaml.safe_load(f) or {}

        # Ignore bookkeeping keys from older settings files.
        settings = {k: v for k, v in settings.items() if not k.startswith('_')}

        logger.info(
            f'Loading {len(settings)} lattice settings from '
            f'{self.lattice_settings_filename}'
        )
        self._apply_settings(settings)

    def _apply_settings(self, settings: dict[str, float]):
        """Write knob values through the interface's set pathway."""
        if not settings:
            return
        if not self.interface:
            logger.warning(
                'No interface attached; skipping application of '
                f'{len(settings)} lattice settings'
            )
            return
        self.interface.set_values(settings, self._line, debug=self.debug)

    def _randomize_settings(self):
        """Perturb every knob uniformly within value * (1 +/- randomize_amount)."""
        rng = np.random.default_rng()
        settings = {}
        for name in type(self).variables:
            value = self._read_channel_value(name)
            if value is None:
                continue
            lo, hi = sorted(
                (
                    value * (1 - self.randomize_amount),
                    value * (1 + self.randomize_amount),
                )
            )
            settings[name] = float(rng.uniform(lo, hi))

        logger.info(f'Randomizing {len(settings)} lattice settings')
        self._apply_settings(settings)
