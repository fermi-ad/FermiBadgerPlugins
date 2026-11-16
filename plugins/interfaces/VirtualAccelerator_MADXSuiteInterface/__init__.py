"""Badger interface for the VirtualAccelerator_MADXSuite environment.

Translates Badger channel names into reads/writes on an xtrack Line and its
twiss results.  The environment owns the Line and the twiss; it passes both
into every call here.

Channel naming:
- variables:   line.vars names ('i_dsexf') or element attributes ('q_dq303.k1')
- observables: global optics ('qx', 'beta_x', ...), monitor orbit readings
               ('p_dvp302.x'), squared-error setpoint channels
               ('qx-SETPOINT'), the optics-stability flag
               ('optics_stable'), and computed channels (below)

Computed channels (added 2026-11-16), so a template can ask for a whole-ring
quantity by name:
- '<stat>(<column>@<regex>)': a statistic of one twiss column over the elements
  whose names match the regex (re.search), e.g. 'rms(x@^p_dhp)' (the horizontal
  orbit at the horizontal monitors) or 'max(betx@^d_dkk)'. Stats: rms, mean, max,
  min, maxabs. Columns: any twiss column, plus 'bbetx' and 'bbety', the beta
  beat (beta / design beta - 1).
- 'phase_x(<a>,<b>)', 'phase_y(<a>,<b>)': the phase advance from element a to a
  downstream element b, in degrees.
- 'sum(<channel>,<channel>,...)': the sum of other channels, any of them
  '-SETPOINT' channels, e.g. 'sum(dqx-SETPOINT,dqy-SETPOINT)' (one objective
  from two squared errors).
"""

import logging
import re
from typing import Any, Optional

import numpy as np
from badger import interface

logger = logging.getLogger(__name__)

SETPOINT_SUFFIX = '-SETPOINT'

STATS = {
    'rms': lambda v: float(np.sqrt(np.mean(np.square(v)))),
    'mean': lambda v: float(np.mean(v)),
    'max': lambda v: float(np.max(v)),
    'min': lambda v: float(np.min(v)),
    'maxabs': lambda v: float(np.max(np.abs(v))),
}
STAT_CHANNEL = re.compile(r'^(' + '|'.join(STATS) + r')\((\w+)@(.+)\)$')
PHASE_CHANNEL = re.compile(r'^phase_([xy])\(([\w.$]+),([\w.$]+)\)$')
SUM_CHANNEL = re.compile(r'^sum\((.+)\)$')
BEAT_COLUMNS = {'bbetx': 'betx', 'bbety': 'bety'}  # beta beat against the design
_MASKS: dict = {}  # (regex, element names) -> boolean row mask; names never change


def split_top_level(text: str) -> list[str]:
    """'a,f(b,c),d' -> ['a', 'f(b,c)', 'd']: split at commas outside parentheses."""
    parts, depth, start = [], 0, 0
    for i, c in enumerate(text):
        depth += (c == '(') - (c == ')')
        if c == ',' and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
    parts.append(text[start:].strip())
    return parts

# 1.0 while the twiss solves, 0.0 when it does not (unstable optics, no closed
# orbit).  Every other channel reads NaN there, which a generator cannot learn
# from; this one stays finite so a template can constrain it ('> 0.5').
OPTICS_STABLE_CHANNEL = 'optics_stable'

# Global optics channels that are scalars on the twiss result.
TWISS_SCALAR_CHANNELS = {
    'qx': 'qx',
    'qy': 'qy',
    'dqx': 'dqx',
    'dqy': 'dqy',
}

# Global optics channels read from the twiss table at the start of the ring.
TWISS_S0_CHANNELS = {
    'beta_x': 'betx',
    'beta_y': 'bety',
    'alpha_x': 'alfx',
    'alpha_y': 'alfy',
    'disp_x': 'dx',
    'disp_y': 'dy',
    'dpx': 'dpx',
    'dpy': 'dpy',
}


class Interface(interface.Interface):
    name = 'VirtualAccelerator_MADXSuiteInterface'

    # ------------------------------------------------------------------ #
    # Observable readback
    # ------------------------------------------------------------------ #

    def get_values(
        self,
        channel_names: list[str],
        line=None,
        twiss=None,
        setpoints: Optional[dict[str, float]] = None,
        debug: bool = False,
        design_twiss=None,
    ) -> dict[str, float]:
        """Read observable channels from the twiss results.

        A '<name>-SETPOINT' channel returns the squared error
        (value - setpoints[name])**2, suitable as a minimization objective.
        If the twiss is None (unstable optics), twiss-derived channels
        return NaN so the optimizer can penalize the point.  design_twiss is
        needed only by the beta-beat columns.
        """
        if line is None:
            raise ValueError(
                'get_values() requires the xtrack Line; the environment '
                'must pass line=...'
            )
        if setpoints is None:
            setpoints = {}

        if twiss is None:
            logger.warning(
                'No twiss available (unstable optics?); '
                'returning NaN for twiss-derived channels'
            )

        readbacks = {name: self._read_channel(name, twiss, design_twiss, setpoints)
                     for name in channel_names}

        if debug:
            print(f'Interface get_values() -> {readbacks}')
        return readbacks

    @staticmethod
    def setpoint_bases(channel_names: list[str]) -> list[str]:
        """The base names of the '-SETPOINT' channels asked for, sums opened up."""
        bases = []
        for name in channel_names:
            total = SUM_CHANNEL.match(name)
            parts = split_top_level(total.group(1)) if total else [name]
            if total:
                bases += Interface.setpoint_bases(parts)
            elif name.endswith(SETPOINT_SUFFIX):
                bases.append(name.removesuffix(SETPOINT_SUFFIX))
        return list(dict.fromkeys(bases))

    def _read_channel(self, raw_name: str, twiss, design_twiss, setpoints) -> float:
        """One channel: a sum of channels, a '-SETPOINT' squared error, or a reading."""
        total = SUM_CHANNEL.match(raw_name)
        if total:
            return sum(self._read_channel(part, twiss, design_twiss, setpoints)
                       for part in split_top_level(total.group(1)))
        base_name = raw_name.removesuffix(SETPOINT_SUFFIX)
        value = self._read_observable(base_name, twiss, design_twiss)
        if raw_name == base_name:
            return value
        if base_name not in setpoints:
            raise ValueError(
                f"No setpoint defined for '{base_name}'. Add it to the "
                "environment's 'setpoints' parameter (the environment fills in "
                'the design value for any channel it can read on the design '
                'lattice).'
            )
        return (value - setpoints[base_name]) ** 2

    def _element_mask(self, twiss, pattern: str):
        """Rows of the twiss table whose element names match the regex (cached)."""
        key = (pattern, hash(tuple(twiss.name)))
        if key not in _MASKS:
            regex = re.compile(pattern)
            _MASKS[key] = np.array([bool(regex.search(n)) for n in twiss.name])
            if not _MASKS[key].any():
                raise ValueError(f"No element matches '{pattern}'")
        return _MASKS[key]

    def _read_observable(self, name: str, twiss, design_twiss=None) -> float:
        """One observable channel from the twiss results (NaN if no twiss)."""
        if name == OPTICS_STABLE_CHANNEL:
            return 0.0 if twiss is None else 1.0

        stat = STAT_CHANNEL.match(name)
        if stat:
            fn, column, pattern = stat.groups()
            if twiss is None:
                return float('nan')
            mask = self._element_mask(twiss, pattern)
            if column in BEAT_COLUMNS:
                if design_twiss is None:
                    raise ValueError(f"'{name}' needs the design twiss")
                beta = BEAT_COLUMNS[column]
                values = twiss[beta][mask] / design_twiss[beta][mask] - 1.0
            else:
                try:
                    values = twiss[column][mask]
                except KeyError:
                    raise ValueError(f"Unknown twiss column '{column}' in '{name}'")
            return STATS[fn](values)

        phase = PHASE_CHANNEL.match(name)
        if phase:
            plane, a, b = phase.groups()
            if twiss is None:
                return float('nan')
            column = f'mu{plane}'
            return float(360.0 * (twiss[column, b] - twiss[column, a]))

        if name in TWISS_SCALAR_CHANNELS:
            if twiss is None:
                return float('nan')
            return float(getattr(twiss, TWISS_SCALAR_CHANNELS[name]))

        if name in TWISS_S0_CHANNELS:
            if twiss is None:
                return float('nan')
            return float(getattr(twiss, TWISS_S0_CHANNELS[name])[0])

        # Any twiss column at any element, '<element>.<column>': the beam
        # centroid 'p_dvp302.x', the local optics 'bphq2.betx', and so on.
        # The environment advertises only the centroids, but a user may type
        # any column into the GUI table.
        if '.' in name:
            element_name, attr = name.split('.', 1)
            if twiss is None:
                return float('nan')
            try:
                return float(twiss[attr, element_name])
            except KeyError:
                raise ValueError(
                    f"Unknown observable channel: '{name}' -- the twiss table "
                    f"has no column '{attr}' at element '{element_name}'"
                )

        raise ValueError(f"Unknown observable channel: '{name}'")

    # ------------------------------------------------------------------ #
    # Variable read/write
    # ------------------------------------------------------------------ #

    def get_settings(
        self,
        settings_names: list[str],
        line=None,
        debug: bool = False,
    ) -> dict[str, float]:
        """Read current values of variable channels from the Line.

        A channel this lattice does not have reads NaN rather than raising:
        Badger's '-mini' variable table asks whichever environment instance it
        happens to hold -- built from the plugin's default lattice, not the
        template's -- for every name in the table, and one unknown name there
        would abort the whole template load.  Writes still raise; silently
        dropping a setting would be a different matter.

        That table is routinely thousands of rows wide, so the unknown names are
        summarized in one debug line rather than reported one by one.
        """
        if line is None:
            raise ValueError(
                'get_settings() requires the xtrack Line; the environment '
                'must pass line=...'
            )

        settings = {}
        unknown = []
        for name in settings_names:
            value = self._read_setting(name, line)
            if value is None:
                unknown.append(name)
                value = float('nan')
            settings[name] = value

        if unknown:
            logger.debug(
                f'{len(unknown)} of {len(settings_names)} channels are neither '
                'a line variable nor an element attribute of this lattice; '
                f'reading NaN (e.g. {", ".join(unknown[:3])})'
            )

        if debug:
            print(f'Interface get_settings() -> {settings}')
        return settings

    @staticmethod
    def _read_setting(name: str, line) -> Optional[float]:
        """The channel's current value, or None if this lattice has no such
        channel (get_settings turns that into NaN)."""
        if name in line.vars.keys():
            return float(line.vars.val[name])

        if '.' in name:
            element_name, attr = name.split('.', 1)
            element = line.element_dict.get(element_name)
            if element is not None and hasattr(element, attr):
                return float(getattr(element, attr))

        return None

    def set_values(
        self,
        settings_dict: dict[str, float],
        line=None,
        debug: bool = False,
    ):
        """Write variable channels to the Line.

        Line variables go through line.vars.update(), which propagates
        through the deferred-expression graph (xtrack's Line has no 'update'
        method itself).  Element attributes are written directly; that is
        safe because the environment only exposes attributes that are not
        driven by a deferred expression.
        """
        if line is None:
            raise ValueError(
                'set_values() requires the xtrack Line; the environment '
                'must pass line=...'
            )

        var_updates = {}
        for name, value in settings_dict.items():
            if name in line.vars.keys():
                var_updates[name] = value
                continue

            if '.' in name:
                element_name, attr = name.split('.', 1)
                element = line.element_dict.get(element_name)
                if element is not None and hasattr(element, attr):
                    setattr(element, attr, value)
                    continue

            raise ValueError(
                f"Cannot set '{name}': neither a line variable nor an "
                'element attribute of this lattice'
            )

        if var_updates:
            line.vars.update(var_updates)

        if debug:
            print(
                f'Interface set_values(): {len(var_updates)} line vars, '
                f'{len(settings_dict) - len(var_updates)} element attributes'
            )
