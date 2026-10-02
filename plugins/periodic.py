"""Periodic (phase) quantities: a reading in degrees or radians comes back wrapped
into one period, but value and value + n*period are the same physics.

Shared by the interfaces and environments under plugins/ (this directory is on
sys.path when Badger loads a plugin, the same way scanner.py is found).
"""


def unwrap(value: float, ref: float, period: float) -> float:
    """Return value shifted by a whole number of periods so it is within half a
    period of ref, i.e. the branch of the periodic quantity nearest ref.

    >>> unwrap(5.0, 350.0, 360.0)
    365.0
    >>> unwrap(355.0, 10.0, 360.0)
    -5.0
    """
    return ref + (value - ref + period / 2) % period - period / 2
