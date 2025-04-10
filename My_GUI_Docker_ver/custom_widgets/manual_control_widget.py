from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import pyqtSignal, QTimer

from My_GUI_Docker_ver.custom_widgets.CommandSender import CommandSender


class ManualControlWidget(QWidget):
    moveCommand = pyqtSignal(str)
    actionCommand = pyqtSignal(str)

    def __init__(self,g_control, parent=None):
        super().__init__(parent)
        self.initUI()
        self.stopped = False  # ⛔ Stop állapot
        self.g_control = g_control
        self.command_sender = CommandSender(self.g_control)
        self.command_sender.start()

    def initUI(self):
        layout = QVBoxLayout()

        # Mozgatási időzítők
        self.timers = {
            "up": QTimer(self),
            "down": QTimer(self),
            "left": QTimer(self),
            "right": QTimer(self),
        }

        # Iránygombok
        dir_layout = QVBoxLayout()
        up = QPushButton("↑")
        down = QPushButton("↓")
        left = QPushButton("←")
        right = QPushButton("→")

        self.timers["up"].timeout.connect(lambda: self.send_move_command("up"))
        self.timers["down"].timeout.connect(lambda: self.send_move_command("down"))
        self.timers["left"].timeout.connect(lambda: self.send_move_command("left"))
        self.timers["right"].timeout.connect(lambda: self.send_move_command("right"))


        for timer in self.timers.values():
            timer.setInterval(250)  # 100ms-onta mozgat

        up.pressed.connect(self.timers["up"].start)
        up.released.connect(self.timers["up"].stop)
        down.pressed.connect(self.timers["down"].start)
        down.released.connect(self.timers["down"].stop)
        left.pressed.connect(self.timers["left"].start)
        left.released.connect(self.timers["left"].stop)
        right.pressed.connect(self.timers["right"].start)
        right.released.connect(self.timers["right"].stop)

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

        btn_start.clicked.connect(self.on_start)
        btn_stop.clicked.connect(self.on_stop)
        # btn_start.clicked.connect(lambda: self.actionCommand.emit("start"))
        # btn_stop.clicked.connect(lambda: self.actionCommand.emit("stop"))
        layout.addLayout(bottom_layout)


        # Save gomb
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(lambda: self.actionCommand.emit("save"))
        layout.addWidget(btn_save)

        self.setLayout(layout)

    def on_start(self):
        print("[INFO] Start gomb megnyomva")
        self.stopped = False

    def on_stop(self):
        print("[INFO] Stop gomb megnyomva")
        self.stopped = True


    def send_move_command(self, direction):
        if self.stopped:
            return  # ⛔ ne küldjön semmit

        command = None
        if direction == "up":
            command = "G91\nG1 X1 F3000\n"       # X+
        elif direction == "down":
            command = "G91\nG1 X-1 F3000\n"      # X-
        elif direction == "right":
            command = "G91\nG1 Y1 F3000\n"       # Y+
        elif direction == "left":
            command = "G91\nG1 Y-1 F3000\n"      # Y-

        if command:
            print(f"[GCODE] {command.strip()}")
            self.command_sender.sendCommand.emit(command)

    def closeEvent(self, event):
        print("🧹 ManualControlWidget.closeEvent() meghívva!")
        if self.command_sender.isRunning():
            self.command_sender.running = False
            self.command_sender.quit()
            self.command_sender.wait()
        event.accept()


