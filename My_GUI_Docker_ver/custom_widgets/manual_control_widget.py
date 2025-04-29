from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QSize

from My_GUI_Docker_ver.custom_widgets.CommandSender import CommandSender


class ManualControlWidget(QWidget):
    moveCommand = pyqtSignal(str)
    actionCommand = pyqtSignal(str)

    def __init__(self, g_control, parent=None):
        super().__init__(parent)
        self.stopped = False  # ⛔ Stop állapot
        self.paused = False

        self.g_control = g_control

        self.status_label = QLabel("Checking connection...")  # 💡 Előbb hozzuk létre
        self.initUI()  # 💡 Csak ezután hívjuk

        self.command_sender = CommandSender(self.g_control)
        self.command_sender.start()

        self.check_connection()  # 💡 Megjelenítés frissítése

    def initUI(self):
        layout = QVBoxLayout()
        # 💬 Állapot kijelzés felül
        status_layout = QHBoxLayout()
        layout.addWidget(self.status_label)
        btn_reconnect = QPushButton("Reconnect")
        btn_reconnect.clicked.connect(self.reconnect)
        status_layout.addWidget(btn_reconnect)

        layout.addLayout(status_layout)
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
        btn_pause = QPushButton("Pause")
        btn_stop = QPushButton("STOP !")
        btn_stop.setStyleSheet("color: red; font-weight: bold;")

        bottom_layout.addWidget(btn_start)
        bottom_layout.addWidget(btn_pause)
        bottom_layout.addWidget(btn_stop)

        btn_start.clicked.connect(self.on_start)
        btn_pause.clicked.connect(self.on_pause)
        btn_stop.clicked.connect(self.emergency_stop)
        # btn_start.clicked.connect(lambda: self.actionCommand.emit("start"))
        # btn_stop.clicked.connect(lambda: self.actionCommand.emit("stop"))
        layout.addLayout(bottom_layout)

        # Save gomb
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(lambda: self.actionCommand.emit("save"))
        layout.addWidget(btn_save)

        # Home gomb
        btn_home = QPushButton("Home")
        btn_home.clicked.connect(self.send_home_command)
        layout.addWidget(btn_home)

        # --- Kézi G-code beírás ---
        gcode_input_layout = QHBoxLayout()
        self.gcode_input = QLineEdit()
        self.gcode_input.setPlaceholderText("G-code parancs pl. G28, M114...")
        self.btn_send_gcode = QPushButton("Send")
        self.btn_send_gcode.clicked.connect(self.send_custom_gcode)

        gcode_input_layout.addWidget(self.gcode_input)
        gcode_input_layout.addWidget(self.btn_send_gcode)

        layout.addLayout(gcode_input_layout)

        self.setLayout(layout)



    def on_start(self):
        print("[INFO] Start gomb megnyomva")
        self.stopped = False
        if self.paused:
            self.command_sender.sendCommand.emit("M24\n") # Folytatás parancs
            self.paused = False

    def on_pause(self):
        print("[INFO] Pause gomb megnyomva")
        self.command_sender.sendCommand.emit("M0\n")  # Általános stop/szünet
        self.stopped = True
        self.paused = True



    def send_move_command(self, direction):
        if self.stopped:
            return  # ⛔ ne küldjön semmit

        command = None
        if direction == "up":
            command = "G91\nG1 X15 F3000\n"       # X+
        elif direction == "down":
            command = "G91\nG1 X-15 F3000\n"      # X-
        elif direction == "right":
            command = "G91\nG1 Y15 F3000\n"       # Y+
        elif direction == "left":
            command = "G91\nG1 Y-15 F3000\n"      # Y-

        if command:
            print(f"[GCODE] {command.strip()}")
            self.command_sender.sendCommand.emit(command)



    def check_connection(self):
        ser = getattr(self.g_control, "ser", None)
        if self.g_control.connected and ser:
            port = getattr(ser, "port", "ismeretlen port")
            self.status_label.setText(f"✅ {port} - Connected")
        else:
            self.status_label.setText("❌ No connection")

    def reconnect(self):
        # 🔁 Leállítjuk a meglévő szálat, ha fut
        if self.command_sender and self.command_sender.isRunning():
            print("[INFO] Előző CommandSender leállítása...")
            self.command_sender.stop()

        self.try_auto_connect()
        self.check_connection()

        # ✅ Új CommandSender indítása
        self.command_sender = CommandSender(self.g_control)
        self.command_sender.start()


    def try_auto_connect(self):
        print("[INFO] Trying to connect...")
        self.g_control.autoconnect()



    def send_custom_gcode(self):
        gcode = self.gcode_input.text().strip()
        if not gcode:
            return

        if self.g_control.connected:
            commands = gcode.strip().split("G")  # szétvágja a G-k szerint
            for cmd in commands:
                if not cmd.strip():
                    continue
                full_cmd = "G" + cmd.strip()  # visszatesszük a 'G'-t
                if not full_cmd.endswith("\n"):
                    full_cmd += "\n"
                print(f"[CUSTOM GCODE → QUEUE] {full_cmd.strip()}")
                self.command_sender.sendCommand.emit(full_cmd)
            self.gcode_input.clear()
        else:
            print("[HIBA] Gép nincs csatlakoztatva.")

    def emergency_stop(self):
        print("[VÉSZLEÁLLÍTÁS] A gép azonnali leállítása!")
        self.stopped = True
        self.command_sender.sendCommand.emit("M112\n")  # Vészleállítás G-kódja

    def send_home_command(self):
        print("[GCODE] G28")
        self.command_sender.sendCommand.emit("G28\n")

    def closeEvent(self, event):
        # Ha az ablakot "X"-szel zárják be, itt NEM mentünk semmit.
        print("Manula control ablak bezárva felhasználó által (X), mentés kihagyva.")
        try:
            if self.command_sender and self.command_sender.isRunning():
                print("[INFO] CommandSender szál leállítása...")
                self.command_sender.stop()
                print("[INFO] Szál sikeresen leállítva.")
        except Exception as e:
            print(f"[HIBA] Szál leállítása közben hiba történt: {e}")

        event.accept()  # Engedélyezzük a bezárást


