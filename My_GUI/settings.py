# settings.py (javított verzió)
import cv2, os
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QComboBox, QHBoxLayout
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from custom_window import CustomWindow

class SettingsWidget(QWidget):
    cameraSelected = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.resize(640, 480)
        self.camera_index = None
        self.cap = None
        self.current_frame = None

        self.initUI()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

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
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap and cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    available.append(i)
                cap.release()
        return available

    def start_camera(self):
        self.available_cams = self.detect_cameras()
        if not self.available_cams:
            print("Nem található elérhető kamera.")
            return
        self.combo_cameras.clear()
        for index in self.available_cams:
            self.combo_cameras.addItem(f"Camera {index}", index)
        self.set_camera(self.available_cams[0])
        self.timer.start(30)

    def set_camera(self, index):
        if self.cap:
            self.cap.release()
        self.camera_index = index
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

    def on_camera_change(self, i):
        index = self.combo_cameras.itemData(i)
        self.set_camera(index)

    def update_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.current_frame = frame
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qimg = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg).scaled(self.label_image.size(), Qt.KeepAspectRatio)
                self.label_image.setPixmap(pixmap)

    def capture_image(self):
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
        self.close()  # Ez fogja triggerelni a closeEvent-et!

    def close_camera(self):
        self.timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None

    def closeEvent(self, event):
        self.close_camera()
        event.accept()

class SettingsWindow(CustomWindow):
    def __init__(self, parent=None):
        self.settings_widget = SettingsWidget()
        super().__init__("Settings", self.settings_widget, parent)

    def start_camera(self):
        self.settings_widget.start_camera()