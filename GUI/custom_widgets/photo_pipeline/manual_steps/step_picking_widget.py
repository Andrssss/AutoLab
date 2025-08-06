from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal

class StepPickingWidget(QWidget):
    finished = pyqtSignal()  # You can connect this to trigger saving, closing, etc.

    def __init__(self, context, image_path=None):
        super().__init__()
        self.context = context
        self.image_path = image_path

        layout = QVBoxLayout()

        label = QLabel("Summary Step")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        self.prev_btn = QPushButton("◀ Previous")
        self.finish_btn = QPushButton("✓ Finish")  # Later will trigger save/export

        layout.addWidget(self.prev_btn)
        layout.addWidget(self.finish_btn)

        self.setLayout(layout)

        # Example: connect to a placeholder method
        self.finish_btn.clicked.connect(self.on_finish)

    def on_finish(self):
        print("[DEBUG] Finish clicked — results would be saved here.")
        self.finished.emit()  # Optional: notify parent widget
