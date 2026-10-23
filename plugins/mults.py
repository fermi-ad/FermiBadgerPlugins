"""Mults: fixed-proportion additive knobs, as on a console parameter page.

A mult is one Badger variable, ``mult:<Name>``, whose value is an integer step count
in the knob's range (±10). Each member device is written as

    setting = as_found + coefficient * step_size * steps

``mults`` is one pydantic field on the environment, {name: {step: size, members:
{DEV: coefficient, ...}}}, so a tuning template can override it and operators can
adjust a step size, a member or a coefficient in the GUI's environment parameters.

A member that would leave its own hard bounds is clipped, never refused; how much of
the requested step was lost is reported as the observable ``MultOOB_<Name>`` (0 good,
1 = that member could not move at all) so a template can constrain on it.
"""
from typing import Dict

from typing_extensions import TypedDict

from badger.errors import BadgerEnvVarError

MULT_PREFIX = 'mult:'      # variable name  mult:<Name>
OOB_PREFIX = 'MultOOB_'    # observable     MultOOB_<Name>


def is_mult(name: str) -> bool:
    return name.startswith(MULT_PREFIX)


def mult_name(variable: str) -> str:
    return variable[len(MULT_PREFIX):]


class Mult(TypedDict):
    """One mult: its step size, and each member device's coefficient."""
    step: float
    members: Dict[str, float]


def mult_members(mults: dict) -> list[str]:
    """Every member device of every mult, in declaration order, no duplicates."""
    out = []
    for mult in mults.values():
        for dev in mult['members']:
            if dev not in out:
                out.append(dev)
    return out


def expand_mults(requested: dict, mults: dict, as_found: dict, hard_bounds: dict, warn=print):
    """Replace every mult:<Name> in `requested` by its member settings.

    Returns (settings, steps, oob):
      settings: `requested` minus the mult keys, plus one entry per member at
        as_found + coeff * step_size * steps, clipped to hard_bounds[member] if any;
      steps:    {Name: int} -- the discrete step actually taken (nearest integer);
      oob:      {Name: fraction of the requested offset lost to clipping, worst member}
                (0.0 when nothing was clipped or the step is 0).
    Raises BadgerEnvVarError if a member is also set directly in the same call.
    """
    settings = {k: v for k, v in requested.items() if not is_mult(k)}
    steps, oob = {}, {}
    for var, value in requested.items():
        if not is_mult(var):
            continue
        name = mult_name(var)
        if name not in mults:
            raise BadgerEnvVarError(f'{var}: no such mult; mults = {list(mults)}')
        n = int(round(float(value)))
        steps[name] = n
        lost = 0.0
        for dev, coeff in mults[name]['members'].items():
            if dev in settings:
                raise BadgerEnvVarError(
                    f'{dev} is set directly and through {var} in the same step; uncheck one of them')
            if dev not in as_found:
                raise BadgerEnvVarError(f'{var}: no as-found setting captured for {dev}')
            offset = coeff * mults[name]['step'] * n
            target = as_found[dev] + offset
            if dev in hard_bounds:
                lo, hi = hard_bounds[dev]
                clipped = min(max(target, lo), hi)
                if clipped != target:
                    warn(f'mult {name}: {dev} clipped to {clipped} (wanted {target}, bounds {lo}..{hi})')
                    if offset:
                        lost = max(lost, abs(target - clipped) / abs(offset))
                    target = clipped
            settings[dev] = target
        oob[name] = min(lost, 1.0)
    return settings, steps, oob
