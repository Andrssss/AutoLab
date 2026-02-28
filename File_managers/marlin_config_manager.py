import yaml
import os
import logging
from Pozitioner_and_Communicater.gcode_presets import DEFAULT_SETTINGS

# Path to the config_profiles directory and marlin_settings.yaml
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config_profiles')
SETTINGS_PATH = os.path.join(CONFIG_DIR, "marlin_settings.yaml")


def ensure_marlin_settings_exists():
    """Ensure the marlin_settings.yaml file exists with default values."""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    if not os.path.exists(SETTINGS_PATH):
        logging.getLogger(__name__).info(f"[INFO] {SETTINGS_PATH} not found, creating with default settings...")
        save_settings(DEFAULT_SETTINGS)
    # else: keep existing settings file


def load_settings():
    ensure_marlin_settings_exists()
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_settings(data):
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


def get_settings_path():
    return SETTINGS_PATH
