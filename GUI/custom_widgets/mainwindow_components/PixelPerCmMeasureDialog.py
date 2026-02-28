import cv2
from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt


class PixelPerCmMeasureDialog(QDialog):
    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("1 cm Measurement")
        self.setMinimumSize(800, 600)

        self.image = image
        self.start_point = None
        self.end_point = None
        self.pixel_per_cm = None

        # Image and text
        self.label_image = QLabel()
        self.label_image.setAlignment(Qt.AlignCenter)
        self.label_result = QLabel("Draw a 1 cm line with the mouse")
        self.btn_save = QPushButton("Save")

        layout = QVBoxLayout()
        layout.addWidget(self.label_image)
        layout.addWidget(self.label_result)
        layout.addWidget(self.btn_save, alignment=Qt.AlignRight)
        self.setLayout(layout)

        self.update_display()
        self.label_image.mousePressEvent = self.mouse_pressed
        self.label_image.mouseMoveEvent = self.mouse_moved
        self.label_image.mouseReleaseEvent = self.mouse_released

        self.btn_save.clicked.connect(self.save_and_close)

    def update_display(self):
        img = self.image.copy()
        if self.start_point and self.end_point:
            cv2.line(img, self.start_point, self.end_point, (0, 255, 0), 2)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        self.label_image.setPixmap(pixmap)

    def mouse_pressed(self, event):
        self.start_point = self.get_image_coords(event.pos())

    def mouse_moved(self, event):
        if self.start_point:
            self.end_point = self.get_image_coords(event.pos())
            self.update_display()

    def mouse_released(self, event):
        self.end_point = self.get_image_coords(event.pos())
        self.update_display()
        self.calculate_distance()

    def calculate_distance(self):
        if self.start_point and self.end_point:
            x1, y1 = self.start_point
            x2, y2 = self.end_point
            dist = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
            self.pixel_per_cm = dist
            self.label_result.setText(f"1 cm = {dist:.2f} pixel")

    def save_and_close(self):
        if self.pixel_per_cm is not None:
            self.accept()
        else:
            self.label_result.setText("Draw a measurement line first!")

    def get_image_coords(self, pos):
        label_w = self.label_image.width()
        label_h = self.label_image.height()
        img_h, img_w, _ = self.image.shape
        scale_x = img_w / label_w
        scale_y = img_h / label_h
        return int(pos.x() * scale_x), int(pos.y() * scale_y)

    def get_pixel_per_cm(self):
        try:
            return float(self.pixel_per_cm)
        except Exception as e:
            parent = self.parent()
            log_widget = getattr(parent, "log_widget", None) if parent is not None else None
            if log_widget:
                log_widget.append_log(f"[ERROR] Invalid pixel_per_cm value: {e}")
            return None
