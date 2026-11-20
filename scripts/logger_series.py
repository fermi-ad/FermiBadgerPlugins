"""Logged time series, binned: per device and day, statistics of its logged values in each
BIN-second bin: median, p10, p90, count, and on_median, the median of the values above
ON_FRACTION of the bin's p95. Readings sampled on every cycle mix beam and no-beam cycles
(about nine in ten Booster resets were null cycles in a 2026-11-19 sample), so a plain
median of a toroid can sit near 0 while beam cycles carry full current; on_median is the
beam-on level (ON_FRACTION is an untested choice). READ-ONLY (logger reads through logger_noise's guarded pacsys; one read
of every device per day, as scripts/logger_ranges.py).

Run from the repo root (FNAL network or VPN):
    pixi run python scripts/logger_series.py DEV ... [--end 2026-11-19] [--days 90]
        [--bin 300] [--out logs/logger_series]
Writes <out>/<device>/<day>.csv (bin start in epoch s and the statistics); days already
there are not pulled again. load(out, devices, stat) returns one wide DataFrame (bins x
devices) of one statistic.
"""
import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from logger_noise import DAY_MS, guarded_get_many  # noqa: E402
from logger_ranges import read_day  # noqa: E402

ON_FRACTION = 0.2


def bin_stats(v):
    v = np.asarray(v, float)
    p95 = np.percentile(v, 95)
    on = v[v > ON_FRACTION * p95] if p95 > 0 else v
    return pd.Series({"median": np.median(v), "p10": np.percentile(v, 10),
                      "p90": np.percentile(v, 90), "n": v.size,
                      "on_median": np.median(on) if on.size else np.nan})


def day_path(out, device, day):
    return os.path.join(out, device.replace(":", "_"), f"{day}.csv")


def load(out, devices, stat="on_median"):
    cols = {}
    for d in devices:
        folder = os.path.join(out, d.replace(":", "_"))
        parts = [pd.read_csv(os.path.join(folder, f)) for f in sorted(os.listdir(folder))] if os.path.isdir(folder) else []
        parts = [x for x in parts if len(x)]
        if parts:
            cols[d] = pd.concat(parts).set_index("t")[stat]
    return pd.DataFrame(cols).sort_index()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("devices", nargs="+")
    ap.add_argument("--end", default=dt.date.today().isoformat())
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--bin", type=float, default=300.0)
    ap.add_argument("--out", default="logs/logger_series")
    a = ap.parse_args()
    end = dt.datetime.fromisoformat(a.end)
    get_many = None
    for k in range(a.days, 0, -1):
        day = (end - dt.timedelta(days=k)).date().isoformat()
        todo = [d for d in a.devices if not os.path.exists(day_path(a.out, d, day))]
        if not todo:
            continue
        get_many = get_many or guarded_get_many()
        t1 = int(dt.datetime.fromisoformat(day).timestamp() * 1000)
        got = read_day(get_many, todo, t1, t1 + DAY_MS)
        if not got:  # every read failed (network?): leave the day unwritten, so it is retried
            print(f"{day}: no data for any device; not cached", flush=True)
            continue
        for d in todo:
            t, v = got.get(d, ((), ()))
            df = pd.DataFrame({"t": np.floor(np.asarray(t, float) / a.bin) * a.bin,
                               "v": np.asarray(v, float)}).dropna()
            g = (df.groupby("t")["v"].apply(bin_stats).unstack().reset_index() if len(df)
                 else pd.DataFrame(columns=["t", "median", "p10", "p90", "n", "on_median"]))
            os.makedirs(os.path.dirname(day_path(a.out, d, day)), exist_ok=True)
            g.to_csv(day_path(a.out, d, day), index=False)
        print(f"{day}: {len(got)}/{len(todo)} devices with data", flush=True)


if __name__ == "__main__":
    main()
