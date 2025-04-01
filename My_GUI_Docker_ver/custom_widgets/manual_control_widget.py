from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import pyqtSignal


class ManualControlWidget(QWidget):
    moveCommand = pyqtSignal(str)
    actionCommand = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Iránygombok
        dir_layout = QVBoxLayout()
        up = QPushButton("↑")
        down = QPushButton("↓")
        left = QPushButton("←")
        right = QPushButton("→")

        up.clicked.connect(lambda: self.moveCommand.emit("up"))
        down.clicked.connect(lambda: self.moveCommand.emit("down"))
        left.clicked.connect(lambda: self.moveCommand.emit("left"))
        right.clicked.connect(lambda: self.moveCommand.emit("right"))

        arrow_grid = QVBoxLayout()
        arrow_row_top = QHBoxLayout()
        arrow_row_mid = QHBoxLayout()
        arrow_row_bot = QHBoxLayout()

        arrow_row_top.addStretch()
        arrow_row_top.addWidget(up)
        arrow_row_top.addStretch()

        arrow_row_mid.addWidget(left)
        arrow_row_mid.addStretch()
        arrow_row_mid.addWidget(right)

        arrow_row_bot.addStretch()
        arrow_row_bot.addWidget(down)
        arrow_row_bot.addStretch()

        arrow_grid.addLayout(arrow_row_top)
        arrow_grid.addLayout(arrow_row_mid)
        arrow_grid.addLayout(arrow_row_bot)

        layout.addLayout(arrow_grid)

        # IN/OUT gombok
        in_out_layout = QVBoxLayout()
        btn_in = QPushButton("IN")
        btn_out = QPushButton("OUT")
        in_out_layout.addWidget(btn_in)
        in_out_layout.addWidget(btn_out)

        btn_in.clicked.connect(lambda: self.actionCommand.emit("in"))
        btn_out.clicked.connect(lambda: self.actionCommand.emit("out"))

        layout.addLayout(in_out_layout)

        # Start/Stop legalul
        bottom_layout = QHBoxLayout()
        btn_start = QPushButton("Start")
        btn_stop = QPushButton("Stop")
        bottom_layout.addWidget(btn_start)
        bottom_layout.addWidget(btn_stop)

        btn_start.clicked.connect(lambda: self.actionCommand.emit("start"))
        btn_stop.clicked.connect(lambda: self.actionCommand.emit("stop"))
        layout.addLayout(bottom_layout)


        # Save gomb
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(lambda: self.actionCommand.emit("save"))
        layout.addWidget(btn_save)

        self.setLayout(layout)
