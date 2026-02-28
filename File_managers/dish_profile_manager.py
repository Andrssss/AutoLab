# dish_profile_manager.py
import yaml
import os
import logging

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

        # Save lists instead of tuples because YAML handles lists better.
        roi_list = [[int(x), int(y)] for (x, y) in roi_points]

        data[dish_key] = {
            "roi_points": roi_list
        }

        save_dish_profiles(data)
        logging.getLogger(__name__).info(f"[OK] ROI points saved to dish_profiles.yaml under dish_id={dish_id}.")
    except Exception as e:
        logging.getLogger(__name__).error(f"[ERROR] Failed to save ROI points: {e}")
        raise

