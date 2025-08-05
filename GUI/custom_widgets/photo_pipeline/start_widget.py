# start_widget.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt

class StartWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        label = QLabel("Kérlek válassz módszert:")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        self.setFixedSize(700, 700)
        self.manual_btn = QPushButton("Manuális elemzés")
        self.auto_btn = QPushButton("Automatikus elemzés")

        layout.addWidget(self.manual_btn)
        layout.addWidget(self.auto_btn)

        self.setLayout(layout)
