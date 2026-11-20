# Booster (Pacsys)

DRAFT: one environment for every Booster tuning task (injection, orbit, RF capture and
transition, extraction, notching, tune and chromaticity), unconfirmed until the hardware
owners sign off. A template picks the variables and readings for its task; this
environment holds them all. Reads and writes ACNET through pacsys, and reads only
(`settings_role` `nosettings`) unless a template names a writing role.

## What it can tune (variables)

Every device is listed, with its family, description, hard limits, and where those
limits came from, in `devices.csv` beside this file. The families:

- Injection: `L:C7PHAS` (periodic, 360 degrees; its logged setting changes on nearly
  every pulse and spent days in a second state near 316 degrees), `B:VIMIN` and its autotune targets
  `B:VIMTGT1`-`3`, `B:VIMAX`, `B:BFLAT`, the injection-line bends (`B:MH1`, `B:MH2`,
  `B:MV0`-`2`, `B:LAM`, `B:HTMH2`), quads (`B:Q10`...), trims, and the injection orbit bump.
- Linac boundary: Linac cavity 7 and debuncher phase and gradient, `L:V5QSET`,
  `L:RFQPAH`, `L:RFBPAH`, and the 400 MeV chopper `B:CHOP`.
- Ring orbit: the 96 correctors `B:HLn`, `B:HSn`, `B:VLn`, `B:VSn` (n = 1-24).
- Ring optics: quads `B:QLn`/`B:QSn`, sextupoles `B:SXLn`/`B:SXSn`, skew quads and
  skew sextupoles. What their base-device settings do (versus their ramp tables) is
  for the hardware owners to confirm.
- RF: injection and transition frequency, curve delay, phase-error gain, paraphase
  offsets (`B:DC1OFF`...), radial and anode settings, and gamma-t.
- Extraction and notching: kickers `B:MKS04`-`08`, extraction bumps and septa, notcher
  timing, and the MI8 bend `B:V803`.

Hard limits: for a setting the data logger keeps, the band it actually spent the last
90 days in, widened on each side (`range_source` logged). For one it does not keep, the
device database's setting limits, which are mostly the full supply range, not an
operating range (`range_source` db): a template for these must use small windows
around the current values. Settings with neither are left out.

## What it can read (objectives, constraints, observables)

- Losses: every Booster beam-loss monitor with a scalar reading (Short and Long
  `B:BLMS`/`B:BLML`, `B:BLMLAM`, the numbered `B:BLMnnn`), the BLM sums, and the
  Linac and injection-line loss monitors.
- Throughput: `B:BOOEFF` and the per-cycle efficiencies `B:BEFFnn`, charge (`B:CHG0`,
  `B:CHG122`, `B:IRMCHG`, ...), the DCCTs, `B:TORDMP`, `L:D7TOR`, `G:LINEFF`,
  `E:MBRATE`, and the injection turns `G:TURNnn`.
- Orbit: the ring and injection-line BPMs.
- `WorstLossNorm`: computed. `max` over the calibrated BLMs of
  `(reading - baseline) / scale`, both historical (see `_WORST_LOSS_BASELINE_SCALE` in
  the module); 28 of 49 BLMs are calibrated.

## Parameters (Machine Interface)

- `settings_role`: the DPM role used to write settings; `nosettings` reads only.
- `allow_auto_written`: empty. Some settings are also written by another loop:
  `B:VIMIN` by its autotune, and every setting whose logged value changes on more than
  10 % of its readings (`L:C7PHAS` on nearly every pulse, the 400 MeV trims, extraction
  kickers, gamma-t, ...; column `auto_written` in `devices.csv`). A write to one of these
  is refused, even with a writing role, unless this list names it, after its hardware
  owner confirms Badger and that loop will not fight. For `B:VIMIN`, its targets
  `B:VIMTGT1`-`3` are the gentler knob.
- `periodic_devices`: phases whose readings wrap (`L:C7PHAS`, `L:CDPHAS`: 360 degrees).
- `sample_events`, `average_events`: the clock event to read each device on, and how
  many events to average; defaults read one fresh value. Many Booster readings change
  from cycle to cycle with the cycle type (beam to MiniBooNE, studies, null cycles), so
  a template should read its losses on the event of the cycle it tunes.
- `debug`: print every read and write to the terminal.

## Safety

- Writes stay off (`nosettings`) until a template, reviewed by the hardware owner,
  names a role.
- Writes to settings another loop also writes (`auto_written`) stay refused until each
  is signed off.
- Ranges come from logged history and the device database, not from a sign-off.
