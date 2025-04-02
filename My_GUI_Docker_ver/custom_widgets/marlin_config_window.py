from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QFileDialog
)
from PyQt5.QtCore import Qt


class MarlinConfigWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Marlin Config")
        self.setFixedSize(300, 150)

        layout = QVBoxLayout()

        # Beviteli mező
        self.title_input = QLineEdit("Settings")
        layout.addWidget(self.title_input)

        # Upload gomb
        self.upload_button = QPushButton("Upload to Marlin")
        layout.addWidget(self.upload_button)

        # Save/Load gombok
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.load_button = QPushButton("Load")
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.load_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Jelek bekötése
        self.load_button.clicked.connect(self.open_file_dialog)

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Válassz egy Marlin config fájlt",
            "",  # alapértelmezett mappa pl. "/home" vagy "C:/"
            "Config Files (*.h *.ini *.json *.txt);;All Files (*)"
        )
        if file_path:
            print(f"Kiválasztott fájl: {file_path}")
            # Itt lehet majd betölteni vagy megjeleníteni a tartalmat
