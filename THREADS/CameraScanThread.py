import cv2
from PyQt5.QtCore import QThread, pyqtSignal

class CameraScanThread(QThread):
    camerasFound = pyqtSignal(list)

    def __init__(self, max_index=5):
        super().__init__()
        self.max_index = max_index

    def run(self):
        found = []
        for i in range(self.max_index):
            try:
                cap = cv2.VideoCapture(i)
                if cap is not None and cap.isOpened():
                    found.append(i)
                    cap.release()
            except Exception as e:
                print(f"Kamera {i} hibás: {e}")
        self.camerasFound.emit(found)
