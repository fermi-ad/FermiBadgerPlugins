"""Limits on the trims fed by one bulk power supply (BulkPS), which trips off if
they draw too much together.

``BulkPS_Limit`` is one pydantic field on the environment, {group: BulkPS}, so a
tuning template can override it under environment.params. Each bulk supply lists
the plain setting devices it feeds and its limit, as either

  limit: A                     the sum of |I| over its trims stays <= A, or
  positive: P, negative: N     the sum of the positive currents stays <= P and
                               the magnitude of the sum of the negative ones <= N
                               (a supply with separate + and - limits).

Each such sum is a "budget". Before any write, every budget over its limit is
brought back by moving the largest contributor being set toward zero, then the
next largest; members not being set count at their live setting. The sums are
offered as observables (bulk_ps_observables) so a template can constrain them.
"""
from typing import Annotated, Dict, List

from pydantic import AfterValidator
from typing_extensions import NotRequired, TypedDict

from badger.errors import BadgerEnvVarError

OBSERVABLE_PREFIX = 'BulkPS_'


class BulkPS(TypedDict):
    """One bulk power supply: the trims it feeds and its limit(s), in amps.
    Plain setting names only, no "read,set,tolN@X" pair syntax: the trims don't use it."""
    devices: List[str]
    limit: NotRequired[float]
    positive: NotRequired[float]
    negative: NotRequired[float]


# (limit key, observable suffix, what each current contributes, what is summed)
_BUDGETS = (
    ('limit', '', abs, 'sum|I|'),
    ('positive', '_Pos', lambda v: max(v, 0.0), 'sum of +I'),
    ('negative', '_Neg', lambda v: max(-v, 0.0), '|sum of -I|'),
)


def _check(bulk_ps: dict) -> dict:
    for group, ps in bulk_ps.items():
        has_limit = 'limit' in ps
        has_signs = 'positive' in ps or 'negative' in ps
        if has_limit == has_signs or (has_signs and not ('positive' in ps and 'negative' in ps)):
            raise ValueError(f"{group}: give either 'limit', or both 'positive' and 'negative'")
    return bulk_ps


BulkPSLimits = Annotated[Dict[str, BulkPS], AfterValidator(_check)]


def _budgets(ps: dict):
    return [(suffix, share, ps[key], what) for key, suffix, share, what in _BUDGETS if key in ps]


def bulk_ps_observables(bulk_ps: dict) -> list[str]:
    """Observable names for every budget: BulkPS_<group>, or BulkPS_<group>_Pos/_Neg."""
    return [f'{OBSERVABLE_PREFIX}{group}{suffix}'
            for group, ps in bulk_ps.items() for suffix, *_ in _budgets(ps)]


def bulk_ps_observable(bulk_ps: dict, name: str, read_settings) -> float:
    """The live value of one bulk_ps_observables() name, from the trims' settings."""
    for group, ps in bulk_ps.items():
        for suffix, share, _, _ in _budgets(ps):
            if name == f'{OBSERVABLE_PREFIX}{group}{suffix}':
                return sum(share(v) for v in read_settings(ps['devices']).values())
    raise KeyError(name)


def clip_to_bulk_ps_limits(requested: dict, bulk_ps: dict, read_settings, warn=print) -> dict:
    """Return a copy of `requested` with every bulk-supply budget at or under its limit.

    Only devices being set are clipped, each toward zero, largest contribution first.
    If the members *not* being set already exceed a limit on their own, nothing can be
    written safely and BadgerEnvVarError is raised.
    """
    out = dict(requested)
    for group, ps in bulk_ps.items():
        devs = ps['devices']
        settable = [d for d in devs if d in out]
        if not settable:
            continue
        missing = [d for d in devs if d not in out]
        vals = {d: out[d] for d in settable}
        if missing:
            vals.update(read_settings(missing))
        for suffix, share, limit, what in _budgets(ps):
            total = sum(share(v) for v in vals.values())
            excess = total - limit
            if excess <= 0:
                continue
            clipped = []
            while excess > 0:
                dev = max(settable, key=lambda d: share(vals[d]))
                old = vals[dev]
                if share(old) == 0:
                    raise BadgerEnvVarError(
                        f'bulk PS {group}: members not being set already give {what} '
                        f'{total - sum(share(vals[d]) for d in settable):.3f} A > {limit} A; '
                        'refusing to write')
                cut = min(share(old), excess)
                new = old - cut if old > 0 else old + cut  # toward zero
                vals[dev] = out[dev] = new
                excess -= cut
                clipped.append(f'{dev} {old:.3f} -> {new:.3f}')
            warn(f'bulk PS {group}: {what} {total:.3f} A > {limit} A; clipped ' + ', '.join(clipped))
    return out
