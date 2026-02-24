import os
import yaml
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QFileDialog, QMessageBox, QGridLayout
)
from File_managers import marlin_config_manager

PROFILE_DIR = "config_profiles"
os.makedirs(PROFILE_DIR, exist_ok=True)


class MarlinConfigWindow(QWidget):
    def __init__(self, g_control, log_widget=None):
        super().__init__()
        self.setWindowTitle("Marlin Config")
        self.setMinimumSize(400, 500)

        self.g_control = g_control
        self.log_widget = log_widget

        # Automatikusan beállítjuk az apply_callback-et, ha van g_control
        self.apply_callback = (
            g_control.apply_marlin_settings if g_control else None
        )

        self.fields = {}
        self.main_layout = QVBoxLayout()
        self.grid = QGridLayout()
        self.main_layout.addLayout(self.grid)


        # Gombok
        btn_layout = QHBoxLayout()
        self.load_button = QPushButton("📄 Betöltés")
        self.save_button = QPushButton("💾 Mentés")
        self.upload_button = QPushButton("⬆️ Küldés Marlinnak")
        btn_layout.addWidget(self.load_button)
        btn_layout.addWidget(self.save_button)
        btn_layout.addWidget(self.upload_button)
        self.main_layout.addLayout(btn_layout)

        profile_layout = QHBoxLayout()
        self.btn_save_as = QPushButton("🔖 Mentés másként...")
        self.btn_load_from = QPushButton("📂 Betöltés profilból...")
        profile_layout.addWidget(self.btn_save_as)
        profile_layout.addWidget(self.btn_load_from)
        self.main_layout.addLayout(profile_layout)

        self.setLayout(self.main_layout)

        # Jelzések
        self.load_button.clicked.connect(self.load_settings)
        self.save_button.clicked.connect(self.save_settings)
        self.upload_button.clicked.connect(self.upload_to_marlin)
        self.btn_save_as.clicked.connect(self.save_as_profile)
        self.btn_load_from.clicked.connect(self.load_from_profile)

        # Mezők létrehozása
        self.load_settings()

    def flatten_dict(self, d, parent_key=''):
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self.flatten_dict(v, new_key).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def unflatten_dict(self, flat):
        result = {}
        for full_key, value in flat.items():
            keys = full_key.split(".")
            d = result
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            d[keys[-1]] = value
        return result

    def load_settings(self):
        # Beviteli mezők törlése
        for i in reversed(range(self.grid.count())):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        self.fields.clear()

        try:
            raw = marlin_config_manager.load_settings()
        except Exception as e:
            QMessageBox.critical(self, "Hiba", f"Beállítás betöltése sikertelen:\n{e}")
            raw = {}

        flat = self.flatten_dict(raw)
        for row, (key, value) in enumerate(flat.items()):
            label = QLabel(key)
            field = QLineEdit(str(value) if isinstance(value, (int, float)) else "")
            self.grid.addWidget(label, row, 0)
            self.grid.addWidget(field, row, 1)
            self.fields[key] = field


    def save_settings(self):
        try:
            flat = {}
            for key, field in self.fields.items():
                text = field.text().strip()
                if not text:
                    continue
                try:
                    flat[key] = float(text)
                except ValueError:
                    continue
            structured = self.unflatten_dict(flat)
            marlin_config_manager.save_settings(structured)
            QMessageBox.information(self, "OK", "Beállítás elmentve.")
        except Exception as e:
            QMessageBox.critical(self, "Hiba", f"Nem sikerült menteni:\n{e}")

    def upload_to_marlin(self):
        if self.apply_callback:
            try:
                settings = marlin_config_manager.load_settings()
                self.apply_callback(settings)
                if self.log_widget:
                    self.log_widget.append_log("[INFO] Beállítások feltöltve Marlin firmware-re.")
                QMessageBox.information(self, "OK", "Beállítások alkalmazva.")
            except Exception as e:
                if self.log_widget:
                    self.log_widget.append_log(f"[HIBA] Feltöltési hiba: {e}")
                QMessageBox.critical(self, "Hiba", f"Nem sikerült feltölteni:\n{e}")
        else:
            QMessageBox.warning(self, "Figyelem", "Nincs csatlakoztatott vezérlés.")

    def save_as_profile(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Mentés profilként",
            os.path.join(PROFILE_DIR, "settings_profile.yaml"),
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )
        if file_path:
            try:
                flat = {}
                for key, field in self.fields.items():
                    text = field.text().strip()
                    if not text:
                        continue
                    try:
                        flat[key] = float(text)
                    except ValueError:
                        continue
                structured = self.unflatten_dict(flat)
                with open(file_path, "w") as f:
                    yaml.dump(structured, f)
                QMessageBox.information(self, "OK", f"Profil elmentve:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Hiba", f"Nem sikerült menteni:\n{e}")

    def load_from_profile(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Profil betöltése",
            PROFILE_DIR,
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "r") as f:
                    raw = yaml.safe_load(f)
                flat = self.flatten_dict(raw)

                for key, field in self.fields.items():
                    if key in flat and isinstance(flat[key], (int, float)):
                        field.setText(str(flat[key]))
                    else:
                        field.setText("")
                QMessageBox.information(self, "OK", f"Profil betöltve:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Hiba", f"Nem sikerült betölteni:\n{e}")
