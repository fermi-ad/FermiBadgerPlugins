"""Badger interface for the VirtualAccelerator_MADXSuite environment.

Translates Badger channel names into reads/writes on an xtrack Line and its
twiss results.  The environment owns the Line and the twiss; it passes both
into every call here.

Channel naming:
- variables:   line.vars names ('i_dsexf') or element attributes ('q_dq303.k1')
- observables: global optics ('qx', 'beta_x', ...), monitor orbit readings
               ('p_dvp302.x'), and squared-error setpoint channels
               ('qx-SETPOINT')
"""

import logging
from typing import Any, Optional

from badger import interface

logger = logging.getLogger(__name__)

SETPOINT_SUFFIX = '-SETPOINT'

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
    ) -> dict[str, float]:
        """Read observable channels from the twiss results.

        A '<name>-SETPOINT' channel returns the squared error
        (value - setpoints[name])**2, suitable as a minimization objective.
        If the twiss is None (unstable optics), twiss-derived channels
        return NaN so the optimizer can penalize the point.
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

        readbacks = {}
        for raw_name in channel_names:
            base_name = raw_name.removesuffix(SETPOINT_SUFFIX)
            value = self._read_observable(base_name, twiss)

            if raw_name != base_name:  # setpoint channel
                if base_name not in setpoints:
                    raise ValueError(
                        f"No setpoint defined for '{base_name}'. Add it to "
                        "the environment's 'setpoints' parameter (design "
                        'values are recorded automatically for global optics).'
                    )
                value = (value - setpoints[base_name]) ** 2

            readbacks[raw_name] = value

        if debug:
            print(f'Interface get_values() -> {readbacks}')
        return readbacks

    def _read_observable(self, name: str, twiss) -> float:
        """One observable channel from the twiss results (NaN if no twiss)."""
        if name in TWISS_SCALAR_CHANNELS:
            if twiss is None:
                return float('nan')
            return float(getattr(twiss, TWISS_SCALAR_CHANNELS[name]))

        if name in TWISS_S0_CHANNELS:
            if twiss is None:
                return float('nan')
            return float(getattr(twiss, TWISS_S0_CHANNELS[name])[0])

        # Monitor orbit reading: '<element>.x' / '<element>.y' from the
        # twiss closed orbit at that element.
        if '.' in name:
            element_name, attr = name.split('.', 1)
            if attr in ('x', 'y'):
                if twiss is None:
                    return float('nan')
                try:
                    return float(twiss[attr, element_name])
                except KeyError:
                    raise ValueError(
                        f"Element '{element_name}' not found in the twiss table"
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
        """Read current values of variable channels from the Line."""
        if line is None:
            raise ValueError(
                'get_settings() requires the xtrack Line; the environment '
                'must pass line=...'
            )

        settings = {name: self._read_setting(name, line) for name in settings_names}

        if debug:
            print(f'Interface get_settings() -> {settings}')
        return settings

    @staticmethod
    def _read_setting(name: str, line) -> float:
        if name in line.vars.keys():
            return float(line.vars.val[name])

        if '.' in name:
            element_name, attr = name.split('.', 1)
            element = line.element_dict.get(element_name)
            if element is not None and hasattr(element, attr):
                return float(getattr(element, attr))

        raise ValueError(
            f"Cannot read '{name}': neither a line variable nor an "
            'element attribute of this lattice'
        )

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
