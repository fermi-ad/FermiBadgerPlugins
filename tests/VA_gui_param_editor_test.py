"""GUI param editor test: verify GUI config loading works.

Reproduces routine_page.py:1137 exactly: load the env through the factory,
then feed configs['params'] to BadgerPydanticEditor.set_params_from_dict —
the function that raised "Dict type must have subtypes" — using an
offscreen Qt platform so no display is needed.

Run from the repo root:
    ~/miniconda3/envs/Badger_154_VirtAcc/bin/python tests/VA_gui_param_editor_test.py
"""
import os

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from badger.settings import init_settings
init_settings(os.path.join(REPO_ROOT, 'config.yaml'))

from PyQt5.QtWidgets import QApplication
app = QApplication([])

from badger.factory import get_env
from badger.gui.components.pydantic_editor import BadgerPydanticEditor

for env_name in ['VirtualAccelerator_MADXSuite', 'SimpleVirtualAccelerator']:
    Env, configs = get_env(env_name)
    editor = BadgerPydanticEditor()
    # The exact call from routine_page.select_env (line 1137)
    editor.set_params_from_dict(configs['params'])
    print(f'{env_name}: GUI param editor accepted all '
          f'{len(configs["params"])} params')

print('GUI EDITOR TEST PASSED')
