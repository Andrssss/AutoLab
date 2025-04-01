import cv2
import sys
import os
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QComboBox, QHBoxLayout
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from custom_window import CustomWindow

class CameraWidget(QWidget):
    cameraSelected = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.resize(640, 480)  # Ajánlott kamera-widget méret
        self.camera_index = None
        self.cap = None
        self.current_frame = None

        self.initUI()
        self.available_cams = self.detect_cameras()
        if not self.available_cams:
            print("Nem található elérhető kamera.")
            self.close()
        else:
            for index in self.available_cams:
                self.combo_cameras.addItem(f"Camera {index}", index)
            self.combo_cameras.setCurrentIndex(0)
            self.set_camera(self.available_cams[0])

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

    def initUI(self):
        layout = QVBoxLayout()
        self.combo_cameras = QComboBox()
        self.combo_cameras.currentIndexChanged.connect(self.on_camera_change)
        layout.addWidget(self.combo_cameras)

        self.label_image = QLabel("Kamera kép")
        self.label_image.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label_image)

        btn_layout = QHBoxLayout()
        self.btn_capture = QPushButton("Capture")
        self.btn_capture.clicked.connect(self.capture_image)
        btn_layout.addWidget(self.btn_capture)

        self.btn_select = QPushButton("Select")
        self.btn_select.clicked.connect(self.select_camera)
        btn_layout.addWidget(self.btn_select)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def detect_cameras(self):
        available = []
        for i in range(5):
            if sys.platform.startswith('win'):
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) # --> win
            else:
                cap = cv2.VideoCapture(i)                # --> linux
            if cap is not None and cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    available.append(i)
                cap.release()
        return available

    def set_camera(self, index):
        if self.cap is not None:
            self.cap.release()
        self.camera_index = index
        if sys.platform.startswith('win'):
            self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)  # --> win
        else:
            self.cap = cv2.VideoCapture(index)  # --> linux

    def on_camera_change(self, i):
        index = self.combo_cameras.itemData(i)
        self.set_camera(index)

    def update_frame(self):
        if self.cap is not None and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.current_frame = frame
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, channel = rgb_image.shape
                bytes_per_line = 3 * width
                qimg = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg).scaled(self.label_image.width(), self.label_image.height(), Qt.KeepAspectRatio)
                self.label_image.setPixmap(pixmap)

    def capture_image(self):  # Ha ez később meg lesz tartva, akkor linux-ra is specifikálni kell.
        if self.current_frame is not None:
            base_dir = r"C:\Users\Public\Pictures\MyCaptures"
            date_folder = datetime.now().strftime("%Y.%m.%d")
            save_folder = os.path.join(base_dir, date_folder)
            os.makedirs(save_folder, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = os.path.join(save_folder, f"capture_cam{self.camera_index}_{timestamp}.jpg")
            cv2.imwrite(filename, self.current_frame)
            print(f"Kép elmentve: {filename}")

    def select_camera(self):
        self.cameraSelected.emit(self.camera_index)
        print(f"Selected camera {self.camera_index}")
        self.close()

    def closeEvent(self, event):
        if self.cap is not None:
            self.cap.release()
        event.accept()

class CameraWidgetWindow(CustomWindow):
    def __init__(self, parent=None):
        super().__init__("Camera Widget", CameraWidget(), parent)

