import yaml
import os

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
    settings.update(updates)  # több kulcsot is hozzáad/frissít
    save_settings(settings)


def save_camera_settings(index, data: dict):
    settings = load_settings()
    # Biztosítjuk, hogy legyen camera_settings rész
    if "camera_settings" not in settings:
        settings["camera_settings"] = {}
    index_str = str(index)
    # Ha már van bejegyzés ehhez a kamerához, csak frissítsük a mezőket
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
        print(f"[INFO] {filepath} nem található, létrehozás...")
        try:
            with open(filepath, "w") as f:
                yaml.dump({}, f)
            print(f"[OK] Üres {filepath} létrehozva.")
        except Exception as e:
            print(f"[HIBA] Nem sikerült létrehozni a {filepath} fájlt: {e}")
    else:
        print(f"[INFO] {filepath} már létezik.")