"""Clock-event counts per time bin: how many Booster beam cycles of each type fired in each
BIN-second bin, from ACL's event_log over HTTP (read-only; one request per event and day,
sequential). In 2026-11, $10 ("Bstr: generic reset ac beam") fired once per beam cycle and
never on a null cycle ($11), so its count is the beam rate; the type events say which
beam (TCLK names, 2026-11-20): $1D beam to MiniBooNE (BNB), $19 NuMI beam, $13 fixed
target, $14 MI/Muon studies, $15 MI/RR studies, $16 MI studies, $17 Booster studies,
$1C 8 GeV beam to Muon; and $1A, NTF parasitic beam enable (Linac beam to the Neutron
Therapy Facility).

Run from the repo root (FNAL network or VPN):
    pixi run python scripts/event_counts.py [--end 2026-11-20] [--days 90] [--bin 300]
        [--events 10 13 14 15 16 17 19 1A 1C 1D] [--out logs/event_counts]
Writes <out>/<event>/<day>.csv (bin start in epoch s, count); days already there are not
fetched again. load(out, events) returns a wide DataFrame (bins x events), 0 where none.
"""
import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from event_tag import event_times, ACL_TZ  # noqa: E402

EVENTS = ["10", "13", "14", "15", "16", "17", "19", "1A", "1C", "1D"]


def load(out, events=EVENTS):
    cols = {}
    for e in events:
        folder = os.path.join(out, e)
        if not os.path.isdir(folder):
            continue
        parts = [pd.read_csv(os.path.join(folder, f)) for f in sorted(os.listdir(folder))]
        parts = [x for x in parts if len(x)]
        if parts:
            cols[f"${e}"] = pd.concat(parts).set_index("t")["count"]
    return pd.DataFrame(cols).fillna(0).sort_index()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--end", default=dt.date.today().isoformat())
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--bin", type=float, default=300.0)
    ap.add_argument("--events", nargs="+", default=EVENTS)
    ap.add_argument("--out", default="logs/event_counts")
    a = ap.parse_args()
    end = dt.datetime.fromisoformat(a.end)
    for k in range(a.days, 0, -1):
        day = (end - dt.timedelta(days=k)).date()
        t1 = dt.datetime.combine(day, dt.time(), tzinfo=ACL_TZ)
        counts = {}
        for e in a.events:
            path = os.path.join(a.out, e, f"{day}.csv")
            if os.path.exists(path):
                continue
            try:
                times = event_times(e, t1, t1 + dt.timedelta(days=1))
            except Exception as error:  # noqa: BLE001  a failed day is retried on the next run
                print(f"{day} ${e}: {error}", file=sys.stderr)
                continue
            b = pd.Series(np.floor(times / a.bin) * a.bin).value_counts().sort_index()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            pd.DataFrame({"t": b.index, "count": b.values}).to_csv(path, index=False)
            counts[e] = len(times)
        if counts:
            print(f"{day}: " + " ".join(f"${e} {n}" for e, n in counts.items()), flush=True)


if __name__ == "__main__":
    main()
