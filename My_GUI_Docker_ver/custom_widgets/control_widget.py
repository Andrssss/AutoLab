from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit

class ControlWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        self.btn_picking = QPushButton("Picking Protocol")
        layout.addWidget(self.btn_picking)

        h_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        h_layout.addWidget(self.btn_start)
        h_layout.addWidget(self.btn_stop)
        layout.addLayout(h_layout)

        self.btn_run = QPushButton("Run Sterilizing protocol")
        layout.addWidget(self.btn_run)

        self.line_target = QLineEdit()
        self.line_target.setPlaceholderText("Target Range pl. A1-A36")
        layout.addWidget(self.line_target)

        self.setLayout(layout)
