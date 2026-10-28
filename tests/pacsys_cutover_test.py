"""Guard for the Pacsys cutover (2026-10-28): every real-world tuning template
(not simulation/, not saved/) uses a Pacsys (or test) environment, never an
Acsys one. The Acsys environments stay in the repo, unused.

Run from the repo root:
    pixi run python tests/pacsys_cutover_test.py
"""
from pathlib import Path

import yaml

templates = [
    p for p in Path("tuning_templates").rglob("*.yaml")
    if p.parts[1] not in ("simulation", "saved")
]
assert templates
acsys = {str(p): yaml.safe_load(p.read_text())["environment"]["name"] for p in templates}
acsys = {p: e for p, e in acsys.items() if e.endswith("_Acsys")}
assert not acsys, f"templates still on Acsys: {acsys}"
named = [str(p) for p in templates if p.stem.endswith("_Acsys")]
assert not named, f"templates still named _Acsys: {named}"
print(f"PACSYS CUTOVER TEST PASSED ({len(templates)} real-world templates)")
