"""Checks the docs behind the GUI's two Parameters buttons stay complete.

Machine Interface -> plugins/environments/<env>/README.md: every environment has
one, and it mentions every parameter its class declares.
Optimization Algo -> docs/algorithms/<generator>.md: every algorithm Badger
offers has one. Both load through Badger (badger-1.6.0-plugin-docs.patch).

Badger's docs window drops a leading '---' block and breaks tables, so neither
may appear.

Run from the repo root:
    pixi run python tests/plugin_docs_test.py
"""
import importlib
import re
from pathlib import Path

from badger.settings import init_settings

init_settings("config.local.yaml")
from badger.environment import Environment as BaseEnvironment  # noqa: E402
from badger.factory import list_generators, load_badger_docs, load_plugin_docs  # noqa: E402

ENVS = Path("plugins/environments")
ALGOS = Path("docs/algorithms")
failures = []


def check_markdown(path, text):
    if re.search(r"^\s*---\s*$", text, re.M):
        failures.append(f"{path}: a '---' line (Badger's docs window hides what follows)")
    if re.search(r"^\s*\|", text, re.M):
        failures.append(f"{path}: a table (Badger's docs window breaks them)")


for env_dir in sorted(p for p in ENVS.iterdir() if (p / "__init__.py").exists()):
    readme = env_dir / "README.md"
    if not readme.exists():
        failures.append(f"{readme}: missing")
        continue
    text = readme.read_text()
    check_markdown(readme, text)
    try:
        cls = importlib.import_module(f"environments.{env_dir.name}").Environment
    except Exception as e:  # e.g. a syntax error: the README must say so
        if "Known issue" not in text:
            failures.append(f"{env_dir.name}: does not import ({e}) and README has no 'Known issue'")
        continue
    for field in cls.model_fields:
        if field not in BaseEnvironment.model_fields and f"`{field}`" not in text:
            failures.append(f"{readme}: parameter `{field}` not documented")
    shown = load_plugin_docs(env_dir.name, "environment")
    if "Docstrings" in shown and "\nNone\n" in shown:
        failures.append(f"{env_dir.name}: docs window would show an empty 'Docstrings ... None' block")

for name in list_generators():
    page = ALGOS / f"{name}.md"
    if not page.exists():
        failures.append(f"{page}: missing")
        continue
    check_markdown(page, page.read_text())
    shown = load_badger_docs(name, "generator")
    if page.read_text().splitlines()[0] not in shown:
        failures.append(f"{name}: Badger does not load {page}")

for f in failures:
    print("FAIL", f)
assert not failures, f"{len(failures)} problem(s)"
print("plugin_docs_test ok")
