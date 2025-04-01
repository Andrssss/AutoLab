# camera_widget.py
import cv2, os
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap


class CameraWidget(QWidget):
    playPressed = pyqtSignal()
    stopPressed = pyqtSignal()
    snapshotPressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.current_frame = None
        self.camera_index = None
        self.available_cams = []
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Legördülő lista az elérhető kamerákhoz
        self.combo_cameras = QComboBox()
        self.combo_cameras.currentIndexChanged.connect(self.on_camera_change)
        layout.addWidget(self.combo_cameras)

        # Kamera kép megjelenítése
        self.label_camera = QLabel("Camera Feed")
        self.label_camera.setFixedSize(300, 200)
        self.label_camera.setStyleSheet("background-color: black;")
        self.label_camera.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label_camera)

        # Gombok: Play, Stop, Snapshot
        btn_layout = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.btn_stop = QPushButton("Stop")
        self.btn_snapshot = QPushButton("Snapshot")
        btn_layout.addWidget(self.btn_play)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_snapshot)
        layout.addLayout(btn_layout)

        self.btn_play.clicked.connect(self.on_play)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_snapshot.clicked.connect(self.on_snapshot)

        self.setLayout(layout)
        self.populate_camera_list()

    def detect_cameras(self):
        available = []
        # Próbáljunk 5 lehetséges kameraindexet
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    available.append(i)
                cap.release()
        return available

    def populate_camera_list(self):
        self.available_cams = self.detect_cameras()
        self.combo_cameras.clear()
        for index in self.available_cams:
            self.combo_cameras.addItem(f"Camera {index}", index)
        if self.available_cams:
            self.combo_cameras.setCurrentIndex(0)
            self.on_play()  # Azonnal indítja is

    def set_camera(self, index):
        self.camera_index = index
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(index)

    def on_camera_change(self, i):
        index = self.combo_cameras.itemData(i)
        if index is not None and index != self.camera_index:
            was_running = self.timer.isActive()
            self.on_stop()
            print(f"Camera {self.camera_index} leállítva.")
            self.stopPressed.emit()

            self.set_camera(index)

            # Mindig indítunk, ha kamera elérhető
            self.on_play()
            print(f"Camera {self.camera_index} elindítva.")

    def on_play(self):
        self.playPressed.emit()
        current_index = self.combo_cameras.currentData()
        if current_index is not None:
            self.set_camera(current_index)
        if not self.timer.isActive():
            self.timer.start(30)

    def on_stop(self):
        self.stopPressed.emit()
        if self.timer.isActive():
            self.timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        self.label_camera.clear()
        self.label_camera.setText("Camera Feed")

    def on_snapshot(self):
        self.snapshotPressed.emit()
        self.capture_image()

    def update_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.current_frame = frame
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qimg = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg).scaled(self.label_camera.size(), Qt.KeepAspectRatio)
                self.label_camera.setPixmap(pixmap)

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

    def on_camera_change(self, i):
        index = self.combo_cameras.itemData(i)
        if index is not None and index != self.camera_index:
            was_running = self.timer.isActive()
            if was_running:
                self.on_stop()
                print(f"Camera {self.camera_index} leállítva.")
                self.stopPressed.emit()  # Log jele
            self.set_camera(index)
            if was_running:
                self.timer.start(30)
                print(f"Camera {self.camera_index} elindítva.")
                self.playPressed.emit()  # Log jele
