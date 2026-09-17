---
name: basic-pacsys-interface-port
description: BasicAcsysInterface ported to pacsys as BasicPacsysInterface; API mapping, two bugs fixed, what's still unverified
metadata:
  type: project
---

# `BasicPacsysInterface`: porting `BasicAcsysInterface` from acsys-py to pacsys

## What and why

`plugins/interfaces/BasicPacsysInterface/` is a new Badger interface plugin
with the same feature set as `plugins/interfaces/BasicAcsysInterface/`, but
built on [pacsys](https://github.com/fermi-ad/pacsys) instead of
`acsys`/our own `plugins/scanner.py`. `BasicAcsysInterface` is untouched —
both interfaces coexist; no environment has been switched over to the new
one yet.

pacsys postdates this model's training data and its GitHub repo is private,
so the plan was built by cloning it directly (`git clone
git@github.com:fermi-ad/pacsys.git`, works via existing SSH access) and
reading the source/README, not from memory. `pip install pacsys` also works
(it's on public PyPI) even though the repo itself needs auth to browse.

## API mapping (acsys-py + scanner.py → pacsys)

pacsys is natively synchronous and thread-safe, so **`plugins/scanner.py`
has no equivalent in the new interface** — no asyncio, no `DPMContext`, no
hand-rolled timeout/empty-list guards.

| Old | New |
|---|---|
| `acsys.run_client(read_once, drf_list=..., sample_events={...})` | `pacsys.get_many(drfs, timeout=...)` — sample events go inline per-DRF string (`"L:CDPHAS@e,52,e,0"`), not a side dict |
| `acsys.run_client(set_once, drf_list=..., value_list=..., settings_role=...)` | `with pacsys.dpm(auth=pacsys.KerberosAuth(), role=settings_role) as be: be.write_many(list(zip(drfs, values)))` — opened per `set_values()` call, same session-per-call cost as before |
| manual `.SETTING` suffix (`extract_setting_devices`) | not needed — `write()`/`write_many()` append `.SETTING`/`@I` automatically; `extract_setting_devices` only needs to pick the settable side of a read/set pair now |
| manual circular-buffer settle-to-tolerance loop | kept as-is — it's a stability check (spread of last N samples), not a target-match check, so `pacsys.Verify` doesn't replace it; only its I/O call changed |
| no read error-checking | `pacsys.get_many()` returns `Reading` objects with a real `.ok`; `get_values()`/`get_settings()` now raise `pacsys.errors.DeviceError` on a bad reading instead of silently propagating garbage |

`pacsys.testing.FakeBackend` (has `.set_reading()`/`.set_error()`/
`.was_written()`) is the test double — see
`plugins/interfaces/BasicPacsysInterface/test_basic_pacsys_interface.py`,
wired in via a private `_backend_override` attr on the interface (`None` in
production).

pacsys versions: GitHub `main` was `0.3.0` when read; PyPI publishes `0.2.2`
(installed and pinned in `environment.yml`). The parts this port uses
(`get_many`, `write_many`, `dpm()`, `KerberosAuth`, `Reading.ok`,
`WriteResult.success`, `testing.FakeBackend`) are identical in both —
checked by installing 0.2.2 for real and comparing against the cloned
source, not assumed.

## Two bugs found in `BasicAcsysInterface` while writing this (not fixed there)

Writing fresh code surfaced two real bugs that exist in `BasicAcsysInterface`
today. They're **not** fixed in the old file (out of scope — wasn't asked to
touch it), but the new interface doesn't repeat them:

1. **`get_values(names)` with no `sample_events` arg `KeyError`s.**
   `get_values`'s own signature defaults `sample_events={}`, and that empty
   dict gets passed straight through to `read_once(..., sample_events=
   sample_events)` — which shadows `read_once`'s *own* default of
   `{'default':'@i'}` (that default only applies when the kwarg is omitted
   entirely, not when an empty dict is explicitly passed). Inside
   `read_once`, every device name misses the `sample_events.keys()` check
   and falls to `sample_events['default']` → `KeyError` on the empty dict.
   This is exactly the call shape Badger's own `Environment.get_variables()`
   uses (`self.interface.get_values(variable_names)`, no sample_events) for
   a plain current-value read. `BasicPacsysInterface` uses
   `.get('default', '@i')` instead of `['default']`, so an empty/missing
   dict falls back to `'@i'` instead of crashing.

2. **Settle loop's fast-path branch has a dead `self.` bug that's masked by
   a second bug.** In `set_values()`'s settle-to-tolerance loop, the "buffer
   just became full" branch calls bare `meets_tolerance(...)` (no `self.`
   — `meets_tolerance` is a method, not a module function, so this would
   `NameError`). It's never actually reached, though, because the guard
   above it, `buffer_full = np.all(np.where(~np.isnan(circ_buffers[setdev])))`,
   is `np.all` over the *indices* `np.where` returns (not over a boolean
   array) — so `buffer_full` is `False` any time index `0` is among the
   filled positions, which is always true once a front-filling buffer is
   full. The two bugs cancel: `BasicAcsysInterface` has never crashed here
   in production, it just always falls through to the slower roll-buffer
   branch (`self.meets_tolerance(...)`, spelled correctly) one iteration
   later than it could. `BasicPacsysInterface` fixes both together:
   `buffer_full = not np.isnan(circ_buffers[setdev]).any()` and
   `self.meets_tolerance(...)`.

If `BasicAcsysInterface` is ever touched again, both are worth fixing there
too for the same reason.

## Verification status

- **Done:** 8 offline assert-based checks against `FakeBackend` (DRF
  parsing, both `get_values` bugs above, `get_settings`, the `nosettings`
  no-op guard, the settle loop reaching tolerance and writing). `pacsys`
  installed for real in `FermiBadger_env` and its API confirmed to match.
- **Not done — no controls-network access from this environment:** a live,
  Kerberos-authenticated write via `pacsys.dpm(auth=KerberosAuth(),
  role=...)` against a real DPM role (e.g. `ril_tuning_fake`,
  `linac_quads`), to confirm it behaves like acsys-py's
  `dpm.enable_settings(role=...)` did. Do this before pointing any
  environment's `configs.yaml` `interface:` at `BasicPacsysInterface` for
  real use.

## Files

- `plugins/interfaces/BasicPacsysInterface/__init__.py`
- `plugins/interfaces/BasicPacsysInterface/configs.yaml`
- `plugins/interfaces/BasicPacsysInterface/test_basic_pacsys_interface.py`
- `environment.yml` — added `pacsys==0.2.2`

Committed as `2ea9ab5`, pushed to `origin/main`.
