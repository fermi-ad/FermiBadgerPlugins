"""Operating ranges from the data logger: months of logged values per device, reduced day by
day. READ-ONLY: pacsys's write calls are disabled before any read (logger_noise's guard).

For settings, name the device with its property, e.g. B:VIMIN.SETTING. Each day is one
read of every device (bare logger DRF: the finest rate logged); a device with no data that
way is retried on logger_noise.EVENTS. Each day is reduced to n, min, p1, p50, p99, max,
the number of value changes, and its last value, plus up to SAMPLE readings drawn at
random, from which the whole span's quantiles come (<out>/<device>_sample.csv.gz, by day).

Periodic devices (--period L:C7PHAS.SETTING=360: 0 and 360 degrees are the same phase):
each day's values are first moved by whole periods to within half a period of that day's
circular mean, and the span's quantiles and extremes to within half a period of the
span's, so a phase near the wrap is not split into two far-apart groups.

ranges.csv, per device: days with data, min, p0.5, p1, p50, p99, p99.5, max over the
span, the days on which the value changed (settings: how often it is tuned), the median
share of a day's readings that differ from the one before (change_fraction: near 1, a
setting something writes continuously, such as a regulation loop), and the last value.

Run from the repo root (FNAL network or VPN):
    pixi run python scripts/logger_ranges.py B:VIMIN.SETTING L:C7PHAS.SETTING ...
        [--period L:C7PHAS.SETTING=360] [--end 2026-11-19] [--days 90]
        [--out logs/logger_ranges]
Daily summaries are cached in <out>/<device>.csv (one row per day; days already there are
not pulled again).
"""
import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from logger_noise import DAY_MS, EVENTS, guarded_get_many  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins"))
from periodic import unwrap as wrap  # noqa: E402  value moved to within period/2 of ref

SAMPLE = 500  # readings kept per device-day for the span's quantiles


def circular_mean(v, period):
    angle = 2 * np.pi * np.asarray(v, float) / period
    return period * np.arctan2(np.sin(angle).mean(), np.cos(angle).mean()) / (2 * np.pi)


def day_row(day, values, rng, period=None):
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return None, np.empty(0)
    if period:
        v = wrap(v, circular_mean(v, period), period)
    p1, p50, p99 = np.percentile(v, [1, 50, 99])
    row = {"day": day, "n": v.size, "min": v.min(), "p1": p1, "p50": p50, "p99": p99,
           "max": v.max(), "changes": int(np.count_nonzero(np.diff(v))), "last": v[-1]}
    return row, (v if v.size <= SAMPLE else rng.choice(v, SAMPLE, replace=False))


def read_day(get_many, devices, t1, t2):
    """{device: values} for one day: all devices in one bare-DRF read, then the other
    events for those that came back empty."""
    out, pending = {}, list(devices)
    for ev in EVENTS:
        if not pending:
            break
        drfs = [f"{d}{'@' + ev if ev else ''}<-LOGGER:{t1}:{t2}" for d in pending]
        try:
            readings = get_many(drfs, timeout=300)
        except Exception as error:  # noqa: BLE001  a failed read is reported, not fatal
            print(f"  {dt.datetime.fromtimestamp(t1 / 1000):%Y-%m-%d} {ev!r}: {error}"[:200],
                  file=sys.stderr)
            readings = [None] * len(drfs)
        still = []
        for d, r in zip(pending, readings):
            val = r.value if r is not None and getattr(r, "ok", False) else None
            if isinstance(val, dict) and len(val.get("data", ())):
                out[d] = val["data"]
            else:
                still.append(d)
        pending = still
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("devices", nargs="+")
    ap.add_argument("--end", default=dt.date.today().isoformat(), help="YYYY-MM-DD, local")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--out", default="logs/logger_ranges")
    ap.add_argument("--period", action="append", default=[], metavar="DEVICE=P",
                    help="a periodic device and its period (repeatable)")
    a = ap.parse_args()
    periods = {k: float(v) for k, v in (x.split("=") for x in a.period)}
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(0)
    end = dt.datetime.fromisoformat(a.end)
    days = [(end - dt.timedelta(days=k)).date().isoformat() for k in range(a.days, 0, -1)]
    path = {d: os.path.join(a.out, d.replace(":", "_") + ".csv") for d in a.devices}
    cached = {d: pd.read_csv(p) if os.path.exists(p) else pd.DataFrame() for d, p in path.items()}
    samples = {d: [] for d in a.devices}
    get_many = None
    for day in days:
        todo = [d for d in a.devices if cached[d].empty or day not in set(cached[d]["day"])]
        if not todo:
            continue
        get_many = get_many or guarded_get_many()
        t1 = int(dt.datetime.fromisoformat(day).timestamp() * 1000)
        got = read_day(get_many, todo, t1, t1 + DAY_MS)
        for d in todo:
            row, sample = day_row(day, got.get(d, ()), rng, periods.get(d))
            row = row or {"day": day, "n": 0}
            cached[d] = pd.concat([cached[d], pd.DataFrame([row])], ignore_index=True)
            samples[d].append(pd.DataFrame({"day": day, "value": sample}))
        print(f"{day}: {len(got)}/{len(todo)} devices with data", flush=True)
    for d in a.devices:
        cached[d].sort_values("day").to_csv(path[d], index=False)
        s = path[d].replace(".csv", "_sample.csv.gz")
        old = [pd.read_csv(s)] if os.path.exists(s) else []
        pd.concat(old + samples[d] + [pd.DataFrame(columns=["day", "value"])],
                  ignore_index=True).to_csv(s, index=False)
    rows = []
    for d in a.devices:
        c = cached[d][cached[d]["day"].isin(days) & (cached[d]["n"] > 0)]
        sample = pd.read_csv(path[d].replace(".csv", "_sample.csv.gz"))
        sample = sample.loc[sample["day"].isin(days), "value"].to_numpy(float)
        if c.empty or sample.size == 0:
            rows.append({"device": d, "days": 0})
            continue
        lo_x, hi_x = c["min"].to_numpy(float), c["max"].to_numpy(float)
        if d in periods:  # into one branch, around the span's circular mean
            ref, period = circular_mean(sample, periods[d]), periods[d]
            sample = wrap(sample, ref, period)
            lo_x, hi_x = wrap(lo_x, ref, period), wrap(hi_x, ref, period)
        lo, p1, med, p99, hi = np.percentile(sample, [0.5, 1, 50, 99, 99.5])
        rows.append({"device": d, "days": len(c), "min": lo_x.min(), "p0.5": lo, "p1": p1,
                     "p50": med, "p99": p99, "p99.5": hi, "max": hi_x.max(),
                     "change_days": int((c["changes"] > 0).sum()),
                     "change_fraction": float((c["changes"] / c["n"]).median()),
                     "last": c.sort_values("day")["last"].iloc[-1]})
    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(a.out, "ranges.csv"), index=False)
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
