"""Which clock event (cycle type) does each logged reading belong to? Tags data-logger
readings by the clock events that fired just before them, and checks the tagging.
READ-ONLY: logger reads through pacsys (writes disabled, logger_noise's guard); event
history through ACL's event_log over HTTP (www-bd.fnal.gov/cgi-bin/acl.pl).

The data logger serves Booster readings (BLMs, charge, DCCT, ...) at the fastest rate it
keeps, every cycle type mixed; event-qualified logger reads (@e,1D) return nothing. So a
reading's cycle type has to come from the event history. Cycles: event firings less than
CLUSTER_S apart form a cluster; a cluster at least 0.75 cycle after the previous cycle's
start starts a new cycle, and later clusters join that cycle (in 2026-11, $10 fired
with $1D or $17 at a reset, and $1F about 35 ms later, mid-cycle). A cycle's tag is the
set of its events, e.g. {$10, $1D, $1F}: a cycle of beam to MiniBooNE. A reading's tag is
that of the cycle that started last before it.

Checks that the tagging matches readings to events as intended:
  proportions   each tag's share of the readings next to its share of the cycles (event
                firings in the same window). A logger that samples every cycle shows the
                same shares; one that samples on one event shows only that event.
  timing        the delay from the latest tagged event to the reading: tight and steady
                (one trigger), or spread (a reading not tied to these events).
  shift         how well the tags separate the readings' values (R^2: the share of the
                values' variance between tags), with each reading matched to its own cycle
                (k = 0) and to the k-th cycle before (k < 0) or after (k > 0). If the
                tagging is real, R^2 peaks sharply at one k, and that k says which cycle's
                beam the reading reflects (k = -1: the one before; a readout at the next
                reset). A flat R^2 means the tags say nothing about the values. Caveat: if
                the cycle pattern repeats every p cycles (a beam cycle every 3rd, say),
                shifts k and k + p cannot be told apart; the shifts tried (-2 to 2) are
                decisive only when no such short repeat exists, so the tool reports the
                runner-up shift too.

Run from the repo root (FNAL network or VPN):
    pixi run python scripts/event_tag.py B:BLMS13 --start "2026-11-19 19:00" --minutes 10
        [--events 10 11 12 13 14 15 16 17 19 1C 1D 1F]
    pixi run python scripts/event_tag.py --selftest      # offline, synthetic
"""
import argparse
import datetime as dt
import os
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

CYCLE_S = 1 / 15  # Booster cycle (15 Hz)
CLUSTER_S = 0.005  # firings closer than this belong together
BOOSTER_RESETS = ["10", "11", "12", "13", "14", "15", "16", "17", "19", "1C", "1D", "1F"]
ACL_URL = "https://www-bd.fnal.gov/cgi-bin/acl.pl?acl="
ACL_TZ = ZoneInfo("America/Chicago")  # ACL prints local (Central) time
STAMP = re.compile(r"^(\d{2}-[A-Z]{3}-\d{4} \d{2}:\d{2}:\d{2}\.\d+)")


def acl(command):
    q = command.replace("%", "%25").replace(" ", "%20").replace('"', "%22")
    with urllib.request.urlopen(ACL_URL + q, timeout=120) as r:
        return r.read().decode(errors="replace")


def acl_time(text):
    return dt.datetime.strptime(text, "%d-%b-%Y %H:%M:%S.%f").replace(tzinfo=ACL_TZ).timestamp()


def event_times(code, t1, t2):
    """Epoch seconds at which TCLK event `code` fired between t1 and t2 (datetimes)."""
    fmt = "%d-%b-%Y %H:%M:%S"
    out = acl(f'event_log/start="{t1:{fmt}}"/end="{t2:{fmt}}" {code}')
    return np.array([acl_time(m.group(1)) for m in map(STAMP.match, out.splitlines()) if m])


def cycles(events):
    """(start times, tags): one entry per cycle, from all the events' firings."""
    fired = sorted((t, c) for c, times in events.items() for t in times)
    starts, tags, last = [], [], -np.inf
    for t, c in fired:
        if t - last >= CLUSTER_S and (not starts or t - starts[-1] >= 0.75 * CYCLE_S):
            starts.append(t)
            tags.append(set())
        tags[-1].add(c)
        last = t
    return np.array(starts), [" ".join(sorted(x)) for x in tags]


def tag(readings_t, starts, tags, shift=0):
    """Each reading's cycle tag (the cycle that started last before it, moved by `shift`
    cycles), and its delay after that cycle's start; '-' outside the event history."""
    i = np.searchsorted(starts, np.asarray(readings_t, float)) - 1
    lag = np.where(i >= 0, readings_t - starts[np.clip(i, 0, None)], np.nan)
    j = i + shift
    ok = (i >= 0) & (j >= 0) & (j < len(starts)) & (lag < 1.5 * CYCLE_S)
    return [tags[k] if good else "-" for k, good in zip(j, ok)], np.where(ok, lag, np.nan)


def r_squared(values, tags):
    v = pd.Series(values, dtype=float)
    groups = v.groupby(pd.Series(tags)).transform("mean")
    total = ((v - v.mean()) ** 2).sum()
    return float(((groups - v.mean()) ** 2).sum() / total) if total > 0 else np.nan


def analyze(t, values, events):
    """The three checks: a per-tag table, and R^2 for shifts -2..2 cycles."""
    starts, cyc = cycles(events)
    tags, lag = tag(t, starts, cyc)
    df = pd.DataFrame({"tag": tags, "value": values, "lag_ms": 1e3 * lag})
    span = (t.max() - t.min()) or 1.0
    table = df.groupby("tag").agg(n=("value", "size"), median=("value", "median"),
                                  q25=("value", lambda x: x.quantile(0.25)),
                                  q75=("value", lambda x: x.quantile(0.75)),
                                  lag_median_ms=("lag_ms", "median"),
                                  lag_iqr_ms=("lag_ms", lambda x: x.quantile(0.75) - x.quantile(0.25)))
    table["share_readings"] = table["n"] / table["n"].sum()
    # each tag's share of the cycles in the readings' span, all tags and only the tags the
    # readings carry (a logger that samples on some cycle types only)
    inside = (starts >= t.min()) & (starts <= t.max())
    counts = pd.Series([c for c, keep in zip(cyc, inside) if keep]).value_counts()
    table["share_cycles"] = (counts / counts.sum()).reindex(table.index).fillna(0.0)
    seen = counts.reindex(table.index).fillna(0.0)
    table["share_cycles_seen"] = seen / seen.sum() if seen.sum() else 0.0
    shifts = {k: r_squared(values, tag(t, starts, cyc, k)[0]) for k in (-2, -1, 0, 1, 2)}
    return table.sort_values("n", ascending=False), shifts, span


def selftest():
    """Synthetic: cycles at 15 Hz, a $1D beam cycle at random a third of the time (a
    regular every-3rd pattern would make shifts -1 and +2 alike), the others null ($11);
    each reading is taken 1 ms after a reset and shows the PREVIOUS cycle's beam (losses
    0.2 after a beam cycle, 0.013 otherwise). The checks must find: tags {$1D} and {$11},
    shares matching the cycles, lag about 1 ms, and R^2 peaking at k = -1."""
    rng = np.random.default_rng(0)
    n = 900
    resets = 1000.0 + np.arange(n) * CYCLE_S
    beam = rng.random(n) < 1 / 3
    events = {"1D": resets[beam], "11": resets[~beam]}
    t = resets[1:] + 0.001
    values = np.where(beam[:-1], 0.2, 0.013) + 0.002 * rng.standard_normal(n - 1)
    table, shifts, _ = analyze(t, values, events)
    print(table.round(4).to_string())
    print("R^2 by shift:", {k: round(v, 3) for k, v in shifts.items()})
    assert set(table.index) == {"1D", "11"}, table.index
    assert abs(table.loc["1D", "share_readings"] - table.loc["1D", "share_cycles"]) < 0.02
    assert abs(table["lag_median_ms"] - 1.0).max() < 0.1
    assert max(shifts, key=shifts.get) == -1 and shifts[-1] > 0.95 > 0.2 > shifts[0], shifts
    print("event_tag selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("device", nargs="?")
    ap.add_argument("--start", help='local time, "YYYY-MM-DD HH:MM"')
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--events", nargs="+", default=BOOSTER_RESETS, help="TCLK event codes, hex")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    from logger_noise import guarded_get_many
    t1 = dt.datetime.fromisoformat(a.start).replace(tzinfo=ACL_TZ)
    t2 = t1 + dt.timedelta(minutes=a.minutes)
    events = {c.upper(): event_times(c, t1, t2) for c in a.events}
    print("event firings:", {c: len(v) for c, v in events.items() if len(v)})
    r = guarded_get_many()([f"{a.device}<-LOGGER:{int(t1.timestamp() * 1000)}:"
                            f"{int(t2.timestamp() * 1000)}"], timeout=300)[0]
    val = r.value if getattr(r, "ok", False) else None
    if not (isinstance(val, dict) and len(val.get("data", ()))):
        sys.exit(f"no logger data for {a.device} in that window")
    t = np.asarray(val["micros"]) / 1e6
    values = np.asarray(val["data"], float)
    table, shifts, span = analyze(t, values, events)
    print(f"{a.device}: {len(t)} readings over {span:.0f} s "
          f"({len(t) / span:.2f} per s; cycles at {1 / CYCLE_S:.0f} per s)")
    print(table.round(4).to_string())
    print("R^2 of values on tags, by shift k (cycles):", {k: round(v, 3) for k, v in shifts.items()})
    best, second = sorted(shifts, key=shifts.get, reverse=True)[:2]
    print(f"best k = {best} (R^2 {shifts[best]:.3f}); runner-up k = {second} "
          f"(R^2 {shifts[second]:.3f}): a close runner-up means a repeating cycle pattern")


if __name__ == "__main__":
    main()
