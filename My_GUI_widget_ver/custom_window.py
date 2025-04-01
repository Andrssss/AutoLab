from PyQt5.QtWidgets import QFrame, QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt

class CustomWindow(QFrame):
    def __init__(self, title, widget, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Box)
        self.setLineWidth(2)
        self.setFixedSize(widget.width() + 10, widget.height() + 35)
        self.setStyleSheet("background-color: #ddd;")  # Nem lesz átlátszó

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Címsor
        self.title_bar = QWidget(self)
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background-color: #444; color: white;")

        self.title_layout = QHBoxLayout(self.title_bar)
        self.title_layout.setContentsMargins(5, 0, 5, 0)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: white;")

        self.btn_min = QPushButton("-")
        self.btn_close = QPushButton("×")

        for btn in [self.btn_min, self.btn_close]:
            btn.setFixedSize(20, 20)
            btn.setStyleSheet("color:white; background:#666; border:none;")

        self.title_layout.addWidget(self.title_label)
        self.title_layout.addStretch()
        self.title_layout.addWidget(self.btn_min)
        self.title_layout.addWidget(self.btn_close)

        self.main_layout.addWidget(self.title_bar)
        self.main_layout.addWidget(widget)

        self.widget = widget
        self.dragging = False

        # Gombok működése
        self.btn_close.clicked.connect(self.close)
        self.btn_min.clicked.connect(self.toggle_minimize)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.y() < 30:
            self.dragging = True
            self.drag_start_pos = event.globalPos() - self.pos()

    def mouseMoveEvent(self, event):
        if self.dragging:
            new_pos = event.globalPos() - self.drag_start_pos
            parent_rect = self.parentWidget().rect()
            new_x = max(0, min(parent_rect.width() - self.width(), new_pos.x()))
            new_y = max(0, min(parent_rect.height() - self.height(), new_pos.y()))
            self.move(new_x, new_y)

    def mouseReleaseEvent(self, event):
        self.dragging = False

    def toggle_minimize(self):
        if self.widget.isVisible():
            self.widget.hide()
            self.resize(self.width(), 30)
        else:
            self.widget.show()
            self.resize(self.width(), self.widget.height() + 35)
