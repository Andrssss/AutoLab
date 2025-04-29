from PyQt5.QtWidgets import QDockWidget

class CameraDock(QDockWidget):
    def __init__(self, camera_widget, log_widget, parent=None):
        super().__init__("Camera", parent)
        self.camera_widget = camera_widget
        self.log_widget = log_widget
        self.setWidget(self.camera_widget)

    def closeEvent(self, event):
        self.camera_widget.on_pause()
        self.log_widget.append_log("Camera panel bezárva (closeEvent), kamera leállítva.")
        super().closeEvent(event)