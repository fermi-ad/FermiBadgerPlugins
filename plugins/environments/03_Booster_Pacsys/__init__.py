# Booster: every device a Booster tuning template may use (variables, objectives,
# constraints, observables), read from devices.csv beside this file. That table is built by
# scripts/make_booster_devices.py from the fermi-ad/ad-tools device inventory, 90 days of
# data-logger settings, and 24 months of Booster logbook entries (docs/booster-environment.md
# has the sources and rules). Everything here is a DRAFT: devices and ranges are unconfirmed
# until the hardware owners sign off, per this repo's convention.
#
# SAFETY: some settings are also written by another loop: B:VIMIN by its autotune
# (B:VIMLUP2 heartbeat, targets B:VIMTGT1-3), and every setting whose logged value changes
# on more than 10 % of its readings (L:C7PHAS on nearly every pulse; the 400 MeV trims,
# extraction kickers, gamma-t, ...): devices.csv column auto_written. set_variables
# refuses to write these unless allow_auto_written names them, which must wait for the
# hardware owner to confirm that Badger and that loop will not fight. The environment
# reads only (settings_role 'nosettings') until a template names a role.
import csv
import os
from typing import Dict, List

from badger import environment
from badger.errors import BadgerNoInterfaceError

_DEVICES = os.path.join(os.path.dirname(__file__), "devices.csv")
with open(_DEVICES, newline="") as _f:
    _ROWS = list(csv.DictReader(_f))
# variables: hard limits [lo, hi]; ones without a usable range are left out (see the table)
_VARIABLES = {r["device"]: [float(r["lo"]), float(r["hi"])] for r in _ROWS
              if r["role"] == "variable" and r["range_source"] in ("logged", "db")}
_OBSERVABLES = [r["device"] for r in _ROWS if r["role"] == "observable"]
_PERIODIC = {r["device"]: float(r["periodic"]) for r in _ROWS if r.get("periodic")}
_AUTO_WRITTEN = {r["device"] for r in _ROWS if r.get("auto_written") == "True"}


# Per-device (baseline, scale) for the normalized "worst loss" objective: the elog shows
# operators chasing whichever ring sector is spiking that day (S01, S04, S06, S08, S13,
# L15, L22, ...), not one fixed device -- so the objective is
#     WorstLossNorm = max_d (reading_d - baseline_d) / scale_d
# over every Booster Short/Long BLM, rather than betting on one sector. baseline = the
# historical median reading, scale = the historical IQR (p75-p25), both pooled from
# before+after logger readings over 929 injection-tuning sessions back to 2024
# (docs/reflections/booster_injection/).
#
# Only 28/49 BLMs are calibrated here. Excluded, deliberately rather than guessed:
#   - Most B:BLML02-24 (all but 01/10/11): n = 14, below the n >= 20 gate used
#     throughout this reflection -- these Long BLMs are logged in only ~1-5% of
#     sessions (confirmed 2026-11-12: a bare, no-@event LOGGER DRF returns data for
#     the Shorts and B:BLMLAM almost every time, but rarely for the Longs). Untested
#     whether a different logging event would recover them; they stay in
#     `observables` for live reads but drop out of the WorstLossNorm max().
_WORST_LOSS_BASELINE_SCALE = {
    "B:BLMS01": (0.015, 0.002), "B:BLMS02": (0.016, 0.003), "B:BLMS03": (0.018, 0.003),
    "B:BLMS04": (0.015, 0.002), "B:BLMS05": (0.015, 0.001), "B:BLMS06": (0.009, 0.890),
    "B:BLMS07": (0.00967, 0.00040), "B:BLMS08": (0.01072, 0.00034), "B:BLMS09": (0.01142, 0.00045),
    "B:BLMS10": (0.01033, 0.00025), "B:BLMS11": (0.01036, 0.00028),
    "B:BLMS12": (0.009, 0.001), "B:BLMS13": (0.009, 0.005), "B:BLMS14": (0.009, 0.002),
    "B:BLMS15": (0.009, 0.002), "B:BLMS16": (0.010, 0.002), "B:BLMS17": (0.010, 0.002),
    "B:BLMS18": (0.019, 0.002), "B:BLMS19": (0.019, 0.002), "B:BLMS20": (0.019, 0.002),
    "B:BLMS21": (0.018, 0.002), "B:BLMS22": (0.018, 0.002), "B:BLMS23": (0.017, 0.002),
    "B:BLMS24": (0.015, 0.005), "B:BLML01": (0.016, 0.002), "B:BLML10": (0.010, 0.002),
    "B:BLML11": (0.010, 0.003), "B:BLMLAM": (0.010, 0.003),
    # B:BLMS06 and B:BLML01/10/11 above are calibrated from n in the dozens, not the
    # ~1850 the other Shorts have -- low-confidence, flagged here rather than dropped.
    # B:BLMS07-11 have a much smaller IQR than the other Shorts (narrower baseline
    # loss band, not a dead channel -- each still shows hundreds of distinct values
    # and real spikes up to 4.0) so a small reading change there normalizes large;
    # untested whether that is the physically correct sensitivity.
}
_WORST_LOSS_DEVICES = (
    [f"B:BLMS{i:02d}" for i in range(1, 25)]
    + [f"B:BLML{i:02d}" for i in range(1, 25)]
    + ["B:BLMLAM"]
)


class Environment(environment.Environment):
    name = "03_Booster_Pacsys"
    # Hard limits are the live readback bands actually seen in the screenshots, NOT a
    # hardware owner's sign-off -- see the module docstring.
    variables = _VARIABLES
    observables = _OBSERVABLES

    # --- Parameters ---------------------------------------------------------------
    settings_role: str = 'nosettings'
    debug: bool = False
    # Confirmed 2026-11-11: a bare DRF (no @event) returns logger/live data for every
    # device above; explicit periodic/clock-event qualifiers (@p,15000, @e,52, ...)
    # returned nothing for the BLMs and B:BOOEFF here, unlike the Linac/RIL environment.
    sample_events: Dict[str, str] = {}
    average_events: Dict[str, int] = {"default": 1}
    periodic_devices: Dict[str, float] = dict(_PERIODIC)
    allow_auto_written: List[str] = []  # SAFETY: see the module comment

    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_settings(variable_names, debug=self.debug)

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
        refused = sorted((set(settable_devices) & _AUTO_WRITTEN) - set(self.allow_auto_written))
        if refused and self.settings_role != "nosettings":
            # RuntimeError, not BadgerError: that one opens a Qt dialog, which a run worker lacks
            raise RuntimeError(f"{', '.join(refused)}: also written by another loop (autotune "
                               "or regulation); Badger may not write them until "
                               "allow_auto_written names them (the hardware owner's sign-off).")
        self.interface.set_values(
            settable_devices, settings_role=self.settings_role,
            periods=self.periodic_devices, debug=self.debug,
        )

    def get_observables(self, observable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        requested = list(observable_names)  # never change the caller's list
        to_read = [n for n in requested if n != "WorstLossNorm"]
        if "WorstLossNorm" in requested:
            to_read += [d for d in _WORST_LOSS_DEVICES if d not in to_read]

        result = self.interface.get_values(
            to_read, sample_events=self.sample_events, periods=self.periodic_devices,
            average_events=self.average_events, debug=self.debug,
        )

        if "WorstLossNorm" in requested:
            normed = []
            for d in _WORST_LOSS_DEVICES:
                bs = _WORST_LOSS_BASELINE_SCALE.get(d)
                if bs is None:
                    continue  # not yet calibrated; excluded rather than guessed
                baseline, scale = bs
                normed.append((result[d] - baseline) / scale)
            result["WorstLossNorm"] = max(normed) if normed else float("nan")

        return {n: result[n] for n in requested}
