from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt
import cv2
import numpy as np


class StepROIWidget(QWidget):
    def __init__(self, context, image_path=None, parent=None):
        super().__init__(parent)
        self.context = context
        self.points = context.roi_points or []

        # UI Elements
        self.image_label = QLabel("Image not loaded")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(800, 600)  # 🖼️ Larger image area
        self.image_label.mousePressEvent = self.handle_mouse_click

        self.instructions = QLabel("🖱️ Left-click to add point, right-click to remove")
        self.instructions.setAlignment(Qt.AlignCenter)

        self.info_label = QLabel("ROI Info")
        self.info_label.setAlignment(Qt.AlignTop)

        self.prev_btn = QPushButton("◀ Previous")
        self.next_btn = QPushButton("Next ▶")
        self.reset_btn = QPushButton("🧹 Reset ROI")
        self.reset_btn.clicked.connect(self.reset_points)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.reset_btn)
        nav_layout.addWidget(self.next_btn)

        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        layout.addWidget(self.instructions)
        layout.addWidget(self.info_label)
        layout.addLayout(nav_layout)
        self.setLayout(layout)

        self.display_image = None
        self.scaled_display_size = None

    def load_from_context(self):
        self.points = self.context.roi_points or []
        info_lines = []

        settings = self.context.settings
        if settings:
            info_lines.append("⚙️ Settings:")
            for key, val in settings.items():
                info_lines.append(f" - {key}: {val}")

        if self.context.mask is not None:
            info_lines.append("🧪 Petri dish mask: Available")
        else:
            info_lines.append("❌ No Petri dish mask")

        if self.context.image is not None:
            info_lines.append("🖼️ Image: Loaded and displayed")
            self.display_roi_image()
        else:
            info_lines.append("❌ No image")

        info_lines.append(f"📍 ROI Points: {len(self.points)} selected")
        self.info_label.setText("\n".join(info_lines))

    def display_roi_image(self):
        image = self.context.image
        mask = self.context.mask

        if image is None:
            self.image_label.setText("No image to show.")
            return

        if mask is not None:
            masked = cv2.bitwise_and(image, image, mask=mask)
            preview = masked.copy()
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(preview, contours, -1, (0, 255, 255), 2)
        else:
            preview = image.copy()

        self.display_image = preview
        self.update_image_label()

    def update_image_label(self):
        if self.display_image is None:
            return

        image = self.display_image.copy()

        for pt in self.points:
            cv2.drawMarker(image, pt, (0, 0, 255), markerType=cv2.MARKER_TILTED_CROSS,
                           markerSize=8, thickness=1)

        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w

        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image).scaled(
            self.image_label.width(),
            self.image_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.scaled_display_size = pixmap.size()
        self.image_label.setPixmap(pixmap)

    def handle_mouse_click(self, event):
        if self.display_image is None or self.context.mask is None:
            return

        pixmap = self.image_label.pixmap()
        if not pixmap or self.scaled_display_size is None:
            return

        disp_w = self.scaled_display_size.width()
        disp_h = self.scaled_display_size.height()
        img_h, img_w = self.display_image.shape[:2]

        scale_x = img_w / disp_w
        scale_y = img_h / disp_h

        label_w = self.image_label.width()
        label_h = self.image_label.height()
        offset_x = (label_w - disp_w) // 2
        offset_y = (label_h - disp_h) // 2

        x = int((event.pos().x() - offset_x) * scale_x)
        y = int((event.pos().y() - offset_y) * scale_y)

        if x < 0 or y < 0 or x >= img_w or y >= img_h:
            return

        if event.button() == Qt.LeftButton:
            if self.context.mask[y, x] == 0:
                print("[INFO] Click ignored — outside Petri dish.")
                return

            for px, py in self.points:
                if abs(px - x) < 5 and abs(py - y) < 5:
                    print("[INFO] Point already exists nearby.")
                    return

            self.points.append((x, y))
            print(f"[DEBUG] Added point: ({x}, {y})")

        elif event.button() == Qt.RightButton:
            if not self.points:
                return

            distances = [np.hypot(px - x, py - y) for (px, py) in self.points]
            closest_idx = int(np.argmin(distances))
            if distances[closest_idx] < 20:
                removed = self.points.pop(closest_idx)
                print(f"[DEBUG] Removed point: {removed}")

        self.update_image_label()
        self.update_info()

    def update_info(self):
        self.info_label.setText(f"📍 ROI Points: {len(self.points)} selected")

    def reset_points(self):
        self.points.clear()
        self.update_image_label()
        self.update_info()
        print("[INFO] All ROI points cleared.")

    def save_to_context(self):
        self.context.roi_points = self.points
        print(f"[DEBUG] Saved {len(self.points)} ROI points to context.")
