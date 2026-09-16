#!/usr/bin/env python
"""
Read-only diagnostic for RIL_tuning tuning templates.

Loads a template's environment.params and vocs.variables, constructs the
RIL_tuning Environment + BasicAcsysInterface exactly the way Badger itself
does (see badger.environment.instantiate_env), and calls env.get_variables()
to read the CURRENT LIVE values of every variable the template declares.
Prints each one next to its declared vocs hard bounds so you can see, in one
shot, which variable(s) are currently outside their template's range -- this
is what trips badger's "Current value is not within variable range!" error
when the mini GUI tries to auto-populate the initial-points table.

SAFETY: this script only calls Environment.get_variables() / Interface's
read path (get_settings). It never calls set_variables / set_values, so it
cannot change anything on the real accelerator -- it only reads.

Usage (run from the FermiBadgerPlugins repo root, inside FermiBadger_env):

    python check_RIL_tuning_live_bounds.py tuning_templates/RIL_tuning_trims_and_sol_LEBT_MEBTquads.yaml

If no path is given it defaults to that same template.
"""

import sys
import os
import importlib.util
import yaml

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.join(REPO_ROOT, "plugins")

# Badger normally puts BADGER_PLUGIN_ROOT on sys.path so that plugin modules
# can do bare imports like `from scanner import read_once, set_once` inside
# BasicAcsysInterface. Replicate that here.
sys.path.insert(0, PLUGIN_ROOT)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    template_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "tuning_templates/RIL_tuning_trims_and_sol_LEBT_MEBTquads.yaml"
    )
    template_path = os.path.join(REPO_ROOT, template_path) if not os.path.isabs(
        template_path
    ) else template_path

    with open(template_path) as f:
        template = yaml.safe_load(f)

    env_mod = load_module(
        "ril_tuning_env",
        os.path.join(PLUGIN_ROOT, "environments", "RIL_tuning", "__init__.py"),
    )
    intf_mod = load_module(
        "basic_acsys_interface",
        os.path.join(PLUGIN_ROOT, "interfaces", "BasicAcsysInterface", "__init__.py"),
    )

    Environment = env_mod.Environment
    Interface = intf_mod.Interface

    env_params = dict(template["environment"]["params"])

    # Older templates (badger_version < 1.4) carry stale singular
    # sample_event/setpoint keys from before the Environment class was
    # refactored to sample_events/setpoints (plural dicts). Badger's own
    # instantiate_env() silently ignores unrecognized kwargs (pydantic
    # extra='ignore' default), so this isn't strictly necessary, but we
    # drop them explicitly here to use the class's current, real defaults.
    env_params.pop("sample_event", None)
    env_params.pop("setpoint", None)

    print(f"Template: {template_path}")
    print(f"environment.params used: {env_params}\n")

    intf = Interface()
    env = Environment(interface=intf, **env_params)

    variables = template["vocs"]["variables"]
    names = list(variables.keys())

    print(f"Reading {len(names)} variables live via BasicAcsysInterface (read-only)...\n")
    current = env.get_variables(names)

    header = f"{'variable':10s} {'current':>16s} {'lo':>10s} {'hi':>10s}  status"
    print(header)
    print("-" * len(header))

    any_out = False
    any_missing = False
    for name in names:
        lo, hi = variables[name]
        val = current.get(name)
        if val is None:
            status = "NO READING"
            any_missing = True
        elif val < lo or val > hi:
            status = "OUT OF RANGE"
            any_out = True
        else:
            status = "ok"
        val_str = f"{val:.6g}" if isinstance(val, (int, float)) else str(val)
        print(f"{name:10s} {val_str:>16s} {lo:>10g} {hi:>10g}  {status}")

    print()
    if any_out:
        print(
            "At least one variable's live value is outside this template's declared "
            "vocs bounds. That's what's triggering badger's 'Current value is not "
            "within variable range!' error on load."
        )
    if any_missing:
        print(
            "At least one variable returned no reading (None) -- check device names "
            "and ACNET connectivity."
        )
    if not any_out and not any_missing:
        print(
            "All live values are within declared bounds. The load-time error may be "
            "transient (value moved between reads) -- try rerunning badger, or check "
            "vrange_limit_options / limit_option_idx handling in routine_page.py."
        )


if __name__ == "__main__":
    main()
