# `setup.sh` — one-command setup for a fresh clone

## Context

A user who clones this repo today follows ~6 manual README steps: create the
conda env, activate it, find the site-packages path, apply four patches from
three different directories with two different strip levels, then hand-edit five
absolute paths in `config.yaml`. Every one of those paths is currently hard-coded
to `/Users/stjohn/Development/...`, so the repo is unusable from any other
location — and `config.yaml` is *tracked*, so editing it dirties the working
tree for every user.

This plan adds `setup.sh` at the repo root to do all of it, from a clone at an
arbitrary path (including under `/tmp`).

### What exploration established

**Patches do not share an application recipe.** Verified by dry-run against a
pristine Badger 1.6.0 tree (`~/miniconda3/pkgs/badger-opt-1.6.0-pyhd8ed1ab_0/site-packages`):

| patch | apply from | strip |
|---|---|---|
| `pydantic_editor-badger-1.6.0-dict-subtypes.patch` | `<sp>/badger/gui/components` | `-p1` |
| `badger-mini-config.patch` | `<sp>` | `-p1` |
| `badger-mini-var-table-env-configs.patch` | `<sp>` | `-p1` |

All three apply cleanly to pristine 1.6.0. The `-p0` invocations in
[patches/README.md](patches/README.md) and [README.md](README.md) are **wrong**
for the first one (`patch -p0` there prompts "File to patch:"); the README is
corrected as part of this work.

**The xopt patch is not reproducible and must be excluded.** Diffing pristine
`xopt-3.2.1` against this environment shows the live tree carries ~127 lines of
hand-edits to `xopt/pydantic.py` and `xopt/generators/bayesian/turbo.py` (a
`model_dump` override, an `_initial_state_value` PrivateAttr, a
`model_dump_json` override) that **no file in `patches/` contains**.
`xopt-pydantic-serialization-fix.patch` and `apply_xopt_fix.py` both *remove or
amend* that hand-written code — their context lines and search strings are
absent from a pristine install, so neither can run on a fresh clone
(`grep -c 'super(XoptBaseModel, self).model_dump' pristine/turbo.py` → 0). The
patch header is also malformed (`patch` rejects it at line 22). The setup script
therefore skips xopt and prints a one-line notice; regenerating that patch from
the pristine baseline is listed under "Not in scope".

**`config.yaml` structure.** Five `is_path: true` settings need real values;
`config_MCR.yaml` is the same file with MCR paths, confirming the intended
pattern. Badger's `ConfigSingleton.load_or_create_config`
(`badger/settings.py:156`) does a plain `yaml.safe_load` and validates each entry
as a `Setting`, so a generated sibling file loads identically via `-cf`.

**Templates carry CWD-relative lattice paths** (`sim_configs/DeliveryRing/...madx`
in all three `tuning_templates/*.yaml`), and `create_VA()` does a bare
`Path(self.lattice_filename)` at
[__init__.py:250](plugins/environments/VirtualAccelerator_MADXSuite/__init__.py#L250),
so Badger only works when launched from the repo root.

---

## Changes

### 0. Write this plan to the repo first

Before any code: save this plan verbatim (Context, Changes, Files touched,
Verification) to **`docs/2026-09-15-setup-script-plan.md`**, so it lives with the
work rather than only in the session, and is reviewable/diffable alongside the
implementation. `docs/` already holds the running history
(`progress.md`, `log.md`, the dated summaries), so it is the established home.
Add a pointer line to it from `docs/progress.md` when the work is logged at the
end of the session.

### 1. `setup.sh` (new, repo root, executable)

`bash`, `set -euo pipefail`. Finds the repo from its own location
(`SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`) — never `pwd`, so
it works from anywhere and under `/tmp`. Flags: `--env-name NAME`,
`--yes` (non-interactive: accept every default, never prompt), `--skip-env`
(patches + config only), `--help`.

**Step 1 — conda.** Locate via `conda info --base`; hard-fail with an install
pointer if absent. Source `"$(conda info --base)/etc/profile.d/conda.sh"` before
any `conda activate` — the shell function is not available to a non-interactive
script. Default env name read from `environment.yml` (`name: FermiBadger_env`).

If `conda env list` already has that name, prompt with three choices:

```
Environment 'FermiBadger_env' already exists.
  [r] remove and recreate   [n] use a different name   [k] keep it as-is, just patch & configure
```

`--yes` takes `k` (keep) — the safe default; automation should never silently
delete an environment. `n` re-prompts for a name and loops the existence check.

Then `conda env create -n "$ENV_NAME" -f environment.yml --yes`, and
`conda activate "$ENV_NAME"`. On failure, print the `acsys`/FNAL-network
troubleshooting note already in [README.md](README.md) and exit non-zero.

**Step 2 — patches.** Resolve site-packages *from the target env*, not the
caller's:

```bash
SP=$(conda run -n "$ENV_NAME" python -c "import sys, sysconfig; print(sysconfig.get_paths()['purelib'])")
```

A small `apply_patch <dir> <strip> <file>` helper drives the table above and is
idempotent — the reason each patch needs a per-entry directory:

```
if patch -d "$dir" -p"$strip" -R --dry-run --force < "$f" >/dev/null 2>&1; then
    echo "  already applied: $(basename "$f")"          # reverse applies cleanly
elif patch -d "$dir" -p"$strip" --dry-run --force < "$f" >/dev/null 2>&1; then
    patch -d "$dir" -p"$strip" --force < "$f"           # clean forward apply
else
    echo "  FAILED: $(basename "$f")"; FAILED=1          # record, keep going
fi
```

`--force` suppresses `patch`'s interactive "Assume -R? [y]" prompt, which would
otherwise hang an unattended run. Re-running `setup.sh` is safe. Any failure is
reported at the end with a non-zero exit, but does not abort the remaining
steps — a partly-patched env is more useful than a half-configured one.

Skip `xopt-pydantic-serialization-fix.patch` / `apply_xopt_fix.py` with a printed
note (see Context).

**Step 3 — `config.local.yaml`.** Generated from the tracked `config.yaml` by a
small inline Python snippet run through the env's interpreter (PyYAML is a Badger
dependency, so it is present; `sed` on YAML is the flimsier option). It loads
`config.yaml`, overwrites only the five `value:` fields below, and dumps with
`sort_keys=True, default_flow_style=False` so the file stays diff-comparable with
the tracked template:

| setting | value |
|---|---|
| `BADGER_PLUGIN_ROOT` | `$REPO/plugins` |
| `BADGER_TEMPLATE_ROOT` | `$REPO/tuning_templates` |
| `BADGER_LOG_DIRECTORY` | `$REPO/logs` |
| `BADGER_ARCHIVE_ROOT` | prompted, default `~/BadgerArchive` |
| `BADGER_LOGBOOK_ROOT` | prompted, default `~/BadgerLogs` |

The two prompts show the default and accept Enter; `--yes` or a non-TTY stdin
(`[ -t 0 ]`) takes the defaults silently. `~` is expanded and the paths are made
absolute before writing. All four directories are created with `mkdir -p`.

If `config.local.yaml` already exists, prompt before overwriting (`--yes`
overwrites — the paths are derived, not hand-authored).

**Step 4 — verify.** Run the env's python on a three-line check: import badger,
`init_settings(config.local.yaml)`, and assert
`'VirtualAccelerator_MADXSuite' in list_env()`. This is the one runnable check
the whole script leaves behind — it fails if the plugin root is wrong, the patch
set broke an import, or the env is incomplete. Then print the launch command:

```
badger -g   -cf <repo>/config.local.yaml      # full GUI
badger -mini -cf <repo>/config.local.yaml -t tuning_templates/DR_BetatronTunes_sim.yaml
```

### 2. `.gitignore` — add `config.local.yaml`

So the generated file never reaches a commit and `git pull` never conflicts on it.

### 3. Lattice paths resolve against the repo root

[plugins/environments/VirtualAccelerator_MADXSuite/__init__.py](plugins/environments/VirtualAccelerator_MADXSuite/__init__.py) —
a module-level constant beside the existing ones, and a two-line fallback in
`create_VA()` at line 250:

```python
# Templates carry repo-relative lattice paths, so Badger need not be launched
# from the repo root.  plugins/environments/<name>/__init__.py -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
...
self._lattice_path = Path(self.lattice_filename)
if not self._lattice_path.is_absolute() and not self._lattice_path.is_file():
    self._lattice_path = REPO_ROOT / self.lattice_filename
```

CWD keeps priority, so nothing currently working changes. The existing
`FileNotFoundError` a few lines down still catches a genuinely missing file.

One consequence to fix in the same edit: the slow-path fallback
`_update_madx_variables` re-opens `self.lattice_filename` at
[line 546](plugins/environments/VirtualAccelerator_MADXSuite/__init__.py#L546);
that becomes `self._lattice_path` so both paths agree on which file they mean.

### 4. Documentation

- [README.md](README.md) — replace Quick Start steps 2–4 with `./setup.sh`, and
  correct the stale `-p0` patch instructions in the manual fallback.
- [patches/README.md](patches/README.md) — correct the dict-subtypes recipe to
  `-p1` from `gui/components`, and note that the xopt patch does not apply to a
  pristine 3.2.1 install.

### Not in scope

- Regenerating `xopt-pydantic-serialization-fix.patch` against pristine 3.2.1 so
  a fresh clone gets the TurboController serialization fix. Separate task; the
  hand-edits exist only in this machine's env and need to be captured as a real
  diff first.
- Replacing `test-quick-start.sh` — it clones from GitHub and builds a *separate*
  throwaway env, which is a different job from setting up the clone you have.

---

## Files touched

| file | change |
|---|---|
| `docs/2026-09-15-setup-script-plan.md` | **new** — this plan, written first |
| `setup.sh` | **new** — the whole script |
| `.gitignore` | one line: `config.local.yaml` |
| `plugins/environments/VirtualAccelerator_MADXSuite/__init__.py` | `REPO_ROOT` + fallback in `create_VA()`; line 546 uses `_lattice_path` |
| `README.md`, `patches/README.md` | Quick Start rewrite; correct `-p0` → `-p1` |

---

## Verification

**1. Fresh clone under `/tmp`, the case the user named.** This is the real
end-to-end test and takes several minutes (conda solve); no timeout.

```bash
git clone . /tmp/fbp-setup-test && cd /tmp/fbp-setup-test
./setup.sh --env-name FermiBadger_setuptest --yes
grep -A1 'BADGER_PLUGIN_ROOT' config.local.yaml    # expect /tmp/fbp-setup-test/plugins
```

Expected: env created, 3 patches applied, `config.local.yaml` written with
`/tmp` paths, step-4 check reports the plugin discovered.

**2. Idempotence.** Re-run `./setup.sh --env-name FermiBadger_setuptest --yes`
in the same clone: every patch must report "already applied", and the script must
exit 0 without prompting or double-applying.

**3. Existing-environment prompt.** Run without `--yes` against the existing
`FermiBadger_env`, answer `k`; confirm it patches and configures without
touching the env.

**4. Lattice resolution from another directory** — the point of change 3:

```bash
cd /tmp && /Users/stjohn/miniconda3/envs/FermiBadger_env/bin/python -c "
import sys; sys.path.insert(0, '<repo>')
from plugins.environments.VirtualAccelerator_MADXSuite import Environment
e = Environment(interface=None)
print(e._lattice_path)"
```

Expected: the repo-root absolute path, no `FileNotFoundError`.

**5. The existing five checks still pass**, run with
`/Users/stjohn/miniconda3/envs/FermiBadger_env/bin/python` from the repo root —
change 3 touches a hot path:

```
plugins/environments/VirtualAccelerator_MADXSuite/madx_deferred.py
tests/VA_deferred_expressions_test.py
tests/VA_plugin_smoke_test.py
tests/VA_template_integration_test.py
tests/VA_gui_param_editor_test.py
```

**6. Cleanup** after step 1–2:
`conda env remove -n FermiBadger_setuptest --yes && rm -rf /tmp/fbp-setup-test`.
