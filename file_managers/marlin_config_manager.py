import yaml
import os
from My_G_codes.gcode_presets import DEFAULT_SETTINGS

SETTINGS_PATH = "marlin_settings.yaml"

def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        save_settings(DEFAULT_SETTINGS)
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f: # működik linuxon is
        return yaml.safe_load(f)

def save_settings(data):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)

def get_settings_path():
    return SETTINGS_PATH
