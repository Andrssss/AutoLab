import sys
import cv2
import os
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QComboBox, QHBoxLayout
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt, pyqtSignal


class CameraWidget(QWidget):
    # Signal to emit the selected camera index
    cameraSelected = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kamera Választó és Fotó Készítő")
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
            # Default: select first camera
            self.combo_cameras.setCurrentIndex(0)
            self.set_camera(self.available_cams[0])

        # Timer for live frame updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)  # kb. 30ms, ~33 FPS

    def initUI(self):
        layout = QVBoxLayout()
        # ComboBox for available cameras
        self.combo_cameras = QComboBox()
        self.combo_cameras.currentIndexChanged.connect(self.on_camera_change)
        layout.addWidget(self.combo_cameras)

        # Label for live camera image
        self.label_image = QLabel("Kamera kép")
        self.label_image.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label_image)

        # Horizontal layout for buttons
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
        # Próbáljuk meg az 0-4 indexeket
        for i in range(5):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
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
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

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
                pixmap = QPixmap.fromImage(qimg)
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
        # Emit the selected camera index via signal
        self.cameraSelected.emit(self.camera_index)
        print(f"Selected camera {self.camera_index}")
        self.close()

    def closeEvent(self, event):
        if self.cap is not None:
            self.cap.release()
        event.accept()


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    widget = CameraWidget()
    widget.show()
    sys.exit(app.exec_())
