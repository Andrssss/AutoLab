# start_widget.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout
from PyQt5.QtCore import Qt

class StartWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        label = QLabel("Please choose a method:")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addStretch(2)
        layout.addWidget(label)
        layout.addSpacing(10)

        self.setMinimumSize(700, 520)
        self.manual_btn = QPushButton("Manual Analysis")
        self.auto_btn = QPushButton("Automatic Analysis")

        self.manual_btn.setMinimumHeight(46)
        self.auto_btn.setMinimumHeight(46)
        self.manual_btn.setMinimumWidth(280)
        self.auto_btn.setMinimumWidth(280)

        button_row_1 = QHBoxLayout()
        button_row_1.addStretch()
        button_row_1.addWidget(self.manual_btn)
        button_row_1.addStretch()

        button_row_2 = QHBoxLayout()
        button_row_2.addStretch()
        button_row_2.addWidget(self.auto_btn)
        button_row_2.addStretch()

        layout.addLayout(button_row_1)
        layout.addLayout(button_row_2)
        layout.addStretch(3)

        self.setLayout(layout)
