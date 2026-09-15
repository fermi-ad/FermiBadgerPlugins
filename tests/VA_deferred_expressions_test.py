"""Equivalence and liveness test for the MAD-X ':=' rewrite.

For every lattice in sim_configs/, asserts that the rewritten source is the
same machine as the original -- every global and every element attribute equal
to within rtol=1e-12 -- and that the rewrite actually produced a live
dependency graph rather than parsing cleanly and doing nothing.

Then checks, through the environment itself, that the two lattices respond as
measured: the Delivery Ring tune sweep reproduces the slow-path values, and the
400 MeV transfer line's downstream centroid moves when a quad current moves.

Run from the repo root:
    ~/miniconda3/envs/FermiBadger_env/bin/python tests/VA_deferred_expressions_test.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, 'plugins')

from cpymad.madx import Madx

from environments.VirtualAccelerator_MADXSuite import (
    VERIFIED_ELEMENT_ATTRS,
    Environment,
    _matches,
)
from environments.VirtualAccelerator_MADXSuite.madx_deferred import to_deferred
from interfaces.VirtualAccelerator_MADXSuiteInterface import Interface

DELIVERY_RING = 'sim_configs/DeliveryRing/mu2e-dr-model-v2026.03.23.madx'
TRANSFER_LINE = 'sim_configs/Xfer400MeV/B400tracking.madx'

# Values recorded in docs/progress.md from the old path, which rebuilt the
# whole Line from a modified source on every iteration.
SLOW_PATH_TUNES = {
    220: 10.024228, 230: 9.843706, 240: 9.659982,
    250: 9.474853, 260: 9.285527,
}

XFER_TWISS_INIT = {
    'betx': 1.113092, 'alfx': -0.89649, 'bety': 5.6787, 'alfy': 0.49047,
    'x': 1.0e-3, 'px': 2.0e-4, 'y': -5.0e-4, 'py': 0.0,
}


def load(source_path, rewrite):
    """A Madx with source_path loaded, optionally through the ':=' rewrite."""
    mad = Madx(stdout=False)
    if not rewrite:
        mad.call(str(source_path))
        return mad, None
    rewritten, stats = to_deferred(source_path.read_text())
    with tempfile.NamedTemporaryFile(
        mode='w', dir=source_path.parent, suffix='.madx', delete=False
    ) as handle:
        handle.write(rewritten)
        temp_path = handle.name
    try:
        mad.call(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)
    return mad, stats


def check_equivalence(lattice):
    source_path = Path(lattice)
    original, _ = load(source_path, rewrite=False)
    rewritten, stats = load(source_path, rewrite=True)
    print(f'\n{source_path.name}: deferred {stats["vars"]} variables and '
          f'{stats["attrs"]} element attributes, '
          f'skipped {len(stats["skipped"])}')

    assert set(original.globals.keys()) == set(rewritten.globals.keys()), (
        'the rewrite changed which globals exist'
    )
    for name, value in original.globals.items():
        assert _matches(value, rewritten.globals[name]), (
            f'global {name}: {value} -> {rewritten.globals[name]}'
        )
    print(f'  {len(original.globals)} globals agree')

    compared = live = 0
    for name, element in original.elements.items():
        for attr in VERIFIED_ELEMENT_ATTRS:
            if attr not in element.cmdpar:
                continue
            after = rewritten.elements[name].cmdpar[attr]
            assert _matches(element.cmdpar[attr].value, after.value), (
                f'{name}.{attr}: {element.cmdpar[attr].value} -> {after.value}'
            )
            compared += 1
            live += after.expr is not None
    print(f'  {compared} element attributes agree, {live} now expression-driven')
    assert live, 'the rewrite left nothing live -- it parsed but did nothing'

    original.quit()
    rewritten.quit()


def check_delivery_ring():
    env = Environment(
        interface=Interface(), lattice_filename=DELIVERY_RING, sequence_name='full'
    )
    env._ensure_lattice()  # construction is lazy when the sidecar cache is warm
    assert env._use_deferred, 'the rewrite failed verification'
    print(f'\n{Path(DELIVERY_RING).name}: {len(env._monitor_planes)} monitors, '
          f'{len(Environment.variables)} variables')

    # The main quad gradients are outputs of the supply currents now, so they
    # must not be offered as knobs.
    assert not [v for v in Environment.variables if v.startswith('g_dq')]
    # An hmonitor measures x only.
    assert 'p_dhp301.x' in Environment.observables
    assert 'p_dhp301.y' not in Environment.observables

    design_current = env.get_variables(['i_dqd'])['i_dqd']

    for current, expected in SLOW_PATH_TUNES.items():
        env.set_variables({'i_dqd': float(current)})
        qx = env.get_observables(['qx'])['qx']
        print(f'  i_dqd={current}: qx={qx:.6f} (slow path {expected})')
        assert abs(qx - expected) < 1e-6

    # A corrector current has to move the closed orbit at a BPM, through the
    # whole chain: i_dht301 -> h_dht301 (calibration polynomial) -> the
    # kicker's hkick.  Back at the design optics, where the reference value
    # below was measured.
    env.set_variables({'i_dqd': design_current, 'i_dht301': 0.0})
    assert abs(env.get_observables(['p_dhp301.x'])['p_dhp301.x']) < 1e-9
    env.set_variables({'i_dht301': 0.1})
    x = env.get_observables(['p_dhp301.x'])['p_dhp301.x']
    print(f'  i_dht301=0.1 A: h_dht301={env._line.vars.val["h_dht301"]:.6e}, '
          f'x[p_dhp301]={x:.6e}')
    assert abs(x - -2.8216355e-06) < 1e-12


def check_transfer_line():
    env = Environment(
        interface=Interface(), lattice_filename=TRANSFER_LINE,
        sequence_name='l400mev', twiss_init=XFER_TWISS_INIT,
    )
    env._ensure_lattice()  # construction is lazy when the sidecar cache is warm
    assert env._use_deferred, 'the rewrite failed verification'
    print(f'\n{Path(TRANSFER_LINE).name}: {len(env._monitor_planes)} monitors, '
          f'{len(Environment.variables)} variables')

    # An open line has no tune or chromaticity to advertise.
    assert 'qx' not in Environment.observables
    assert 'beta_x' in Environment.observables

    x = env.get_observables(['bphq2.x'])['bphq2.x']
    print(f'  incoming centroid propagates: x[bphq2]={x:.6e}')
    assert abs(x - 2.960652e-03) < 1e-9

    before = env.get_observables(['bpvq17.y'])['bpvq17.y']
    iq3 = env.get_variables(['iq3'])['iq3']
    env.set_variables({'iq3': iq3 * 1.1})
    after = env.get_observables(['bpvq17.y'])['bpvq17.y']
    print(f'  iq3 {iq3:.4g} -> {iq3 * 1.1:.4g}: '
          f'y[bpvq17] {before:.6e} -> {after:.6e}')
    assert abs(after - before) > 1e-6, 'the quad current is not live'


if __name__ == '__main__':
    for lattice in (DELIVERY_RING, TRANSFER_LINE):
        check_equivalence(lattice)
    check_delivery_ring()
    check_transfer_line()
    print('\nDEFERRED EXPRESSION TEST PASSED')
