import yaml
import os
import logging

# Path to the config_profiles directory (relative to this file)
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config_profiles')
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.yaml")

def load_settings():
    ensure_settings_yaml_exists()
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE, "r") as file:
        return yaml.safe_load(file) or {}


def save_settings(settings):
    with open(SETTINGS_FILE, "w") as file:
        yaml.dump(settings, file)

def update_setting(key, value):
    settings = load_settings()
    settings[key] = value
    save_settings(settings)

def update_settings(updates: dict):
    settings = load_settings()
    settings.update(updates)  # add/update multiple keys
    save_settings(settings)


def load_led_settings(default_pwm=255, default_enabled=False) -> dict:
    settings = load_settings()
    pwm = settings.get("led_pwm", default_pwm)
    enabled = settings.get("led_enabled", default_enabled)
    try:
        pwm = int(pwm)
    except Exception:
        pwm = int(default_pwm)
    pwm = max(0, min(255, pwm))
    return {
        "led_pwm": pwm,
        "led_enabled": bool(enabled),
    }


def save_led_settings(led_pwm=None, led_enabled=None):
    updates = {}
    if led_pwm is not None:
        try:
            pwm = int(led_pwm)
        except Exception:
            pwm = 255
        updates["led_pwm"] = max(0, min(255, pwm))

    if led_enabled is not None:
        updates["led_enabled"] = bool(led_enabled)

    if updates:
        update_settings(updates)


def save_camera_settings(index, data: dict):
    settings = load_settings()
    # Ensure the camera_settings section exists
    if "camera_settings" not in settings:
        settings["camera_settings"] = {}
    index_str = str(index)
    # If this camera already has an entry, only update the fields
    if index_str not in settings["camera_settings"]:
        settings["camera_settings"][index_str] = {}
    settings["camera_settings"][index_str].update(data)
    save_settings(settings)


def load_camera_settings(index=None) -> dict:
    settings = load_settings()
    camera_settings = settings.get("camera_settings", {})
    if index is not None:
        return camera_settings.get(str(index), {})
    return camera_settings

def ensure_settings_yaml_exists(filepath=SETTINGS_FILE):
    """Ensure the settings.yaml exists in the config_profiles folder."""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    if not os.path.exists(filepath):
        logging.getLogger(__name__).info(f"[INFO] {filepath} not found, creating...")
        try:
            with open(filepath, "w") as f:
                yaml.dump({}, f)
            logging.getLogger(__name__).info(f"[OK] Empty {filepath} created.")
        except Exception as e:
            logging.getLogger(__name__).error(f"[ERROR] Failed to create {filepath}: {e}")
    # else: keep existing settings file
