# Read noise of RIL and Booster devices, from the data logger

First look, 2026-11-18: `scripts/logger_noise.py` (method and column meanings in its
docstring). Data-logger reads only (`DEVICE<-LOGGER:t1:t2`), never live readings, with
pacsys's write calls disabled. Purpose: is the machine's read noise Gaussian, how does
it scale with level, and is `s^2/N` (the planned `<name>_var` from `average_events`) a
fair variance for an N-event average? See `docs/heteroskedastic-noise-model.md`.

## Method, in brief

- Steady stretches are found from the readings alone (the RIL settings are logged as
  well, via the bare DRF, every 1-15 s; also cutting at setting changes is untested):
  windows of W = 20 consecutive logged readings, kept when the von Neumann ratio eta
  (mean squared successive difference / variance; 2 for independent noise) is at least
  1.3. Steps and drifts lower eta; spikes and dropouts do not. Results on synthetic data
  are insensitive to eta_min over 1.0-1.6 and to W over 20-40; W = 10 is too short to
  show 1 % spikes (`--selftest`).
- Every shape statistic is compared with Gaussian noise put through the same code,
  since a 20-reading window biases them: skewness 0.00, excess kurtosis -0.45, share
  beyond 4 robust sigmas (tail4) 0.003.
- R (new term): the variance of a window's mean over `s^2/W`, its variance if the
  readings were independent, from adjacent windows that are steady together. R = 1 for
  independent noise (1.00 for the Gaussian reference; about 0.9 in the synthetic
  check, where small level steps inflate `s^2`), and 4.3 for noise with lag-1
  correlation 0.6 (theory 4.0). R > 1 means `s^2/N` understates the noise of an N-event
  average.
- The bare logger DRF (no `@event`) returns the finest rate logged: per pulse (15 Hz)
  for L:D7TOR, B:VIMIN, and B:BLMLAM; every 1 s (G:LINEFF), 15 s (the L:*RAD loss
  monitors), or 30 s (B:BOOEFF) for the others. Every device an earlier probe (`@event`
  forms only) listed as unloggable returns data this way, the RIL `.SETTING`s included.

## Findings

Ranges are over level bins (6 quantile bins of the steady-window means).

| device | logged every | days | level | std | std / level | skew | exkurt | tail4 | R |
|---|---|---|---|---|---|---|---|---|---|
| L:D7TOR | 0.067 s | 1 | 24.5-24.9 | 0.12-0.14 | 0.5 % | -0.07 to -0.19 | -0.43 to -0.23 | 0.003-0.005 (0.017 lowest bin) | 1.6-2.1 |
| G:LINEFF | 1 s | 14 | 91.5-93.7 | 0.19-0.28 | 0.2-0.3 % | -0.06 to 0.26 | -0.43 to -0.27 | 0.006-0.011 | 1.0-1.4 |
| L:TK1RAD | 15 s | 14 | 16.0-23.9 | 0.085-0.14 | 0.5-0.6 % | -0.12 to 0.01 | -0.42 to -0.32 | 0.010-0.020 | 1.6-2.9 |
| L:TK4RAD | 15 s | 14 | 28.6-43.9 | 0.17-0.26 | 0.6 % | about 0 | -0.36 to 0.07 | (quantized) | 1.9-3.5 |
| L:TUNRAD | 15 s | 14 | 48-86 | 0.23-0.52 | 0.5-0.6 % | about 0 | -0.46 to 0.12 | (quantized) | 1.3-4.4 |
| B:BOOEFF | 30 s | 14 | 90.2-92.9 | 0.55-0.66 | 0.6-0.7 % | -0.04 to -0.68 | -0.87 to -0.49 | 0.013-0.039 | 1.1-3.4 |
| B:BLMLAM | 0.067 s | 1 | 0.0094-0.0096 | 6e-5 to 3e-4 | 0.6-3 % | +1.0 to +1.7 | 0.15 to 2.4 | 0.07-0.15 | 1.0-1.2 |
| Gaussian, same W | | | | | | 0.00 | -0.45 | 0.003 | 1.00 |

- **Size and scaling.** The Linac devices' noise is 0.5-0.6 % of their level, nearly
  the same for the beam toroid and the loss monitors, and roughly proportional to level
  over the ranges seen. Since L:TUNRAD's noise grows from 0.23 to 0.52 as its level rises
  from 48 to 86, the noise varies across a run, which favors the heteroskedastic GP.
  Shared pulse-to-pulse beam-intensity fluctuation is a likely common cause (untested:
  correlate each loss monitor with L:D7TOR pulse by pulse).
- **Shape.** The cores are near Gaussian for L:D7TOR, L:TK1RAD, and G:LINEFF, but the
  tails are heavier: beyond 4 robust sigmas 1.1-6.5 times as often as Gaussian noise
  (5.4 times in L:D7TOR's lowest bin, which holds pulse dropouts). B:BOOEFF
  is skewed low (dips), more so at higher efficiency (-0.68 at 92.9 %), which is the
  shape that breaks a risk tolerance on a lower bound (heteroskd-calibration: lognormal).
  B:BLMLAM is skewed high with heavy tails.
- **`s^2/N` understates the noise of an average.** For L:D7TOR, read per pulse as
  `average_events` does, R = 1.6-2.1: consecutive pulses are correlated (lag-1
  autocorrelation about 0.6 over a raw stretch), so an N-pulse mean is 1.6-2 times
  noisier, in variance, than `s^2/N` says. The slow-logged devices give R = 1.3-4.4, but
  there a window spans 5-10 minutes, so R also counts slow wander. A `_var` taken as
  `s^2/N` would make the GP, and any risk tolerance, overconfident by about this factor.
- **Quantization.** L:TK4RAD and L:TUNRAD read in steps of 0.305 (the noise is 0.7-1.2
  steps), so their tail statistics are artifacts of the steps. L:D7TOR steps by 0.0031
  (40 steps per sigma), L:TK1RAD by 0.0031, and B:BOOEFF by 0.031. B:BLMLAM steps by
  5e-5 (about 2.7 steps per sigma), and 34 % of its consecutive logged values repeat.
- **Not usable per pulse.** B:VIMIN: only 0.3 % of windows are steady; its value cycles
  with a period of about 15 pulses (1 s), so per-pulse data mix Booster cycle types.

## Limits and open avenues

- One day (per-pulse devices) or 14 days (the others), ending 2026-11-18, in one running
  period. Levels span less than a factor of 2 for every device, so the law of noise vs
  level is only seen locally; the log-log slope is not reported for that reason. Wider
  ranges need periods with other machine conditions (studies, start-up, beam-off
  pedestals).
- Within one window, a slow drift and correlated noise look alike; the eta cut removes
  both, so strongly correlated stretches are under-represented and R may be understated.
- Untested: per-cycle Booster data (logger reads with an `@e,XX` event for one cycle
  type), the Badger-relevant time scale for the 15 s devices (they are not logged per
  pulse; a live per-pulse sample would need a separate, read-only acquisition), and
  correlations between devices.
- Next for the noise model: an `average_events` `_var` corrected for correlation
  (batch means, or `s^2/N` times a per-device R), then a rerun of the calibration study
  with skewed and correlated noise matched to these numbers.

Reproduce (FNAL network; raw pulls cached under `logs/logger_noise/`, not committed):

    pixi run python scripts/logger_noise.py --end 2026-11-18 --days 1
    pixi run python scripts/logger_noise.py --end 2026-11-18 --days 14 \
        --devices L:TK4RAD L:TUNRAD L:TK1RAD G:LINEFF B:BOOEFF --out logs/logger_noise/slow14
