import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox, QDialog, QSplitter, QGroupBox, QFrame, QSizePolicy
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer
import cv2

from File_managers import config_manager
from File_managers import dish_profile_manager


class StepSummaryWidget(QWidget):
    def __init__(self, context, image_path=None, log_widget=None):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.context = context
        self.image_path = image_path
        self.log_widget = log_widget

        # Main layout: vertical with split panel in middle and buttons at bottom
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Center: Split panel (image left, log right) ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Left: Image
        self.image_label = QLabel("No Image")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(480, 360)
        self.image_label.setFrameShape(QFrame.StyledPanel)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        splitter.addWidget(self.image_label)
        
        # Right: Log (ROI points text)
        roi_group = QGroupBox("ROI Points")
        roi_group_layout = QVBoxLayout()
        self.roi_text = QTextEdit()
        self.roi_text.setReadOnly(True)
        roi_group_layout.addWidget(self.roi_text)
        roi_group.setLayout(roi_group_layout)
        roi_group.setMinimumWidth(300)
        splitter.addWidget(roi_group)
        
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter, 1)

        # --- Bottom: Buttons in one row ---
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        self.measure_btn = QPushButton("Measure 1 cm")
        self.prev_btn = QPushButton("Previous")
        self.next_btn = QPushButton("Next")
        
        button_layout.addWidget(self.prev_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.measure_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.next_btn)
        
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

        self.measure_btn.clicked.connect(self.open_measure_dialog)
        self.next_btn.clicked.connect(self.try_advance)

        self.display_image_with_rois()
        self.display_roi_points()
        QTimer.singleShot(0, self._refresh_view)

        # Automatically load pixel per cm from config
        self.load_pixel_per_cm_from_config()

    def _refresh_view(self):
        self.display_image_with_rois()
        self.display_roi_points()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_view()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.display_image_with_rois()

    def load_pixel_per_cm_from_config(self):
        try:
            cam_index = self.context.settings.get("camera_index", 0)
            all_settings = config_manager.load_camera_settings()

            cam_settings = all_settings.get("camera_settings", {}).get(str(cam_index), {})
            pixel_per_cm = cam_settings.get("pixel_per_cm", None)

            if pixel_per_cm is not None:
                self.context.pixel_per_cm = pixel_per_cm
                self.log_widget.append_log(f"[INFO] pixel_per_cm loaded from YAML: {pixel_per_cm:.2f} px/cm")
        except Exception as e:
            self.log_widget.append_log(f"[ERROR] Failed to load pixel_per_cm: {e}")

    def display_image_with_rois(self):
        # Prefer the annotated display image from ROI widget if available
        display_img_attr = getattr(self.context, "display_image", None)
        display_base = display_img_attr if display_img_attr is not None else self.context.image
        if display_base is None:
            self.image_label.setText("No image loaded.")
            return

        roi_points = list(self.context.roi_points) if self.context.roi_points is not None else []
        display_img = display_base.copy()

        # --- draw Petri dish outline (yellow) only if not from ROI widget ---
        if getattr(self.context, "display_image", None) is None:
            self._apply_dish_outline(display_img, color=(0, 255, 255), thickness=2)

        # draw ROI points (if not already drawn by ROI widget)
        if getattr(self.context, "display_image", None) is None:
            for pt in roi_points:
                cv2.drawMarker(display_img, pt, (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=10, thickness=2)

        rgb_image = cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        # Scale to fit the larger image area in split panel
        content_rect = self.image_label.contentsRect()
        target_w = max(1, content_rect.width())
        target_h = max(1, content_rect.height())
        pixmap = QPixmap.fromImage(qt_img).scaled(target_w, target_h, 
                                                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pixmap)

    def display_roi_points(self):
        roi_points = list(self.context.roi_points) if self.context.roi_points is not None else []
        if not roi_points:
            self.roi_text.setText("No ROI points.")
            return

        text_lines = ["ROI points (x, y):"]
        for idx, (x, y) in enumerate(roi_points, start=1):
            text_lines.append(f"  {idx}. ({x}, {y})")

        self.roi_text.setText("\n".join(text_lines))


    def try_advance(self):
        self.load_pixel_per_cm_from_config()
        px_per_cm = getattr(self.context, "pixel_per_cm", None)

        if px_per_cm is None:
            QMessageBox.warning(
                self,
                "Missing value",
                "This camera has no configured pixel-per-cm value for 1 cm.\n"
                "Please measure it first in the calibration window."
            )
            return False

        try:
            # Save ROI points under dish_id = 1
            roi_points = list(self.context.roi_points) if self.context.roi_points is not None else []
            dish_id = 1
            dish_profile_manager.save_dish_roi_points(dish_id, roi_points)
            self.log_widget.append_log(f"[INFO] ROI points saved for dish_id={dish_id}.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"[ERROR] Failed to save ROI points:\n{e}")
            return False

        return True

    def open_measure_dialog(self):
        from GUI.custom_widgets.mainwindow_components.PixelPerCmMeasureDialog import PixelPerCmMeasureDialog

        if self.context.image is None or self.context.image.size == 0:
            QMessageBox.warning(self, "Error", "No current image found.")
            return

        frame_copy = self.context.image.copy()
        self.dialog = PixelPerCmMeasureDialog(frame_copy, self)

        # Set event handlers
        self.dialog.accepted.connect(self.handle_dialog_accepted)
        self.dialog.rejected.connect(lambda: self.log_widget.append_log("[INFO] Calibration canceled."))

        self.dialog.setModal(True)
        self.dialog.setWindowFlags(self.dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        self.dialog.resize(800, 600)
        self.dialog.show()

    def handle_dialog_accepted(self):
        pixel_per_cm = self.dialog.get_pixel_per_cm()
        if pixel_per_cm:
            self.context.pixel_per_cm = pixel_per_cm

            # Save into settings.yaml
            cam_index = self.context.settings.get("camera_index", 0)
            try:
                all_settings = config_manager.load_camera_settings()

                # Ensure camera_settings section exists
                if "camera_settings" not in all_settings:
                    all_settings["camera_settings"] = {}

                if str(cam_index) not in all_settings["camera_settings"]:
                    all_settings["camera_settings"][str(cam_index)] = {}

                all_settings["camera_settings"][str(cam_index)]["pixel_per_cm"] = pixel_per_cm

                config_manager.save_camera_settings(cam_index, all_settings["camera_settings"][str(cam_index)])

                QMessageBox.information(self, "Saved", f"1 cm = {pixel_per_cm:.2f} px saved")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"[ERROR] Failed to save calibration: {e}")


    def _apply_dish_outline(self, img, color=(0, 255, 255), thickness=2):
        """
        Draw the Petri dish outline (from context.mask) on img in-place.
        color = BGR (default: yellow), thickness in pixels.
        """
        mask = getattr(self.context, "mask", None)
        if mask is None:
            return img
        try:
            # ensure uint8 binary
            m = mask
            if m.dtype != np.uint8:
                m = m.astype(np.uint8)
            if m.ndim == 3:
                m = cv2.cvtColor(m, cv2.COLOR_BGR2GRAY)
            # threshold in case it isn't strictly 0/255
            _, m = cv2.threshold(m, 1, 255, cv2.THRESH_BINARY)
            cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if cnts:
                cv2.drawContours(img, cnts, -1, color, thickness)
        except Exception as e:
            if self.log_widget:
                self.log_widget.append_log(f"[WARNING] Dish outline draw failed: {e}")
        return img



