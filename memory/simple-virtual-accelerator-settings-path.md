---
name: simple-virtual-accelerator-settings-path
description: SimpleVirtualAccelerator's settings_filename resolves relative to the plugin dir, not Badger's CWD
metadata:
  type: project
---

`plugins/environments/99_Sim_SimpleVirtualAccelerator/__init__.py` reads and
writes its quad-strength settings file (`SimpleVirtualAccelerator_settings.yaml`
by default) through a `_settings_path` property that resolves
`settings_filename` against `Path(__file__).parent` — the plugin's own
directory — falling through unchanged only if the configured path is already
absolute.

Before 2026-09-18 this was a bare `Path(self.settings_filename)`, resolved
against whatever directory Badger's process happened to be launched from.
Since the README's Quick Start launches Badger from the repo root, that
silently made the repo-root copy of the settings file the one actually read
and written, while an identically-named copy sitting in the plugin's own
directory sat there stale and drifted out of sync (different `kqd`/`kqf`
values) without anyone touching it directly — it just never got loaded or
saved to. The root-root-vs-plugin-dir duplicate was cleaned up as part of the
fix; only the plugin-directory copy exists now, and it is the one used
regardless of where `badger` is launched from.

If another environment plugin ever needs to read/write a file next to its
own module (not a lattice or template path, which Badger resolves separately),
resolve it the same way — relative to `Path(__file__).parent` — rather than
trusting the process's CWD.
