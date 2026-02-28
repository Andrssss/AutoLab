from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QSlider
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtCore import Qt
import time
from GUI.custom_widgets.mainwindow_components.CommandSender import CommandSender
import re


class ManualControlWidget(QWidget):
    actionCommand = pyqtSignal(str)

    def __init__(self, g_control, log_widget, command_sender, main_window, parent=None):
        super().__init__(parent)
        self.stopped = False  # Stop state
        self.paused = False
        self.led_last_pwm = 255  # last brightness value (0..255)

        self.log_widget = log_widget
        self.g_control = g_control
        self.command_sender = command_sender
        self.main_window = main_window

        self.status_label = QLabel("Checking connection...")
        self.initUI()
        self.check_connection()

    def initUI(self):
        layout = QVBoxLayout()
        # Status display at the top
        status_layout = QHBoxLayout()
        layout.addWidget(self.status_label)
        self.btn_reconnect = QPushButton("Reconnect")
        self.btn_reconnect.clicked.connect(self.reconnect)
        status_layout.addWidget(self.btn_reconnect)
        layout.addLayout(status_layout)

        # Query configuration button
        btn_check_config = QPushButton("Check Config")
        btn_check_config.clicked.connect(self.query_config)
        layout.addWidget(btn_check_config)

        # Movement timers
        self.timers = {
            "up": QTimer(self),
            "down": QTimer(self),
            "left": QTimer(self),
            "right": QTimer(self),
        }


        # Direction buttons
        dir_layout = QVBoxLayout()
        up = QPushButton("^")
        down = QPushButton("v")
        left = QPushButton("<")
        right = QPushButton(">")
        self.timers["up"].timeout.connect(lambda: self.send_move_command("up"))
        self.timers["down"].timeout.connect(lambda: self.send_move_command("down"))
        self.timers["left"].timeout.connect(lambda: self.send_move_command("left"))
        self.timers["right"].timeout.connect(lambda: self.send_move_command("right"))
        for timer in self.timers.values():
            timer.setInterval(250)  # move every 250ms
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

        # IN/OUT buttons
        in_out_layout = QVBoxLayout()
        btn_in = QPushButton("IN")
        btn_out = QPushButton("OUT")
        in_out_layout.addWidget(btn_in)
        in_out_layout.addWidget(btn_out)
        btn_in.clicked.connect(lambda: self.actionCommand.emit("in"))
        btn_out.clicked.connect(lambda: self.actionCommand.emit("out"))
        layout.addLayout(in_out_layout)

        # Start/Stop at the bottom
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
        layout.addLayout(bottom_layout)

        # Save button
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(lambda: self.actionCommand.emit("save"))
        layout.addWidget(btn_save)

        # Home button
        btn_home = QPushButton("Home")
        btn_home.clicked.connect(self.send_home_command)
        layout.addWidget(btn_home)

        # --- LED (D9) control: brightness + toggle ---
        led_layout = QVBoxLayout()
        row1 = QHBoxLayout()
        lbl_led = QLabel("LED (D9)")
        self.lbl_led_value = QLabel("100%")
        row1.addWidget(lbl_led)
        row1.addStretch()
        row1.addWidget(self.lbl_led_value)
        led_layout.addLayout(row1)
        row2 = QHBoxLayout()
        self.sld_led = QSlider(Qt.Horizontal)
        self.sld_led.setMinimum(0)
        self.sld_led.setMaximum(255)
        self.sld_led.setSingleStep(1)
        self.sld_led.setPageStep(5)
        self.sld_led.setTickInterval(25)
        self.sld_led.setTickPosition(QSlider.TicksBelow)
        self.sld_led.setValue(self.led_last_pwm)
        # update display while dragging; send on mouse release
        self.sld_led.valueChanged.connect(self.on_led_value_changed)
        self.sld_led.sliderReleased.connect(self.on_led_slider_released)
        self.btn_led_toggle = QPushButton("LED: OFF")
        self.btn_led_toggle.setCheckable(True)
        self.btn_led_toggle.setChecked(False)
        self.btn_led_toggle.toggled.connect(self.on_led_toggled)
        row2.addWidget(self.sld_led, 1)
        row2.addWidget(self.btn_led_toggle)
        led_layout.addLayout(row2)
        layout.addLayout(led_layout)


        # --- Manual G-code input ---
        gcode_input_layout = QHBoxLayout()
        self.gcode_input = QLineEdit()
        self.gcode_input.setPlaceholderText("G-code command e.g. G28, M114...")
        self.btn_send_gcode = QPushButton("Send")
        self.btn_send_gcode.clicked.connect(self.send_custom_gcode)
        gcode_input_layout.addWidget(self.gcode_input)
        gcode_input_layout.addWidget(self.btn_send_gcode)
        layout.addLayout(gcode_input_layout)
        self.setLayout(layout)



    def on_start(self):
        self.log_widget.append_log("[CONTROL_CMD] Start requested -> sending M24 (resume print)")
        self.stopped = False
        if self.paused:
            self.command_sender.sendCommand.emit("M24\n") # Resume command
            self.paused = False

    def on_pause(self):
        self.log_widget.append_log("[CONTROL_CMD] Pause requested -> sending M0 (pause/stop)")
        self.command_sender.sendCommand.emit("M0\n")  # General stop/pause
        self.stopped = True
        self.paused = True



    def send_move_command(self, direction):
        if self.stopped:
            return  # do not send anything

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
            log_cmd = " | ".join([p.strip() for p in command.strip().splitlines() if p.strip()])
            self.log_widget.append_log(f"[GCODE] {log_cmd}")
            self.command_sender.sendCommand.emit(command)

    def query_config(self):
        if self.g_control.connected:
            self.log_widget.append_log("[INFO] Querying configuration...")
            # Response logging is handled by CommandSender
            self.g_control.send_command("M503\n") # Marlin: M503 prints settings
        else:
            self.log_widget.append_log("[ERROR] Machine is not connected for configuration query.")

    def check_connection(self):
        ser = getattr(self.g_control, "ser", None)
        if self.g_control.connected and ser:
            port = getattr(ser, "port", "unknown port")
            self.status_label.setText(f"Connected: {port}")
            if hasattr(self, "btn_reconnect"):
                self.btn_reconnect.setText("Reconnect")
        else:
            self.status_label.setText("X - No connection")
            if hasattr(self, "btn_reconnect"):
                self.btn_reconnect.setText("Connect")

    def reconnect(self):
        # 1. Stop old CommandSender if it's running
        if self.command_sender and self.command_sender.isRunning():
            self.log_widget.append_log("[INFO] Stopping previous CommandSender...")
            self.command_sender.stop()
            self.command_sender.wait()  # Wait for it to stop

        # 2. Try to reconnect the g_control
        self.log_widget.append_log("[INFO] Attempting to reconnect to device...")
        self.g_control.autoconnect()

        # 3. Create and start a new CommandSender
        new_sender = CommandSender(self.g_control)
        new_sender.start()
        self.log_widget.append_log("[INFO] New CommandSender started.")

        # 4. Update self + inform main window
        self.command_sender = new_sender
        if hasattr(self, "main_window") and self.main_window:
            self.main_window.set_command_sender(new_sender)
            self.log_widget.append_log("[INFO] CommandSender reference updated in MainWindow.")


        # 5. Update connection status on the UI
        self.check_connection()



    def send_custom_gcode(self):
        gcode = self.gcode_input.text()
        if not gcode or not gcode.strip():
            return

        if not self.g_control.connected:
            self.log_widget.append_log("[ERROR] Machine is not connected.")

            return

        # Split before each new G/M/T command (keep the letter)
        commands = [c.strip() for c in re.split(r'(?=[GMT]\d+)', gcode, flags=re.I) if c.strip()]

        for cmd in commands:
            if not cmd.endswith('\n'):
                cmd += '\n'
            self.log_widget.append_log(f"[CUSTOM GCODE -> QUEUE] {cmd.strip()}")

            self.command_sender.sendCommand.emit(cmd)

        self.gcode_input.clear()



    def emergency_stop(self):
        self.log_widget.append_log("[EMERGENCY STOP] Immediate machine stop!")

        # self.stopped = True --> usually resetting RAMPS is enough
        self.command_sender.sendCommand.emit("M112\n")  # emergency stop
        self.log_widget.append_log("[EMERGENCY STOP] Press the reset button on RAMPS!")
        time.sleep(0.2)
        #self.command_sender.sendCommand.emit("M18\n")  # motor off
        #self.command_sender.sendCommand.emit("M84\n")  # minden motor off
        #time.sleep(0.2)
        # Reset command - only if firmware allows it (currently it does not)
        # self.command_sender.sendCommand.emit("M999\n")
        # self.log_widget.append_log("[INFO] Reset (M999) command sent to firmware.")

    def send_home_command(self):
        self.log_widget.append_log("[GCODE] G28")
        self.command_sender.sendCommand.emit("G28\n")

    def closeEvent(self, event):
        # If the window is closed with "X", do not save anything here.
        self.log_widget.append_log("Manual control window closed by user (X), save skipped.")
        event.accept()  # Allow close



    def send_fan_pwm(self, s_value: int):
        """Send M106 S<0..255> safely (only when connected)."""
        s = max(0, min(255, int(s_value)))
        if not self.g_control.connected:
            self.log_widget.append_log("[ERROR] Machine is not connected (M106 skipped).")

            return
        cmd = f"M106 S{s}\n" if s > 0 else "M106 S0\n"  # M107 could also be used for OFF
        self.log_widget.append_log(f"[LED] {cmd.strip()}")

        self.command_sender.sendCommand.emit(cmd)

    def on_led_value_changed(self, val: int):
        """Update display only (does not send command)."""
        pct = int(round(val / 255 * 100))
        self.lbl_led_value.setText(f"{pct}%")

    def on_led_slider_released(self):
        """Send M106 only on slider release when LED is enabled."""
        val = self.sld_led.value()
        self.led_last_pwm = val
        if self.btn_led_toggle.isChecked():
            self.send_fan_pwm(val)
        else:
            # In OFF state do not send, only store the new target value
            self.log_widget.append_log(f"[LED] New target PWM stored (OFF state): S{val}")

    def on_led_toggled(self, checked: bool):
        """Toggle button: ON -> send last PWM, OFF -> S0."""
        if checked:
            # if accidentally set to 0, start with 255
            if self.led_last_pwm == 0:
                self.led_last_pwm = 255
                self.sld_led.setValue(255)
            self.btn_led_toggle.setText("LED: ON")
            self.send_fan_pwm(self.led_last_pwm)
        else:
            self.btn_led_toggle.setText("LED: OFF")
            self.send_fan_pwm(0)

