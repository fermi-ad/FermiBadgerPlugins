# Booster tuning templates on 03_Booster_Pacsys

## Context

The Booster-wide environment `03_Booster_Pacsys` (d5cb46d) holds the Booster's devices. The
user wants one tuning template per Booster task, each with everything the logbook says
operators touch (knobs) or read (watched numbers) for that task, all checked by default:
injection (exists; fill out), orbit, RF capture, RF transition (two templates, the user's
choice), extraction, notching, tunes, chromaticity.

Evidence: logbook mining (24 months; `scratchpad/booster/elog_booster_devices.csv`, per task:
knob and watched counts). Tunes/chromaticity name devices in only 5 of 52 entries; the user
asked to OCR those entries' screenshot attachments for device names, and to use pacsys and
ad-tools for ramps and tables. Found: fermi-ad's internal Elog OCR tools (glyph-matching OCR for the
ACNET fonts: `pipeline/ocr_glyph.py`, `classify.py`, `param_vs_app.row_kind`; HTTP fetch
`pipeline/fetch.py`, ~49k images cached); pacsys `ramp.py` (Booster ramp-card tables);
DC-offset arrays `B:<X>O.SETTING[k]`; BTUNE tune arrays `B:BTHTN1-3`, `B:BTVTN1-3`.

Gaps: logbook knobs missing from the environment (notcher delays B:TNOKAU/TNOKDU, B:POTBIN,
B:CIG, B:K06D1D, B:MKS11, ...); readings missing (B:LM805, BLM sums B:BLQ30/50/70,
B:BLLAM0, B:BLMV20, toroids B:TORL10/20, notcher readbacks B:NOKDC/D/E/I/J/P/R, septum
B:MP02/03, BTUNE arrays). B:NOKD (the logbook's main notching knob) has no setting.
`BasicPacsysInterface` cannot address an array-element setting (it appends `.SETTING`
after the range; pacsys needs `DEV.SETTING[k]`).

## Plan

Stage A: six templates from logbook text (no new interface code)

1. **RF split** of the logbook's one RF task by its own concepts and knobs: capture
   (B:INJFRQ, B:CRVDLY, B:PHERGN, B:POTAIN, B:POTBIN, B:CIG; injection frequency 40,
   capture tune 34, curve delay 31) and transition (B:DC1OFF and paraphase siblings,
   B:TTXFRQ, gamma-t B:GMTV; transition frequency 27, transition losses 17). Devices named
   for both (B:RPOS, BLMs, correctors, B:VIMIN) go in both.
2. **Extend the environment** (`scripts/make_booster_devices.py`, `devices.csv`): add each
   logbook-named device (prefixes B:, L:, G:) that the device-database export has and that
   is not obsolete: scalar settable -> variable (range from a 90-day `scripts/logger_ranges.py`
   pull, else DB limits under the existing rules, else left out); readable scalar ->
   observable; tune arrays -> observables through the existing `<DRF>|<reduce>`
   (e.g. `B:BTHTN1[0:8]|mean`; which elements mean what is undocumented, flagged).
   Excluded: autotune internals and control flags (B:VIMDBUG, B:VIMLASN, ...), other
   machines (I:, E:, M:), non-beam (B:SUMPSE).
3. **Template generator** `scripts/make_booster_templates.py`, the pattern of
   `scripts/make_dr_task_templates.py`: per task, variables = every logbook-named knob that
   is an environment variable (all checked); observables = every watched device in the
   environment plus B:BOOEFF, G:LINEFF, charge, DCCT; per-task lists as constants with their
   logbook counts (names and numbers only). Shared from the injection template: generator
   (EI, SafetyTurboController), initial points, `relative_to_current: true`, `nosettings`,
   `allow_auto_written: []`, periodic devices. Hard limits from `devices.csv`; windows
   (limit_option_idx 2): logged settings delta = half their 90-day p1-p99 span, DB-range
   settings delta = 1 % of the DB span (untested; stated). Objectives (untested choices
   from what the logbook watches): injection, orbit, RF capture, RF transition: minimize
   `WorstLossNorm`; extraction, notching: minimize B:BLM026 (extraction-region BLM, most
   watched there). Constraint everywhere: B:BOOEFF >= 91 (injection's historical floor).
   Files: `tuning_templates/development/03_Booster_{InjectionTuning,Orbit,RFCapture,
   RFTransition,Extraction,Notching}_Pacsys.yaml` (injection regenerated, its description
   facts kept).

Stage B: tunes and chromaticity (after OCR evidence)

4. **OCR the tune/chromaticity entries' screenshots**: re-query the logbook read-only
   (tunnel, `common.require_elog()`) for the 52 tune_chromaticity entry ids (same
   classification rules); their attachment ids from `entries_files`/`comments_files`;
   images from that tool's image cache or fetcher; decode with
   `pipeline/classify.py` + `ocr_glyph.py`; keep tokens matching the device-name regex
   that exist in the DB export; count per entry and per device. Accuracy: on ~10 images,
   compare against a visual read; report recall and precision (logbook rules: no prose or
   images committed, only names, counts, entry ids).
5. **Indexed settings in `BasicPacsysInterface`** (shared by every Pacsys environment;
   behavior unchanged for plain names): form setting DRFs with pacsys's own parser
   (`pacsys.drf3.parse_request(...).to_canonical(property=SETTING)`) so `B:SXS7O[3]`
   becomes `B:SXS7O.SETTING[3]`; offline tests with a FakeBackend for plain, indexed, and
   ranged names; the archetype test still passes.
6. **Templates `03_Booster_Tunes_Pacsys` and `03_Booster_Chromaticity_Pacsys`**: variables
   = the OCR- and text-named knobs (likely QL/QS DC offsets `B:Q*O[k]` for tunes,
   SXL/SXS offsets `B:SX*O[k]` for chromaticity, with the slot k the screenshots show);
   observables = BTUNE tune arrays (reduced), BLMs, efficiency; objective minimize
   `WorstLossNorm` (no tune target is known; a tune-target objective would need the target
   from the experts). Flagged: what each DC-offset slot and BTUNE element means, and
   pacsys's 100 kHz sextupole card vs this repo's `BMA_RampOffset.py` 5 kHz (to check).
   Writing whole ramp tables (`pacsys.ramp`) is out of scope (open item).

Common

7. **Tests**: `tests/03_Booster_Pacsys_test.py`: every Booster template's variables and
   observables are in the environment, its hard limits match `devices.csv`, every variable
   is on limit_option_idx 2; interface tests for indexed settings; template lint.
8. **Docs**: `docs/booster-environment.md` (per template: knobs, objective, sources, OCR
   accuracy), environment README, TODO, log.

## Verification

- `pixi run python scripts/make_booster_templates.py`; `tests/template_lint_test.py`
  (0 failing), `tests/03_Booster_Pacsys_test.py`, `tests/plugin_docs_test.py`,
  `tests/archetype_test.py`.
- Offscreen GUI load of each Booster template with a FakeBackend (as in
  `tests/constraint_risk_tolerance_gui_test.py`): loads, all variables checked, no errors.
- Full suite before push; nothing written to ACNET (writes off; FakeBackend in tests;
  logbook and logger reads only).
- Unexplored: any template on the machine; whole-ramp writes; event-specific reads
  (`sample_events`) for the cycle-type-dependent BLMs.
