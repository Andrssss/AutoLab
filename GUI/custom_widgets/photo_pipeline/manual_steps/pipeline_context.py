from File_managers import config_manager

class PipelineContext:
    def __init__(self):
        self.image = None            # 📷 Eredeti kép
        self.mask = None             # 🧪 Petri dish maszk
        self.settings = {}           # ⚙️ Általános beállítások
        self.filtered_image = None   # 🧼 Szűrt vagy feldolgozott kép
        self.analysis = {}           # 🔬 Detektált kolóniák vagy egyéb eredmények
        self.roi_points = []         # 📍 Kézzel kiválasztott ROI pontok (x, y)

        # Töltsük be a pixel_per_cm-t a settings.yaml fájlból
        self.pixel_per_cm = self._load_pixel_per_cm()

    def _load_pixel_per_cm(self):
        """
        Betölti az adott kamera pixel_per_cm értékét, ha van ilyen a settings.yaml-ban.
        """
        try:
            # Először lekérjük az általános settings.yaml tartalmat
            full_settings = config_manager.load_settings()
            self.settings = full_settings  # az egész settings eltárolása

            # Lekérjük az aktuális kamera indexet (default: 0)
            cam_index = full_settings.get("camera_index", 0)

            # Kamera-specifikus beállítások betöltése
            cam_settings = full_settings.get("camera_settings", {}).get(str(cam_index), {})

            return cam_settings.get("pixel_per_cm", None)

        except Exception as e:
            print(f"[HIBA] Nem sikerült betölteni a pixel_per_cm értéket: {e}")
            return None
