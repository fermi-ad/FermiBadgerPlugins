# Booster injection tuning. Devices and ranges confirmed 2026-11-11 by reading ACNET
# parameter-page and strip-chart screenshots attached to Booster elog entries (DevDB is
# still unreachable from the dev Mac); WorstLoss baseline/scale confirmed from the
# tuning-reflection pull over ~935 historical injection-tuning sessions
# (docs/reflections/booster_injection/). Everything here is a DRAFT: unconfirmed until
# the hardware owner signs off, per this repo's convention.
#
# SAFETY: B:VIMIN runs its own background autotune (B:VIMLUP2 heartbeat, B:VIMERR,
# B:VIMMOD, B:VIMDIAG, targets B:VIMTGT1-3/A-C). It is listed as a variable here on the
# user's instruction (2026-11-11), but do NOT set a settings_role other than
# 'nosettings' on this environment until the hardware owner confirms how Badger writes
# to B:VIMIN interact with that autotune loop -- the two control loops could fight.
from typing import Dict

from badger import environment
from badger.errors import BadgerNoInterfaceError

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
    name = "03_Booster_InjectionTuning_Pacsys"
    # Hard limits are the live readback bands actually seen in the screenshots, NOT a
    # hardware owner's sign-off -- see the module docstring.
    variables = {
        "L:C7PHAS": [140.0, 180.0],   # Linac accel.-cavity RF phase, DEG; shared Linac/Booster boundary device
        "B:VIMIN": [95.0, 110.0],     # GMPS injection-porch current, AMPS -- SAFETY: see module docstring
        "B:VIMAX": [900.0, 1000.0],   # GMPS extraction-flattop current, AMPS
        "B:MH1": [330.0, 380.0],      # Horizontal Bend #1 PS, AMPS
        "B:MH2": [670.0, 710.0],      # 400 MeV Horz Bend PS, AMPS (seen alarmed at 692/691 in one screenshot)
        "B:MV1": [360.0, 400.0],      # Vertical Bend #1 PS, AMPS
        "B:MV2": [350.0, 390.0],      # Vertical Bend #2 PS, AMPS
    }
    observables = [
        "B:BOOEFF",   # floor constraint in the template, not the objective -- see its description
        "G:LINEFF",
        *_WORST_LOSS_DEVICES,
        "WorstLossNorm",
    ]

    # --- Parameters ---------------------------------------------------------------
    settings_role: str = "nosettings"
    debug: bool = False
    # Confirmed 2026-11-11: a bare DRF (no @event) returns logger/live data for every
    # device above; explicit periodic/clock-event qualifiers (@p,15000, @e,52, ...)
    # returned nothing for the BLMs and B:BOOEFF here, unlike the Linac/RIL environment.
    sample_events: Dict[str, str] = {}
    average_events: Dict[str, int] = {"default": 1}
    periodic_devices: Dict[str, float] = {}

    def get_variables(self, variable_names: list[str]) -> dict:
        if not self.interface:
            raise BadgerNoInterfaceError
        return self.interface.get_settings(variable_names, debug=self.debug)

    def set_variables(self, settable_devices: dict[str, float]):
        if not self.interface:
            raise BadgerNoInterfaceError
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
