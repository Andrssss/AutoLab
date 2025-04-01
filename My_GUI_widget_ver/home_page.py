from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout
from PyQt5.QtCore import Qt, QSettings
from custom_window import CustomWindow

class HomePage(QWidget):
    def __init__(self):
        super().__init__()
        self.resize(400, 300)
        self.settings = QSettings("MyApp", "CameraNumber")

        self.camera_label = QLabel("Nincs kamera kiválasztva")
        self.camera_label.setAlignment(Qt.AlignCenter)

        self.btn_settings = QPushButton("Settings")
        self.btn_camera_view = QPushButton("Camera képe")

        layout = QVBoxLayout()
        layout.addWidget(self.camera_label)
        layout.addWidget(self.btn_settings)
        layout.addWidget(self.btn_camera_view)
        self.setLayout(layout)

        stored_camera = self.settings.value("selected_camera", None)
        if stored_camera is not None:
            self.camera_label.setText(f"Kiválasztott kamera: {stored_camera}")

    def update_selected_camera(self, cam_index):
        self.camera_label.setText(f"Kiválasztott kamera: {cam_index}")
        self.settings.setValue("selected_camera", cam_index)

class HomePageWindow(CustomWindow): #  örökli a CustomWindow-t, amely maga egy konténer.
    def __init__(self, parent=None):
        self.home_widget = HomePage()
        super().__init__("Home Page", self.home_widget, parent)
