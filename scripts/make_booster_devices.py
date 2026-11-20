"""Build plugins/environments/03_Booster_Pacsys/devices.csv, the Booster environment's
device table: every device a Booster tuning template may use, its role, and, for
variables, its hard limits and where they came from.

Inputs (local; none of them is committed):
  --inventory  a device inventory from fermi-ad/ad-tools (catalog plus device-database
               export, read offline): device, group, description, has_setting, array,
               db_status, setting_min, setting_max
  --ranges     ranges.csv from scripts/logger_ranges.py (settings, 90 days)
  --elog       per-device logbook counts (device, task_type, n_as_knob, n_as_watched)

Roles:
  variable    a scalar setting in a tuning family (VARIABLE_GROUPS) or an operator-tuned
              knob (EXTRA_VARIABLES)
  observable  readings: loss monitors, efficiencies, charge, intensity, BPMs, Linac losses
Hard limits of a variable (untested choices, for review by the machine experts):
  logged      the logger's p1 to p99 over the span (states held less than 1 % of the
              time, such as L:C7PHAS's excursions to about 320 degrees, left out), widened
              on each side by MARGIN x that span (at least MIN_REL x |median|), within the
              database's setting limits. For a periodic device, only readings within a
              quarter period of its last value count (its current state): L:C7PHAS spent
              days near 316 degrees as well as near 160 (2026-10-23 to 27), two states
              158 degrees apart, a question for the experts
  db          not logged: the database's setting limits (mostly the full DAC range, not
              an operating range; templates must use windows around current values), if
              they span at most DB_MAX_SPAN units (wider is a full integer or float
              range, e.g. a timing table's 0 to 2^32 - 1: no information)
  (none)      not logged and no usable database limits: left out, listed in notes
auto_written: a setting that changes on more than AUTO_FRACTION of its logged readings
(median day), or a known autotune target: something else writes it, likely a regulation
or autotune loop. The environment refuses to write these unless its allow_auto_written
lists them (the hardware owner's sign-off). AUTO_FRACTION is an untested threshold.

Run from the repo root:
    pixi run python scripts/make_booster_devices.py --inventory <adtools_inventory.csv>
        --ranges logs/logger_ranges/ranges.csv --elog <elog_booster_devices.csv>
"""
import argparse
import os
import re
import sys

import numpy as np
import pandas as pd

OUT = "plugins/environments/03_Booster_Pacsys/devices.csv"
MARGIN, MIN_REL = 0.25, 0.02
AUTO_FRACTION = 0.1
AUTO_WRITTEN = {"B:VIMIN"}  # its own autotune loop (B:VIMLUP2 heartbeat, targets B:VIMTGT1-3)
BIG = 1e30
DB_MAX_SPAN = 1e6  # untested threshold; see the docstring
VARIABLE_GROUPS = re.compile(
    r"BOOSTER\.(CORRECTORS_|QUADS_|SEXT_|SKEW_|KICKERS|MK04)|LTB\.(BENDS_|HTMH2|QUADS$|TRIMS_|misc)"
    r"|LINAC\.CAVITY|DB\.(EXT_BUMP|EXT_SEPTUM|INJ_ORBUMP|NOTCH|RF_|TRANSITION)"
    r"|BOOSTER\(commented\)\.GAMMA_T")
NOT_KNOBS = re.compile(r"^L:K[7D]PHGN$|^B:INJPTS$")  # loop gains and point counts
# operator-tuned (logbook) settings outside those groups: {device: (description, min, max)}
# from the device-database export where the inventory lacks them
EXTRA_VARIABLES = {
    "B:VIMIN": ("GMPS IMIN read/set; SAFETY: its own autotune loop also writes it", None, None),
    "B:VIMTGT1": ("VIMIN autotune target, BLS060/BLS130, mode 1", None, None),
    "B:VIMTGT2": ("VIMIN autotune target, BLS060/BL1250, mode 2", None, None),
    "B:VIMTGT3": ("VIMIN autotune target, BLS120/BL1250, mode 3", None, None),
    "B:VIMAX": ("GMPS IMAX read/set", None, None),
    "B:BFLAT": ("Magnetic field flat at injection, A", -40.0, 40.0),
    "B:INJFRQ": ("LLRF injection frequency, MHz", 0.0, 480.0),
    "B:TTXFRQ": ("LLRF transition frequency, MHz", 0.0, 480.0),
    "B:CRVDLY": ("LLRF frequency curve delay, us", None, None),
    "B:PHERGN": ("LLRF phase error gain, 2^n", None, None),
    "B:POTAIN": ("Anode pot A at injection, V", -10.24, 10.24),
    "B:RSTDLY": ("Booster reset delay to TLG, us", None, None),
    "B:N750DY": ("Q-switch fine delay, 26 ns each", None, None),
    "B:V803": ("MI8 vertical bend at 803 and 809, A", -500.0, 500.0),
    "B:CHOP": ("400 MeV chopper PS, kV", -80.0, 80.0),
    "L:V5QSET": ("Linac RF station 5 phase set point, deg", None, None),
    "L:RFQPAH": ("RFQ phase adjust, deg", 0.0, 400.0),
    "L:RFBPAH": ("RF buncher phase adjust, deg", -398.0, 398.0),
}
PERIODIC = {"L:C7PHAS": 360.0, "L:CDPHAS": 360.0}  # phase: 0 and 360 deg are the same
OBSERVABLE_GROUPS = re.compile(
    r"BOOSTER\.(BEAM_LOSS_MONITORS|EFFICIENCY|CHG|BPMS_|TURNS)|DB\.DCCT|LTB\.(BPMS|LOSS_MONITORS)")
EXTRA_OBSERVABLES = {
    "B:CHG0": "Charge through cycle", "B:CHG122": "Charge at 8 GeV", "B:IRMCHG": "BLM Booster charge",
    "B:TORDMP": "Booster dump toroid", "B:RPOS": "Radial position", "B:NOKD": "Notcher kicker",
    "B:LOSBAL1": "BLS060/BLS130 ratio (VIMIN autotune)", "B:BLQ160": "BLM sum Q16, event 10",
    "B:BLV1U0": "BLM sum V1U, event 10", "E:MBRATE": "MiniBooNE intensity rate",
    "G:LINEFF": "Linac efficiency", "L:D7TOR": "Linac output toroid", "L:TUNRAD": "Linac loss",
    "L:TK1RAD": "Linac loss", "L:TK4RAD": "Linac loss", "L:D7LMSM": "Linac loss sum",
    "L:D34LM": "Linac loss", "L:D23LM": "Linac loss", "L:D72LM": "Linac loss", "L:D41LM": "Linac loss",
    "WorstLossNorm": "computed: max over calibrated BLMs of (reading - baseline) / scale",
}


def finite(x):
    return x is not None and not pd.isna(x) and abs(float(x)) < BIG


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--ranges", required=True)
    ap.add_argument("--elog", required=True)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    inv = pd.read_csv(a.inventory).drop_duplicates("device").set_index("device")
    rng = pd.read_csv(a.ranges)
    rng["device"] = rng["device"].str.removesuffix(".SETTING")
    rng = rng.set_index("device")
    elog = pd.read_csv(a.elog)
    elog = elog[elog.task_type == "ALL"].set_index("device")

    scalar_set = inv[(inv.has_setting == "Y") & (inv.array == "no") & (inv.db_status == "ok")]
    variables = {d: (r.group, r.description, r.setting_min, r.setting_max)
                 for d, r in scalar_set.iterrows()
                 if VARIABLE_GROUPS.match(str(r.group)) and not NOT_KNOBS.match(d)}
    for d, (desc, lo, hi) in EXTRA_VARIABLES.items():
        r = inv.loc[d] if d in inv.index else None
        variables[d] = ("logbook knob", desc,
                        lo if lo is not None else (r.setting_min if r is not None else None),
                        hi if hi is not None else (r.setting_max if r is not None else None))

    rows = []
    for d, (group, desc, db_lo, db_hi) in sorted(variables.items()):
        row = {"device": d, "role": "variable", "family": group, "description": desc,
               "periodic": PERIODIC.get(d, "")}
        db_ok = (finite(db_lo) and finite(db_hi)
                 and 0 < float(db_hi) - float(db_lo) <= DB_MAX_SPAN)
        if d in rng.index and rng.loc[d, "days"] > 0:
            r = rng.loc[d].copy()
            sample = os.path.join(os.path.dirname(a.ranges), f"{d.replace(':', '_')}.SETTING_sample.csv.gz")
            if d in PERIODIC and os.path.exists(sample):  # its current state only
                sys.path.insert(0, "plugins")
                from periodic import unwrap
                v = unwrap(pd.read_csv(sample)["value"].to_numpy(float), r["last"], PERIODIC[d])
                v = v[np.abs(v - r["last"]) <= PERIODIC[d] / 4]
                r["p1"], r["p50"], r["p99"] = np.percentile(v, [1, 50, 99])
            span = r["p99"] - r["p1"]
            m = max(MARGIN * span, MIN_REL * abs(r["p50"]), 1e-6)
            lo, hi = r["p1"] - m, r["p99"] + m
            if db_ok and d not in PERIODIC:
                lo, hi = max(lo, float(db_lo)), min(hi, float(db_hi))
            row |= {"lo": lo, "hi": hi, "range_source": "logged",
                    "logged_p1": r["p1"], "logged_p50": r["p50"], "logged_p99": r["p99"],
                    "change_days": int(r["change_days"]), "logged_days": int(r["days"]),
                    "change_fraction": round(float(r["change_fraction"]), 4)}
        elif db_ok:
            row |= {"lo": float(db_lo), "hi": float(db_hi), "range_source": "db"}
        else:
            row |= {"range_source": "none", "notes": "not logged and no usable DB limits: left out"}
        rows.append(row)

    obs = {d: (r.group, r.description) for d, r in inv.iterrows()
           if OBSERVABLE_GROUPS.match(str(r.group)) and r.has_reading == "Y" and r["array"] == "no"
           and r.db_status == "ok" and d not in variables}
    obs |= {d: ("logbook" if d != "WorstLossNorm" else "computed", desc)
            for d, desc in EXTRA_OBSERVABLES.items() if d not in variables}
    rows += [{"device": d, "role": "observable", "family": g, "description": desc}
             for d, (g, desc) in sorted(obs.items())]

    table = pd.DataFrame(rows)
    table["logbook_knob"] = table.device.map(elog["n_as_knob"]).fillna(0).astype(int)
    table["logbook_watched"] = table.device.map(elog["n_as_watched"]).fillna(0).astype(int)
    table["auto_written"] = table.device.isin(AUTO_WRITTEN) | (
        table.get("change_fraction", pd.Series(0.0, index=table.index)).fillna(0) > AUTO_FRACTION)
    for c in ("lo", "hi", "logged_p1", "logged_p50", "logged_p99"):
        table[c] = table[c].map(lambda x: float(f"{x:.6g}") if finite(x) else np.nan)
    table.to_csv(a.out, index=False)
    v = table[table.role == "variable"]
    print(f"wrote {a.out}: {len(v)} variables ({(v.range_source == 'logged').sum()} logged, "
          f"{(v.range_source == 'db').sum()} DB limits, {(v.range_source == 'none').sum()} "
          f"left out), {(table.role == 'observable').sum()} observables")


if __name__ == "__main__":
    main()
