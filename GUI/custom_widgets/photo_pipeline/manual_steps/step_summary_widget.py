from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox, QDialog
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt
import cv2

from File_managers import config_manager


class StepSummaryWidget(QWidget):
    def __init__(self, context, image_path=None):
        super().__init__()
        self.context = context
        self.image_path = image_path

        layout = QVBoxLayout()

        title = QLabel("📋 Összegzés")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.image_label = QLabel("Nincs kép")
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)

        self.roi_text = QTextEdit()
        self.roi_text.setReadOnly(True)
        layout.addWidget(self.roi_text)

        self.measure_btn = QPushButton("📏 Mérj 1 cm-t")
        self.prev_btn = QPushButton("◀ Előző")
        self.next_btn = QPushButton("Következő ▶")

        layout.addWidget(self.measure_btn)
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.next_btn)

        self.setLayout(layout)

        self.measure_btn.clicked.connect(self.open_measure_dialog)
        self.next_btn.clicked.connect(self.try_advance)

        self.display_image_with_rois()
        self.display_roi_points()

        # 🆕 Pixel per cm automatikus betöltése config-ból
        self.load_pixel_per_cm_from_config()

    def load_pixel_per_cm_from_config(self):
        try:
            cam_index = self.context.settings.get("camera_index", 0)
            all_settings = config_manager.load_camera_settings()

            cam_settings = all_settings.get("camera_settings", {}).get(str(cam_index), {})
            pixel_per_cm = cam_settings.get("pixel_per_cm", None)

            if pixel_per_cm is not None:
                self.context.pixel_per_cm = pixel_per_cm
                print(f"[INFO] pixel_per_cm érték betöltve a YAML-ból: {pixel_per_cm:.2f} px/cm")
        except Exception as e:
            print(f"[HIBA] pixel_per_cm betöltése sikertelen: {e}")

    def display_image_with_rois(self):
        image = self.context.image
        if image is None:
            self.image_label.setText("❌ Nincs kép betöltve.")
            return

        roi_points = self.context.roi_points or []
        display_img = image.copy()

        for pt in roi_points:
            cv2.drawMarker(display_img, pt, (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=10, thickness=2)

        rgb_image = cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img).scaled(600, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.image_label.setPixmap(pixmap)

    def display_roi_points(self):
        roi_points = self.context.roi_points or []
        if not roi_points:
            self.roi_text.setText("❌ Nincsenek ROI pontok.")
            return

        text_lines = ["📍 ROI pontok (x, y):"]
        for idx, (x, y) in enumerate(roi_points, start=1):
            text_lines.append(f"  {idx}. ({x}, {y})")

        self.roi_text.setText("\n".join(text_lines))

    def try_advance(self):
        self.load_pixel_per_cm_from_config()
        px_per_cm = getattr(self.context, "pixel_per_cm", None)

        if px_per_cm is None:
            QMessageBox.warning(
                self,
                "Hiányzó érték",
                "⚠️ Ehhez a kamerához nincs beállítva, hogy 1 cm hány pixel!\n"
                "Kérlek, mérd meg előbb a kalibrációs ablakban."
            )
            return False  #  Fontos: ne lépj tovább!

        return True  #  OK, mehet tovább!

    def open_measure_dialog(self):
        from GUI.custom_widgets.mainwindow_components.PixelPerCmMeasureDialog import PixelPerCmMeasureDialog

        if self.context.image is None or self.context.image.size == 0:
            QMessageBox.warning(self, "Hiba", "❌ Nem található aktuális kép.")
            return

        frame_copy = self.context.image.copy()
        self.dialog = PixelPerCmMeasureDialog(frame_copy, self)

        # Állítsd be az eseménykezelőt
        self.dialog.accepted.connect(self.handle_dialog_accepted)
        self.dialog.rejected.connect(lambda: print("[INFO] Kalibráció megszakítva."))

        self.dialog.setModal(True)
        self.dialog.setWindowFlags(self.dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        self.dialog.resize(800, 600)
        self.dialog.show()

    def handle_dialog_accepted(self):
        pixel_per_cm = self.dialog.get_pixel_per_cm()
        if pixel_per_cm:
            self.context.pixel_per_cm = pixel_per_cm

            # Mentés settings.yaml-ba
            cam_index = self.context.settings.get("camera_index", 0)
            try:
                all_settings = config_manager.load_camera_settings()

                # Biztosítsd, hogy legyen camera_settings rész
                if "camera_settings" not in all_settings:
                    all_settings["camera_settings"] = {}

                if str(cam_index) not in all_settings["camera_settings"]:
                    all_settings["camera_settings"][str(cam_index)] = {}

                all_settings["camera_settings"][str(cam_index)]["pixel_per_cm"] = pixel_per_cm

                config_manager.save_camera_settings(cam_index, all_settings["camera_settings"][str(cam_index)])

                QMessageBox.information(self, "✔ Mentve", f"1 cm = {pixel_per_cm:.2f} px elmentve")
            except Exception as e:
                QMessageBox.critical(self, "❌ Hiba", f"[HIBA] Nem sikerült menteni a kalibrációt: {e}")



