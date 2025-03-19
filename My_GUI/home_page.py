import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QSettings, pyqtSignal


class CameraWidget(QWidget):
    # Signal, mely a kiválasztott kamera indexét továbbítja
    cameraSelected = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kamera kiválasztása")
        self.resize(400, 300)

        # Egyszerű gomb, ami egy példa értékkel választ ki egy kamerát (pl. index 0)
        self.btn_select = QPushButton("Kamera 0 kiválasztása")
        self.btn_select.clicked.connect(self.select_camera)

        layout = QVBoxLayout()
        layout.addWidget(self.btn_select)
        self.setLayout(layout)

    def select_camera(self):
        # Példaként a 0-ás indexű kamera kiválasztása
        self.cameraSelected.emit(0)
        self.close()


class HomePage(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Home Page")
        self.resize(800, 600)
        self.selected_camera = None

        # QSettings példány létrehozása; Windows alatt a Registry-ben, Linux alatt általában INI fájlban tárolja
        self.settings = QSettings("MyApp", "CameraNumber")

        self.selected_camera_label = QLabel("Nincs kamera kiválasztva")
        self.selected_camera_label.setAlignment(Qt.AlignCenter)

        self.btn_select_camera = QPushButton("Kamera kiválasztása")
        self.btn_select_camera.clicked.connect(self.open_camera_widget)

        layout = QVBoxLayout()
        layout.addWidget(self.selected_camera_label)
        layout.addWidget(self.btn_select_camera)
        self.setLayout(layout)

        # Korábban elmentett kamera érték beolvasása (ha van)
        stored_camera = self.settings.value("selected_camera", None)
        if stored_camera is not None:
            try:
                self.selected_camera = int(stored_camera)
                self.selected_camera_label.setText(f"Kiválasztott kamera: {self.selected_camera}")
            except ValueError:
                self.selected_camera = None

    def open_camera_widget(self):
        self.cam_widget = CameraWidget()
        # A CameraWidget-ből érkező signal segítségével frissítjük a kiválasztott kamera értékét
        self.cam_widget.cameraSelected.connect(self.update_selected_camera)
        self.cam_widget.show()

    def update_selected_camera(self, cam_index):
        self.selected_camera = cam_index
        self.selected_camera_label.setText(f"Kiválasztott kamera: {cam_index}")
        # Elmentjük a kiválasztott kamera értékét a QSettings-be
        self.settings.setValue("selected_camera", cam_index)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    home = HomePage()
    home.show()
    sys.exit(app.exec_())
