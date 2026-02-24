# dish_profile_manager.py
import yaml
import os

DISH_FILE = os.path.join(os.path.dirname(__file__), '..', 'config_profiles', 'dish_profiles.yaml')


def load_dish_profiles():
    if not os.path.exists(DISH_FILE):
        return {}
    with open(DISH_FILE, "r") as file:
        return yaml.safe_load(file) or {}


def save_dish_profiles(data):
    with open(DISH_FILE, "w") as file:
        yaml.dump(data, file)


def save_dish_roi_points(dish_id, roi_points):
    try:
        data = load_dish_profiles()
        dish_key = str(dish_id)

        # Tuple helyett listát mentsünk, mert a YAML nem szereti a tuple-t
        roi_list = [[int(x), int(y)] for (x, y) in roi_points]

        data[dish_key] = {
            "roi_points": roi_list
        }

        save_dish_profiles(data)
        print(f"[OK] ROI pontok elmentve dish_profiles.yaml-ba dish_id={dish_id} alatt.")
    except Exception as e:
        print(f"[HIBA] Nem sikerült menteni a ROI pontokat: {e}")
        raise
