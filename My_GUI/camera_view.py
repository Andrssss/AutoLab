# camera_view.py (javított)
import cv2
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt
from custom_window import CustomWindow

class CameraViewWidget(QWidget):
    def __init__(self, cam_index=0):
        super().__init__()
        self.resize(640, 480)
        self.cam_index = cam_index
        self.cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

    def update_frame(self):
        ret, frame = self.cap.read()
        if ret:
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            qimg = QImage(rgb_image.data, w, h, ch * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg).scaled(self.label.size(), Qt.KeepAspectRatio)
            self.label.setPixmap(pixmap)

    def closeEvent(self, event):
        self.timer.stop()
        if self.cap:
            self.cap.release()
        event.accept()

class CameraViewWindow(CustomWindow):
    def __init__(self, cam_index=0, parent=None):
        self.view_widget = CameraViewWidget(cam_index)
        super().__init__("Camera View", self.view_widget, parent)
