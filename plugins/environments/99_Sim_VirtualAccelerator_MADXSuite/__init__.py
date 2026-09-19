"""Badger environment for a virtual accelerator built from a MAD-X lattice.

The lattice file is parsed by MAD-X (via cpymad) and converted to an xtrack
Line, which serves as the fast re-simulatable machine model.  Tunable
variables and readable observables are deduced automatically from the loaded
lattice; the companion interface (VirtualAccelerator_MADXSuiteInterface)
translates channel names into reads/writes on the lattice and its twiss results.

Live expressions.  Most MAD-X lattices assign with '=', which MAD-X evaluates
at parse time and then forgets, so every quantity reaches the Line as a frozen
number and moving a knob changes nothing.  At load time this environment
rewrites the source to use deferred ':=' assignment (see madx_deferred.py),
which carries the formulas into xtrack's xdeps graph.  set_variables() is then
just a write to line.vars: xdeps recomputes the affected subtree, and the only
remaining per-iteration cost is the twiss itself.  The rewrite is verified
against the original file at load; if it does not reproduce it exactly, the
environment falls back to reloading MAD-X on every iteration (~40x slower).

Rings and transfer lines.  With no 'twiss_init' parameter the twiss is periodic,
as a ring requires.  Setting 'twiss_init' (betx, alfx, bety, alfy, and
optionally x, px, y, py for the incoming centroid) switches to an open-line
twiss from start to end, as a transfer line requires.

Unstable optics.  When the twiss does not solve, every twiss-derived observable
reads NaN.  The 'optics_stable' observable reads 0.0 there and 1.0 otherwise,
so a template can fence the optimizer out of that region with a constraint
'optics_stable > 0.5'.

Loading lazily.  Badger instantiates the environment with the plugin's *default*
params, once per process, purely to build the browsable variable list
(badger.factory.load_plugin).  Parsing a lattice for that is wasted work when
the routine then loads a different one, so the deduced variable bounds and
observable names are written to a '.varcache.json' sidecar beside the lattice
and the parse itself is deferred to the first call that actually needs the Line.
Delete the sidecar to force a re-deduction; it is also ignored when the lattice
file changes.

Known xtrack behaviour: changing a main bend *angle* moves neither the orbit nor
the tune, because xtrack's Bend carries the reference trajectory along with the
geometry.  Steer with corrector currents instead.
"""

import hashlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pydantic import Field

import numpy as np
import xtrack as xt
import yaml
from cpymad.madx import Madx

from badger import environment
from badger.errors import BadgerEnvVarError, BadgerNoInterfaceError

from .madx_deferred import to_deferred

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

# Global optics that only exist for a periodic (ring) solution.
RING_ONLY_OBSERVABLES = frozenset(['qx', 'qy', 'dqx', 'dqy'])

# Channels that need twiss's chromatic pass, which costs ~4x the twiss itself.
# Requested lazily in get_observables() so tune-only objectives do not pay it.
CHROMATIC_OBSERVABLES = frozenset(['dqx', 'dqy'])

# MAD-X base types that report a beam centroid, and the planes each measures.
MONITOR_PLANES = {
    'hmonitor': ('x',),
    'vmonitor': ('y',),
    'monitor': ('x', 'y'),
}

# Element attributes compared between the original and rewritten lattice when
# verifying the ':=' rewrite.
VERIFIED_ELEMENT_ATTRS = ('l', 'k1', 'k2', 'k3', 'angle', 'tilt',
                          'hkick', 'vkick', 'e1', 'e2', 'volt', 'freq', 'lag')

# Suffix of the squared-error channels the interface derives from a setpoint.
SETPOINT_SUFFIX = '-SETPOINT'

# Reads 1.0 while the twiss solves and 0.0 when it does not.  Advertised on
# every lattice, with no '-SETPOINT' twin: it is a flag to constrain
# ('optics_stable > 0.5'), not a quantity to steer towards.
OPTICS_STABLE = 'optics_stable'

# Templates carry repo-relative lattice paths ('sim_configs/.../x.madx'), which
# only resolve when Badger is launched from the repo root.  Falling back to this
# lets it be launched from anywhere.
# plugins/environments/<name>/__init__.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# A lattice's own TWISS/TRACK/PLOT statements (and MAD-X's own
# checkpoint_restart.dat) write into MAD-X's working directory using whatever
# relative filenames they specify.  Every mad.call() below chdirs MAD-X here
# first so those land in one gitignored place instead of the repo root.
SIM_OUTPUT_DIR = REPO_ROOT / 'sim_outputs'


# (resolved lattice path, sequence name) -> (Madx, design Line, matched name).
# Badger rebuilds the environment on every GUI table refresh and once more per
# optimization run; parsing the Delivery Ring takes ~10 s and copying the
# resulting Line takes 0.5 s.  Only lattices whose ':=' rewrite verified are
# cached, so the entries are never touched by the per-iteration reload path.
_LATTICE_CACHE: dict[tuple[str, str], tuple] = {}

# Sidecar holding the variable bounds and observable names deduced from a
# lattice, so a fresh process can advertise them without parsing it.  Written
# beside the lattice file, named '<lattice>.<sequence>.varcache.json'.
VARCACHE_SUFFIX = '.varcache.json'


def _new_madx(stdout) -> Madx:
    """A cpymad Madx instance chdir'd into SIM_OUTPUT_DIR.

    Keeps the TWISS/TRACK/PLOT files a lattice's own statements write (plus
    MAD-X's checkpoint_restart.dat) out of the repo root.
    """
    SIM_OUTPUT_DIR.mkdir(exist_ok=True)
    mad = Madx(stdout=stdout)
    mad.chdir(str(SIM_OUTPUT_DIR))
    return mad


def _matches(before, after) -> bool:
    """True if two MAD-X attribute values agree (numerically, to rtol=1e-12)."""
    if isinstance(before, (list, tuple)) or isinstance(after, (list, tuple)):
        return (len(before) == len(after)
                and all(_matches(a, b) for a, b in zip(before, after)))
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return bool(np.isclose(before, after, rtol=1e-12, atol=1e-15))
    return before == after


class Environment(environment.Environment):
    name = '99_Sim_VirtualAccelerator_MADXSuite'

    # Populated IN PLACE by create_VA() once the lattice is loaded.  Badger
    # 1.5.4's factory.load_plugin binds aliases to these exact objects before
    # instantiating the environment, so they must be mutated (clear/update,
    # slice assignment), never re-bound.
    variables = {}
    observables = []

    debug: bool = False
    lattice_filename: str = Field(default='sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx')
    sequence_name: str = 'full'
    # Reference momentum fallback, used only if the lattice's BEAM statement
    # does not define one.  Default: Mu2e Delivery Ring protons.
    beam_p0c_eV: float = 8.89e9
    # Variable bounds: value * (1 +/- rel_range) around the current value,
    # or +/- zero_half_range for knobs currently at zero.
    rel_range: float = 0.1
    zero_half_range: float = 0.1
    # Beam position monitors are found by MAD-X base type (monitor / hmonitor /
    # vmonitor), which needs no per-lattice configuration.  Set this to a
    # case-insensitive regex to narrow that set down by name as well.
    bpm_name_pattern: Optional[str] = Field(default=None)
    # Initial optics for an open line, as an inline-YAML mapping string or dict:
    # betx, alfx, bety, alfy, and optionally dx, dpx, dy, dpy and the incoming
    # centroid x, px, y, py.  Leave unset for a ring, which is solved
    # periodically.  A transfer line has no periodic solution and needs this.
    twiss_init: Union[Dict[str, float], str, None] = Field(default=None)
    # '<observable>-SETPOINT' targets as an inline-YAML mapping string or
    # dict, e.g. '{"qx": 9.65, "qy": 9.74}'.  Design values recorded at load
    # time are used for any observable not listed here.  Accepts both str and
    # dict to handle templates that pass dict values (the GUI's DynamicModel
    # creation uses type() which loses subtype info for dicts).
    # Note: The pydantic_editor requires Dict[K, V] with subtypes, not plain dict.
    setpoints: Union[Dict[str, float], str, None] = Field(default=None)

    # Runtime state (pydantic private attributes, not settable via config)
    _line: Optional[Any] = None  # xtrack Line for fast twiss calculations
    _madx: Optional[Any] = None  # cpymad Madx object the Line was built from
    _particle_ref: Optional[Any] = None  # xtrack reference particle (stored for re-conversion)
    _twiss: Optional[Any] = None  # cached twiss results
    _twiss_chromatic: bool = False  # whether the cached twiss has chromatic properties
    _sequence_name_matched: Optional[str] = None  # MAD-X sequence name (case-insensitive match)
    _setpoints: Optional[Dict[str, float]] = None  # parsed from the 'setpoints' param
    _twiss_init_values: Optional[Dict[str, float]] = None  # parsed from 'twiss_init'
    _use_deferred: bool = True  # False if the ':=' rewrite failed verification
    _monitor_planes: Optional[Dict[str, tuple]] = None  # monitor name -> planes it reads
    _lattice_path: Optional[Any] = None  # Path to the lattice file
    _cache_key: Optional[tuple] = None  # (resolved lattice path, sequence name)

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
        self._setpoints = self._parse_mapping(self.setpoints, 'setpoints')
        self._twiss_init_values = self._parse_mapping(self.twiss_init, 'twiss_init')
        self.create_VA()

    @staticmethod
    def _parse_mapping(
        param: Union[Dict[str, float], str, None], field: str
    ) -> dict[str, float]:
        """Parse a name -> float mapping param (inline-YAML string, dict, or None).

        Badger's pydantic editor hands these over as any of the three, so all
        three are accepted.  Used for both 'setpoints' and 'twiss_init'.
        """
        if param is None:
            return {}
        if isinstance(param, dict):
            # Already a dict - convert values to float
            return {str(name): float(value) for name, value in param.items()}
        # String case - parse from YAML
        if not param.strip():
            return {}
        parsed = yaml.safe_load(param)
        if not isinstance(parsed, dict):
            raise ValueError(
                f"The '{field}' parameter must be an inline-YAML mapping, "
                f"e.g. '{{qx: 9.65, qy: 9.74}}'; got: {param!r}"
            )
        return {str(name): float(value) for name, value in parsed.items()}

    # ------------------------------------------------------------------ #
    # Lattice loading and deduction
    # ------------------------------------------------------------------ #

    def create_VA(self):
        """Advertise this lattice's variables and observables.

        Loading is deferred when the sidecar cache can supply both lists (see
        the module docstring): Badger builds one environment per process from
        the plugin defaults just to read them, and parsing a lattice nothing
        will use costs ~10 s.  _ensure_lattice() does the parse on first use.
        """
        if not self.lattice_filename:
            raise ValueError(
                "The 'lattice_filename' parameter is required "
                "(path to a MAD-X lattice file)."
            )
        self._lattice_path = Path(self.lattice_filename)
        if not self._lattice_path.is_absolute() and not self._lattice_path.is_file():
            # The working directory wins when it has the file; this only covers
            # a launch from somewhere else.
            self._lattice_path = REPO_ROOT / self.lattice_filename
        if not self._lattice_path.is_file():
            raise FileNotFoundError(
                f'MAD-X lattice file not found: {self._lattice_path}'
            )
        # Absolute, since mad.call() passes this straight to the MAD-X
        # subprocess, whose cwd is redirected to SIM_OUTPUT_DIR (_new_madx) --
        # a path relative to the launch directory would no longer resolve.
        self._lattice_path = self._lattice_path.resolve()
        self._cache_key = (str(self._lattice_path.resolve()),
                           self.sequence_name.lower())

        if self._cache_key in _LATTICE_CACHE:
            self._ensure_lattice()  # already parsed in this process: cheap
            return

        cached = self._read_varcache()
        if cached is None:
            self._ensure_lattice()
            return

        type(self).variables.clear()
        type(self).variables.update(cached['variables'])
        type(self).observables[:] = cached['observables']
        logger.info(
            f'Advertising {len(cached["variables"])} variables and '
            f'{len(cached["observables"])} observables from the sidecar cache; '
            f'{self._lattice_path.name} will be parsed on first use'
        )

    def _ensure_lattice(self):
        """Parse the lattice if it has not been parsed yet, and deduce from it.

        The lattice source is rewritten to use deferred ':=' assignment so its
        formulas survive into xtrack's expression graph, loaded into MAD-X (via
        cpymad), given a beam, and converted to an xtrack Line.  The rewrite is
        then verified against the original file; if it does not reproduce it
        exactly, the environment falls back to reloading MAD-X per iteration.
        """
        if self._line is not None:
            return

        key = self._cache_key
        if key not in _LATTICE_CACHE:
            self._load_lattice(self._lattice_path)
            if self._use_deferred:
                _LATTICE_CACHE[key] = (self._madx, self._line,
                                       self._sequence_name_matched)
        if self._use_deferred:
            # Including right after a fresh load: the cached Line must stay at
            # the design values, so no instance ever works on it directly.
            self._reuse_cached_lattice(key)

        # In-place population of the class-level lists (see comment at the
        # class attributes above).
        type(self).variables.clear()
        type(self).variables.update(self._deduce_variables())
        type(self).observables[:] = self._deduce_observables()
        self._write_varcache()

        # Twiss of the pristine lattice: its optics are the design values,
        # recorded as default setpoints for '<name>-SETPOINT' observables.
        self._twiss = self._compute_twiss()
        self._twiss_chromatic = True
        self._record_default_setpoints(self._twiss)

    # ------------------------------------------------------------------ #
    # Sidecar cache of the deduced lists
    # ------------------------------------------------------------------ #

    def _varcache_params(self) -> dict:
        """The params, besides the lattice itself, that shape the two lists."""
        return {
            'sequence': self._cache_key[1],
            'rel_range': self.rel_range,
            'zero_half_range': self.zero_half_range,
            'bpm_name_pattern': self.bpm_name_pattern,  # which monitors
            'twiss_init': sorted(self._twiss_init_values),  # ring-only optics
        }

    def _varcache_path(self) -> Path:
        # One file per param set -- they hash into the name -- so two sets do
        # not take turns invalidating each other's cache.
        digest = hashlib.sha1(
            json.dumps(self._varcache_params(), sort_keys=True).encode()
        ).hexdigest()[:8]
        return self._lattice_path.with_name(
            f'{self._lattice_path.name}.{digest}{VARCACHE_SUFFIX}'
        )

    def _varcache_stamp(self) -> dict:
        """What a cached list must be re-deduced after: an edited lattice."""
        stat = self._lattice_path.stat()
        return {'mtime': stat.st_mtime, 'size': stat.st_size,
                **self._varcache_params()}

    def _read_varcache(self) -> Optional[dict]:
        """The sidecar's lists, or None if it is missing, stale or unreadable."""
        path = self._varcache_path()
        try:
            cached = json.loads(path.read_text())
            if cached['stamp'] != self._varcache_stamp():
                logger.info(f'Ignoring the stale sidecar cache {path.name}')
                return None
            return cached
        except FileNotFoundError:
            return None
        except Exception as error:  # a cache file must never break the load
            logger.warning(f'Ignoring unreadable sidecar cache {path.name}: {error}')
            return None

    def _write_varcache(self):
        path = self._varcache_path()
        payload = {
            'stamp': self._varcache_stamp(),
            'variables': dict(type(self).variables),
            'observables': list(type(self).observables),
        }
        try:
            # Same directory, then replace: a half-written file is never read.
            with tempfile.NamedTemporaryFile(
                mode='w', dir=path.parent, suffix=VARCACHE_SUFFIX, delete=False
            ) as handle:
                json.dump(payload, handle)
            os.replace(handle.name, path)
        except Exception as error:
            logger.warning(f'Could not write the sidecar cache {path.name}: {error}')

    def _reuse_cached_lattice(self, key):
        """Take a private copy of an already-parsed lattice.

        line.copy() carries the whole xdeps expression graph across and costs a
        twentieth of a fresh MAD-X parse plus conversion, so the GUI's habit of
        rebuilding the environment on every table refresh stops hurting.  Every
        instance goes through here, the one that did the loading included, so
        the cached Line is never written to and every copy starts from the
        design values.  The MAD-X object is shared, but
        only ever read (monitor base types); the per-iteration reload path,
        which would replace it, is not cached -- see create_VA.
        """
        mad, design_line, matched = _LATTICE_CACHE[key]
        logger.info(f'Reusing the cached load of {key[0]}')
        self._madx = mad
        self._sequence_name_matched = matched
        self._line = design_line.copy()
        self._line.particle_ref = design_line.particle_ref
        self._particle_ref = self._line.particle_ref

    def _load_lattice(self, lattice_path: Path):
        """Parse the lattice with MAD-X and convert it to an xtrack Line."""
        logger.info(f'Loading MAD-X lattice {lattice_path}')
        mad = self._load_deferred(lattice_path)

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

    def _load_deferred(self, lattice_path: Path) -> Madx:
        """Load the lattice with '=' rewritten to ':=', verified against the original.

        On any discrepancy this sets self._use_deferred False and returns a
        MAD-X built from the original source instead, so the environment still
        works (via the per-iteration reload) on a lattice the rewriter cannot
        handle.
        """
        rewritten, stats = to_deferred(lattice_path.read_text())
        logger.info(
            f"Deferred {stats['vars']} variable assignments and "
            f"{stats['attrs']} element attributes; "
            f"{len(stats['skipped'])} assignments left immediate"
        )
        for called in stats['calls']:
            logger.warning(
                'CALLed files are not rewritten, so any lattice quantity they '
                f'define stays frozen: {called}'
            )

        # Same directory as the lattice, so relative CALL/SAVE paths inside it
        # still resolve.
        with tempfile.NamedTemporaryFile(
            mode='w', dir=lattice_path.parent, suffix='.madx', delete=False
        ) as handle:
            handle.write(rewritten)
            rewritten_path = handle.name
        try:
            mad = _new_madx(None if self.debug else False)
            mad.call(rewritten_path)
        finally:
            Path(rewritten_path).unlink(missing_ok=True)

        mismatch = self._verify_rewrite(mad, lattice_path)
        if mismatch is None:
            return mad

        logger.warning(
            f'The deferred-expression rewrite of {lattice_path.name} does not '
            f'reproduce the original lattice: {mismatch}.  Falling back to '
            'reloading MAD-X on every iteration, which is far slower.'
        )
        self._use_deferred = False
        mad = _new_madx(None if self.debug else False)
        mad.call(str(lattice_path))
        return mad

    @staticmethod
    def _verify_rewrite(mad: Madx, lattice_path: Path) -> Optional[str]:
        """Describe how the rewritten lattice differs from the original, or None.

        Loads the original source into a throwaway MAD-X (a fraction of a
        second) and compares every global and every element attribute in
        VERIFIED_ELEMENT_ATTRS.  A rewrite that left nothing expression-driven
        is reported too: it parsed cleanly but did nothing.
        """
        original = _new_madx(False)
        try:
            original.call(str(lattice_path))

            for name, value in original.globals.items():
                if not _matches(value, mad.globals[name]):
                    return (f'global {name} is {value} in the original and '
                            f'{mad.globals[name]} after the rewrite')

            expression_driven = 0
            for name, element in original.elements.items():
                for attr in VERIFIED_ELEMENT_ATTRS:
                    if attr not in element.cmdpar:
                        continue
                    before = element.cmdpar[attr].value
                    after = mad.elements[name].cmdpar[attr]
                    if not _matches(before, after.value):
                        return (f'{name}.{attr} is {before} in the original '
                                f'and {after.value} after the rewrite')
                    expression_driven += after.expr is not None

            if not expression_driven:
                return 'it left no element attribute driven by an expression'
            return None
        finally:
            original.quit()

    def _update_madx_variables(self, variable_inputs: dict[str, float]):
        """Rebuild the Line from a temp lattice file carrying the new values.

        ponytail: fallback path only, used when the ':=' rewrite failed
        verification.  It costs seconds per iteration against milliseconds for
        the deferred path.  Delete it once the deferred path has been exercised
        on every lattice in sim_configs/.

        To have MAD-X re-evaluate every dependent expression, we:

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

        # Read the original lattice file -- _lattice_path, not the raw param,
        # so this agrees with create_VA() about which file that names.
        with open(self._lattice_path, 'r') as f:
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
        mad = _new_madx(None if self.debug else False)
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

    def _compute_twiss(self, chromatic: bool = True):
        """4d twiss: periodic for a ring, open start-to-end when 'twiss_init' is set.

        The chromatic pass costs roughly four times the twiss itself, so
        callers that were not asked for dqx/dqy pass chromatic=False.
        Returns None if the optics are unstable or twiss fails.
        """
        try:
            if self._twiss_init_values:
                return self._line.twiss(
                    method='4d',
                    start=xt.START,
                    end=xt.END,
                    init=xt.TwissInit(**self._twiss_init_values),
                    chrom=chromatic,
                )
            return self._line.twiss(method='4d', chrom=chromatic)
        except Exception as e:
            hint = '' if self._twiss_init_values else (
                "  If this lattice is a transfer line rather than a ring, set "
                "the 'twiss_init' parameter (betx, alfx, bety, alfy, and "
                'optionally the incoming centroid x, px, y, py).'
            )
            logger.warning(f'Twiss failed (unstable optics?): {e}{hint}')
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
            # abs(): a template carrying a negative half-range would otherwise
            # hand Badger [+h, -h] and have every bounds check reject the knob.
            return [-abs(self.zero_half_range), abs(self.zero_half_range)]
        lo = value * (1 - self.rel_range)
        hi = value * (1 + self.rel_range)
        # For negative values the products come out swapped.
        return [min(lo, hi), max(lo, hi)]

    def _deduce_variables(self) -> dict:
        """Infer the tunable knobs from the loaded lattice.

        Knobs come from two sources:
        - line.vars entries that are free, i.e. hold a number rather than an
          expression: power supply currents, calibration factors, tilts,
          lengths and offsets.
        - element strength attributes (k0..k4) that are NOT driven by a
          deferred expression.  Expression-driven attributes are excluded
          because the controlling variable is already exposed as a knob.

        Expression-driven quantities are deliberately left out of both.  After
        the ':=' rewrite they are derived outputs -- a gradient computed from a
        current, say -- and assigning one would overwrite its formula and sever
        that dependence for the rest of the session.
        """
        variables = {}

        for var_name in self._line.vars.keys():
            if self._is_internal_var(var_name):
                continue
            if self._line.vars[var_name]._expr is not None:
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

    def _deduce_monitors(self) -> dict[str, tuple]:
        """Monitor element name -> the planes it measures, by MAD-X base type.

        The element type is the portable signal; names are not ('p_dhp301' in
        one lattice, 'BPHQ2' in another).  'bpm_name_pattern', when set,
        narrows this set further by name.
        """
        pattern = (
            re.compile(self.bpm_name_pattern, re.IGNORECASE)
            if self.bpm_name_pattern
            else None
        )
        in_line = set(self._line.element_names)
        monitors = {}
        for element in self._madx.sequence[self._sequence_name_matched].elements:
            planes = MONITOR_PLANES.get(
                getattr(getattr(element, 'base_type', None), 'name', None)
            )
            if planes is None or element.name not in in_line:
                continue
            if pattern is not None and not pattern.search(element.name):
                continue
            monitors[element.name] = planes
        return monitors

    def _deduce_observables(self) -> list:
        """Infer the readable observables from the loaded lattice.

        Global optics -- tunes and chromaticities only for a ring, since an
        open line has none -- plus the beam centroid at every monitor, in the
        plane that monitor actually measures.  Any other twiss column is still
        readable by typing '<element>.<column>' into the GUI table; the
        advertised list is kept short on purpose.
        """
        is_ring = not self._twiss_init_values
        names = [
            name for name in GLOBAL_OPTICS_OBSERVABLES
            if is_ring or name not in RING_ONLY_OBSERVABLES
        ]

        self._monitor_planes = self._deduce_monitors()
        names += [
            f'{name}.{plane}'
            for name, planes in self._monitor_planes.items()
            for plane in planes
        ]

        logger.info(
            f'Deduced {len(names)} observables from the lattice '
            f'({len(self._monitor_planes)} monitors)'
        )
        return (names + [f'{name}{SETPOINT_SUFFIX}' for name in names]
                + [OPTICS_STABLE])

    def _record_default_setpoints(self, design_twiss):
        """Record the design optics as fallback '<name>-SETPOINT' targets.

        Setpoints supplied via the 'setpoints' parameter take precedence.  The
        values come from the pristine lattice, after load and before any change.
        Channels that do not read back a finite number on this lattice are
        skipped rather than poisoning an objective with NaN.
        """
        if not self.interface or design_twiss is None:
            return
        base_names = [
            name for name in type(self).observables
            if not name.endswith(SETPOINT_SUFFIX) and name != OPTICS_STABLE
        ]
        design_values = self.interface.get_values(
            base_names, self._line, design_twiss, debug=self.debug
        )
        for name, value in design_values.items():
            if value is not None and np.isfinite(value):
                self._setpoints.setdefault(name, float(value))

    # ------------------------------------------------------------------ #
    # Badger environment API
    # ------------------------------------------------------------------ #

    def get_variables(self, variable_names: list[str]) -> dict[str, float]:
        if not self.interface:
            raise BadgerNoInterfaceError
        self._ensure_lattice()
        return self.interface.get_settings(
            variable_names, self._line, debug=self.debug
        )

    def set_variables(self, variable_inputs: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        self._ensure_lattice()

        # Only when the ':=' rewrite failed verification: rebuild the whole
        # Line from a modified source so MAD-X re-evaluates the expressions.
        if not self._use_deferred:
            self._update_madx_variables(variable_inputs)

        # line.vars.update() inside the interface writes through xdeps, which
        # recomputes every dependent lattice quantity in place.
        self.interface.set_values(variable_inputs, self._line, debug=self.debug)

        # The optics have changed; twiss lazily in get_observables(), which
        # knows whether the chromatic pass is worth paying for.
        self._twiss = None

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        self._ensure_lattice()

        chromatic = bool(CHROMATIC_OBSERVABLES.intersection(
            name.removesuffix(SETPOINT_SUFFIX) for name in observable_names
        ))
        if self._twiss is None or (chromatic and not self._twiss_chromatic):
            self._twiss = self._compute_twiss(chromatic)
            self._twiss_chromatic = chromatic

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
        self._ensure_lattice()  # only reached for a name not in the cached list
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
