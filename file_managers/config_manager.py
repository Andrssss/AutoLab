import yaml
import os

SETTINGS_FILE = "settings.yaml"

def load_settings():
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
    if "camera_settings" not in settings:
        settings["camera_settings"] = {}

    settings["camera_settings"][str(index)] = data  # kulcs legyen str!
    save_settings(settings)

def load_camera_settings(index) -> dict:
    settings = load_settings()
    return settings.get("camera_settings", {}).get(str(index), {})

def ensure_settings_yaml_exists(filepath="settings.yaml"):
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
