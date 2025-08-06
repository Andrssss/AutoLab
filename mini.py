import sys
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from PyQt5.QtCore import Qt, QPoint

class DistanceMeasurer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Centiméter pixel mérő")
        self.setGeometry(100, 100, 800, 600)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.label_image = QLabel(self)
        self.label_image.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.label_image)

        self.label_instructions = QLabel(
            "🔧 Használat:\n"
            " - Húzz egy vonalat az egérrel (1 cm szakaszra)\n"
            " - Azonnal megkapod az eredményt", self)
        self.layout.addWidget(self.label_instructions)

        self.label_result = QLabel("", self)
        self.layout.addWidget(self.label_result)

        self.original_img = cv2.imread("centi_foto.jpg")
        if self.original_img is None:
            self.label_result.setText("❌ Nem sikerült betölteni a képet.")
            return

        self.display_img = self.original_img.copy()
        self.update_display()

        self.label_image.mousePressEvent = self.mouse_pressed
        self.label_image.mouseMoveEvent = self.mouse_moved
        self.label_image.mouseReleaseEvent = self.mouse_released

        self.start_point = None
        self.end_point = None
        self.temp_line_img = None

    def update_display(self, custom_img=None):
        img = custom_img if custom_img is not None else self.display_img
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_img.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        self.label_image.setPixmap(pixmap)

    def mouse_pressed(self, event):
        x, y = self.to_image_coords(event.pos())
        self.start_point = (x, y)
        self.temp_line_img = self.display_img.copy()

    def mouse_moved(self, event):
        if self.start_point is None:
            return

        x, y = self.to_image_coords(event.pos())
        temp_img = self.temp_line_img.copy()
        cv2.line(temp_img, self.start_point, (x, y), (0, 255, 0), 2)
        self.update_display(temp_img)

    def mouse_released(self, event):
        if self.start_point is None:
            return

        x2, y2 = self.to_image_coords(event.pos())
        self.end_point = (x2, y2)

        # Rajz véglegesítés
        self.display_img = self.original_img.copy()
        cv2.line(self.display_img, self.start_point, self.end_point, (0, 255, 0), 2)
        self.update_display()

        # Távolság számítás
        (x1, y1) = self.start_point
        distance = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
        pixels_per_cm = distance / 1.0
        mm_per_pixel = 10.0 / distance

        self.label_result.setText(
            f"📏 Eredmény:\n"
            f"Pixel távolság: {distance:.2f} px\n"
            f"1 cm = {pixels_per_cm:.2f} px\n"
            f"1 pixel = {mm_per_pixel:.3f} mm"
        )

        # Reset a következő húzáshoz
        self.start_point = None
        self.end_point = None

    def to_image_coords(self, pos):
        label_w = self.label_image.width()
        label_h = self.label_image.height()
        img_h, img_w, _ = self.original_img.shape
        scale_x = img_w / label_w
        scale_y = img_h / label_h
        return int(pos.x() * scale_x), int(pos.y() * scale_y)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DistanceMeasurer()
    window.show()
    sys.exit(app.exec_())
