"""Hard limit on sum |I| over trim magnets that share one bulk power supply.

``supplies`` is one pydantic field on the environment, {group: {limit: amps,
devices: [DEV, ...]}} of plain setting-device names, so a tuning template can
override it under environment.params.
"""
from typing import List

from typing_extensions import TypedDict

from badger.errors import BadgerEnvVarError


class Supply(TypedDict):
    """One bulk supply: its limit on the summed |I| (amps), and the trims it feeds.
    Plain setting names only, no "read,set,tolN@X" pair syntax: the trims don't use it."""
    limit: float
    devices: List[str]


def clip_to_supply_limits(requested: dict, supplies: dict, read_settings, warn=print) -> dict:
    """Return a copy of `requested` with each supply group's sum |I| at or under its limit.

    Group members not in `requested` keep their live setting (read via `read_settings`)
    and still count toward the sum. Only devices being set are clipped: the largest |I|
    is reduced first, to zero if need be, then the next largest. If the members *not*
    being set already exceed the limit on their own, nothing can be written safely and
    BadgerEnvVarError is raised.
    """
    out = dict(requested)
    for group, supply in supplies.items():
        devs = supply['devices']
        settable = [d for d in devs if d in out]
        if not settable:
            continue
        limit = supply['limit']
        missing = [d for d in devs if d not in out]
        vals = {d: out[d] for d in settable}
        if missing:
            vals.update(read_settings(missing))
        total = sum(abs(v) for v in vals.values())
        excess = total - limit
        if excess <= 0:
            continue
        clipped = []
        while excess > 0:
            dev = max(settable, key=lambda d: abs(vals[d]))
            old = vals[dev]
            if old == 0:
                raise BadgerEnvVarError(
                    f'supply limit {group}: members not being set already total '
                    f'{total - sum(abs(vals[d]) for d in settable):.3f} A > {limit} A; refusing to write')
            cut = min(abs(old), excess)
            new = old - cut if old > 0 else old + cut
            vals[dev] = out[dev] = new
            excess -= cut
            clipped.append(f'{dev} {old:.3f} -> {new:.3f}')
        warn(f'supply limit {group}: sum|I| {total:.3f} A > {limit} A; clipped ' + ', '.join(clipped))
    return out
