"""Offline self-check for plugins/supply_limits.py. Run: python tests/supply_limits_test.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins'))
from supply_limits import clip_to_supply_limits  # noqa: E402
from badger.errors import BadgerEnvVarError  # noqa: E402

GROUPS = {'G': 'L:A,L:B,L:C'}
LIMITS = {'G': 5.0}
LIVE = {'L:A': 1.0, 'L:B': 1.0, 'L:C': 1.0}
read = lambda devs: {d: LIVE[d] for d in devs}  # noqa: E731
quiet = lambda msg: None  # noqa: E731


def test_under_limit_unchanged():
    req = {'L:A': 2.0, 'L:B': -2.0, 'L:C': 0.5}
    assert clip_to_supply_limits(req, GROUPS, LIMITS, read, quiet) == req


def test_clips_largest_only():
    req = {'L:A': 3.0, 'L:B': -2.0, 'L:C': 1.0}  # sum 6 > 5
    out = clip_to_supply_limits(req, GROUPS, LIMITS, read, quiet)
    assert out == {'L:A': 2.0, 'L:B': -2.0, 'L:C': 1.0}
    assert req['L:A'] == 3.0  # input not mutated


def test_largest_hits_zero_then_next():
    req = {'L:A': 1.0, 'L:B': -4.0, 'L:C': 4.0}  # sum 9, excess 4
    out = clip_to_supply_limits(req, GROUPS, LIMITS, read, quiet)
    assert sum(abs(v) for v in out.values()) == 5.0
    assert out['L:A'] == 1.0 and 0.0 in (out['L:B'], out['L:C'])


def test_unset_member_counts():
    req = {'L:A': 3.0, 'L:B': 2.0}  # + live L:C = 1 -> 6 > 5
    out = clip_to_supply_limits(req, GROUPS, LIMITS, read, quiet)
    assert out == {'L:A': 2.0, 'L:B': 2.0}


def test_unset_members_alone_over_limit_raises():
    req = {'L:A': 0.5}
    big = lambda devs: {d: 10.0 for d in devs}  # noqa: E731
    try:
        clip_to_supply_limits(req, GROUPS, LIMITS, big, quiet)
    except BadgerEnvVarError:
        pass
    else:
        raise AssertionError('expected BadgerEnvVarError')


def test_warning_is_one_line():
    lines = []
    clip_to_supply_limits({'L:A': 3.0, 'L:B': 3.0, 'L:C': 0.0}, GROUPS, LIMITS, read, lines.append)
    assert len(lines) == 1 and 'G' in lines[0] and 'clipped' in lines[0], lines


if __name__ == '__main__':
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print(f'{t.__name__}: OK')
    print(f'{len(tests)} checks passed.')
