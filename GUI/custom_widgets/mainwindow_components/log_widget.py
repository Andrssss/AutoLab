from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QHBoxLayout

class LogWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout()

        # Gomb sor (pl. törléshez)
        button_layout = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear_log)
        button_layout.addStretch()
        button_layout.addWidget(btn_clear)

        # Log nézet
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        layout.addLayout(button_layout)  # Gomb sor
        layout.addWidget(self.log_view)  # Szövegdoboz
        self.setLayout(layout)
        self.setMinimumWidth(600)

    def append_log(self, message):
        self.log_view.appendPlainText(message)

    def clear_log(self):
        self.log_view.clear()
