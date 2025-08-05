# step_roi_widget.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt

class StepROIWidget(QWidget):
    def __init__(self, image_path=None):
        super().__init__()

        layout = QVBoxLayout()

        label = QLabel("ROI Step (Region of Interest)")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        self.prev_btn = QPushButton("◀ Previous")
        self.next_btn = QPushButton("Next ▶")

        layout.addWidget(self.prev_btn)
        layout.addWidget(self.next_btn)

        self.setLayout(layout)
