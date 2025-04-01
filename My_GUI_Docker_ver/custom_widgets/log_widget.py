from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit

class LogWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        self.setLayout(layout)

    def append_log(self, message):
        self.log_view.appendPlainText(message)
