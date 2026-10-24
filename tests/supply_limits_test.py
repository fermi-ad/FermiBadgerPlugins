"""Offline self-check for plugins/supply_limits.py (bulk power supply limits).
Run: python tests/supply_limits_test.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins'))
from pydantic import TypeAdapter, ValidationError  # noqa: E402
from supply_limits import (BulkPSLimits, bulk_ps_observable, bulk_ps_observables,  # noqa: E402
                           clip_to_bulk_ps_limits)
from badger.errors import BadgerEnvVarError  # noqa: E402

ABS = {'G': {'limit': 5.0, 'devices': ['L:A', 'L:B', 'L:C']}}
SPLIT = {'S': {'positive': 8.0, 'negative': 8.0, 'devices': ['L:A', 'L:B', 'L:C', 'L:D']}}
LIVE = {'L:A': 1.0, 'L:B': 1.0, 'L:C': 1.0, 'L:D': -1.0}
read = lambda devs: {d: LIVE[d] for d in devs}  # noqa: E731
quiet = lambda msg: None  # noqa: E731


# --- sum of |I| (limit) ----------------------------------------------------------------
def test_under_limit_unchanged():
    req = {'L:A': 2.0, 'L:B': -2.0, 'L:C': 0.5}
    assert clip_to_bulk_ps_limits(req, ABS, read, quiet) == req


def test_clips_largest_only():
    req = {'L:A': 3.0, 'L:B': -2.0, 'L:C': 1.0}  # sum 6 > 5
    out = clip_to_bulk_ps_limits(req, ABS, read, quiet)
    assert out == {'L:A': 2.0, 'L:B': -2.0, 'L:C': 1.0}
    assert req['L:A'] == 3.0  # input not mutated


def test_largest_hits_zero_then_next():
    req = {'L:A': 1.0, 'L:B': -4.0, 'L:C': 4.0}  # sum 9, excess 4
    out = clip_to_bulk_ps_limits(req, ABS, read, quiet)
    assert sum(abs(v) for v in out.values()) == 5.0
    assert out['L:A'] == 1.0 and 0.0 in (out['L:B'], out['L:C'])


def test_unset_member_counts():
    req = {'L:A': 3.0, 'L:B': 2.0}  # + live L:C = 1 -> 6 > 5
    out = clip_to_bulk_ps_limits(req, ABS, read, quiet)
    assert out == {'L:A': 2.0, 'L:B': 2.0}


def test_unset_members_alone_over_limit_raises():
    big = lambda devs: {d: 10.0 for d in devs}  # noqa: E731
    try:
        clip_to_bulk_ps_limits({'L:A': 0.5}, ABS, big, quiet)
    except BadgerEnvVarError:
        pass
    else:
        raise AssertionError('expected BadgerEnvVarError')


def test_warning_is_one_line():
    lines = []
    clip_to_bulk_ps_limits({'L:A': 3.0, 'L:B': 3.0, 'L:C': 0.0}, ABS, read, lines.append)
    assert len(lines) == 1 and 'G' in lines[0] and 'clipped' in lines[0], lines


# --- separate + and - limits (positive / negative) ------------------------------------
def test_split_under_limits_unchanged():
    # sum|I| is 16, but +I sums to 8 and -I to -8: within both limits
    req = {'L:A': 5.0, 'L:B': 3.0, 'L:C': -6.0, 'L:D': -2.0}
    assert clip_to_bulk_ps_limits(req, SPLIT, read, quiet) == req


def test_split_positive_over_clips_positive_only():
    req = {'L:A': 6.0, 'L:B': 4.0, 'L:C': -3.0, 'L:D': -3.0}  # +10 > 8, |-6| fine
    out = clip_to_bulk_ps_limits(req, SPLIT, read, quiet)
    assert out == {'L:A': 4.0, 'L:B': 4.0, 'L:C': -3.0, 'L:D': -3.0}, out


def test_split_negative_over_clips_negative_only():
    req = {'L:A': 1.0, 'L:B': 1.0, 'L:C': -7.0, 'L:D': -4.0}  # |-11| > 8
    out = clip_to_bulk_ps_limits(req, SPLIT, read, quiet)
    assert out == {'L:A': 1.0, 'L:B': 1.0, 'L:C': -4.0, 'L:D': -4.0}, out


def test_split_both_over():
    req = {'L:A': 9.0, 'L:B': 0.0, 'L:C': -9.0, 'L:D': 0.0}
    lines = []
    out = clip_to_bulk_ps_limits(req, SPLIT, read, lines.append)
    assert out['L:A'] == 8.0 and out['L:C'] == -8.0, out
    assert len(lines) == 2 and 'sum of +I' in lines[0] and '|sum of -I|' in lines[1], lines


def test_split_unset_member_counts():
    req = {'L:A': 4.0, 'L:B': 4.0}  # + live L:C = +1 -> +9 > 8; live L:D = -1 fine
    out = clip_to_bulk_ps_limits(req, SPLIT, read, quiet)
    assert out == {'L:A': 3.0, 'L:B': 4.0} or out == {'L:A': 4.0, 'L:B': 3.0}, out


def test_split_unset_members_alone_over_raises():
    big = lambda devs: {d: -9.0 for d in devs}  # noqa: E731
    try:
        clip_to_bulk_ps_limits({'L:A': 0.5}, SPLIT, big, quiet)
    except BadgerEnvVarError as e:
        assert '|sum of -I|' in str(e), e
    else:
        raise AssertionError('expected BadgerEnvVarError')


# --- observables and validation -------------------------------------------------------
def test_observables():
    both = {**ABS, **SPLIT}
    assert bulk_ps_observables(both) == ['BulkPS_G', 'BulkPS_S_Pos', 'BulkPS_S_Neg']
    live = {'L:A': 2.0, 'L:B': -3.0, 'L:C': 0.5, 'L:D': -1.0}
    rd = lambda devs: {d: live[d] for d in devs}  # noqa: E731
    assert bulk_ps_observable(both, 'BulkPS_G', rd) == 5.5
    assert bulk_ps_observable(both, 'BulkPS_S_Pos', rd) == 2.5
    assert bulk_ps_observable(both, 'BulkPS_S_Neg', rd) == 4.0


def test_validation():
    adapter = TypeAdapter(BulkPSLimits)
    adapter.validate_python({**ABS, **SPLIT})
    for bad in ({'X': {'devices': ['L:A']}},                                 # no limit at all
                {'X': {'devices': ['L:A'], 'limit': 1, 'positive': 1, 'negative': 1}},  # both kinds
                {'X': {'devices': ['L:A'], 'positive': 1}},                  # only one sign
                {'X': {'limit': 1}}):                                        # no devices
        try:
            adapter.validate_python(bad)
        except ValidationError:
            continue
        raise AssertionError(f'expected a validation error for {bad}')


if __name__ == '__main__':
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print(f'{t.__name__}: OK')
    print(f'{len(tests)} checks passed.')
