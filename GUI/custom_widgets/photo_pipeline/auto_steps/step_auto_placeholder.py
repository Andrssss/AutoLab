from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt

class StepAutoPlaceholder(QWidget):
    def __init__(self,image_path=None):
        super().__init__()
        layout = QVBoxLayout()
        label = QLabel("Az automatikus pipeline később kerül megvalósításra.")
        label.setAlignment(Qt.AlignCenter)

        self.prev_btn = QPushButton("◀ Vissza")
        layout.addWidget(label)
        layout.addWidget(self.prev_btn)

        self.setLayout(layout)
