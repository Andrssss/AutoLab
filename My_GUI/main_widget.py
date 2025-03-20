# main_widget.py
import sys
from PyQt5.QtWidgets import QApplication, QWidget
from home_page import HomePageWindow
from settings import SettingsWindow
from camera_view import CameraViewWindow
from PyQt5.QtCore import QSettings

class MainWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Main Widget")
        self.resize(1200, 800)

        self.settings = QSettings("MyApp", "CameraNumber")
        self.selected_camera = int(self.settings.value("selected_camera", 0))

        # HomePage
        self.home_window = HomePageWindow(self)
        self.home_window.move(100, 100)

        # Settings és CameraView ablakok kezdetben nincsenek létrehozva
        self.settings_window = None
        self.camera_view_window = None

        # Signal-slot
        self.home_window.home_widget.btn_settings.clicked.connect(self.open_settings)
        self.home_window.home_widget.btn_camera_view.clicked.connect(self.open_camera_view)

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
            self.settings_window.settings_widget.cameraSelected.connect(self.camera_selected)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.start_camera()

    def open_camera_view(self):
        # Mindig újra létrehozza a CameraView-t, hogy friss kameraindex-szel induljon
        if self.camera_view_window is not None:
            self.camera_view_window.close()
        self.selected_camera = int(self.settings.value("selected_camera", 0))
        self.camera_view_window = CameraViewWindow(self.selected_camera, self)
        self.camera_view_window.show()
        self.camera_view_window.raise_()
        self.camera_view_window.move(250, 250)

    def camera_selected(self, cam_index):
        self.home_window.home_widget.update_selected_camera(cam_index)
        self.selected_camera = cam_index
        self.settings.setValue("selected_camera", cam_index)
        if self.camera_view_window is not None:
            self.camera_view_window.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWidget()
    main_window.show()
    sys.exit(app.exec_())
