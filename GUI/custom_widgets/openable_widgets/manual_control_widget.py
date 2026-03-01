from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QSlider
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QPen
from GUI.custom_widgets.mainwindow_components.CommandSender import CommandSender
from Pozitioner_and_Communicater.control_actions import ControlActions
from File_managers import config_manager
import re


class ArrowControlPad(QWidget):
    directionPressed = pyqtSignal(str)
    directionReleased = pyqtSignal(str)
    KEY_TO_DIRECTION = {
        Qt.Key_Up: "up",
        Qt.Key_Down: "down",
        Qt.Key_Left: "left",
        Qt.Key_Right: "right",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(170, 170)
        self._active_dirs = set()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus()
        super().mousePressEvent(event)

    def _event_to_direction(self, event):
        return self.KEY_TO_DIRECTION.get(event.key())

    def keyPressEvent(self, event):
        direction = self._event_to_direction(event)
        if direction is None:
            super().keyPressEvent(event)
            return

        if event.isAutoRepeat():
            event.accept()
            return

        if direction not in self._active_dirs:
            self._active_dirs.add(direction)
            self.directionPressed.emit(direction)
            self.update()
        event.accept()

    def keyReleaseEvent(self, event):
        direction = self._event_to_direction(event)
        if direction is None:
            super().keyReleaseEvent(event)
            return

        if event.isAutoRepeat():
            event.accept()
            return

        if direction in self._active_dirs:
            self._active_dirs.remove(direction)
            self.directionReleased.emit(direction)
            self.update()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        margin = 10
        size = min(self.width(), self.height()) - 2 * margin
        x = (self.width() - size) // 2
        y = (self.height() - size) // 2

        fill_color = QColor("#f2f2f2") if self.hasFocus() else QColor("#f8f8f8")
        border_color = QColor("#5f8dd3") if self.hasFocus() else QColor("#9a9a9a")
        painter.setBrush(fill_color)
        painter.setPen(QPen(border_color, 2))
        painter.drawEllipse(x, y, size, size)

        center_x = x + size // 2
        center_y = y + size // 2
        radius = int(size * 0.32)

        active_color = QColor("#2f6fd6")
        inactive_color = QColor("#4a4a4a")
        painter.setPen(QPen(inactive_color, 2))
        if "up" in self._active_dirs:
            painter.setPen(QPen(active_color, 3))
        painter.drawText(center_x - 8, center_y - radius, "↑")

        painter.setPen(QPen(inactive_color, 2))
        if "down" in self._active_dirs:
            painter.setPen(QPen(active_color, 3))
        painter.drawText(center_x - 8, center_y + radius + 8, "↓")

        painter.setPen(QPen(inactive_color, 2))
        if "left" in self._active_dirs:
            painter.setPen(QPen(active_color, 3))
        painter.drawText(center_x - radius - 8, center_y + 5, "←")

        painter.setPen(QPen(inactive_color, 2))
        if "right" in self._active_dirs:
            painter.setPen(QPen(active_color, 3))
        painter.drawText(center_x + radius - 2, center_y + 5, "→")


class ManualControlWidget(QWidget):
    actionCommand = pyqtSignal(str)

    def __init__(self, g_control, log_widget, command_sender, main_window, control_actions: ControlActions, parent=None):
        super().__init__(parent)
        self.stopped = False  # Stop state
        self.paused = False
        self.jog_step_mm = 0.5
        self.jog_feedrate = 2400
        led_cfg = config_manager.load_led_settings(default_pwm=255, default_enabled=False)
        self.led_last_pwm = int(led_cfg.get("led_pwm", 255))
        self.led_enabled = bool(led_cfg.get("led_enabled", False))
        self.led_last_sent_pwm = None

        self.log_widget = log_widget
        self.g_control = g_control
        self.command_sender = command_sender
        self.main_window = main_window
        self.control_actions = control_actions

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
        self.timers["up"].timeout.connect(lambda: self.send_move_command("up"))
        self.timers["down"].timeout.connect(lambda: self.send_move_command("down"))
        self.timers["left"].timeout.connect(lambda: self.send_move_command("left"))
        self.timers["right"].timeout.connect(lambda: self.send_move_command("right"))
        self._update_jog_timer_interval()

        self.label_arrow_help = QLabel("Direction pad: click the circle, then use keyboard arrows")
        layout.addWidget(self.label_arrow_help)

        self.arrow_pad = ArrowControlPad(self)
        self.arrow_pad.directionPressed.connect(self._on_direction_pressed)
        self.arrow_pad.directionReleased.connect(self._on_direction_released)
        layout.addWidget(self.arrow_pad, alignment=Qt.AlignCenter)

        jog_speed_layout = QVBoxLayout()
        jog_speed_header = QHBoxLayout()
        self.lbl_jog_speed_title = QLabel("Jog speed")
        self.lbl_jog_speed_value = QLabel(f"F{self.jog_feedrate}")
        jog_speed_header.addWidget(self.lbl_jog_speed_title)
        jog_speed_header.addStretch()
        jog_speed_header.addWidget(self.lbl_jog_speed_value)
        jog_speed_layout.addLayout(jog_speed_header)

        self.sld_jog_speed = QSlider(Qt.Horizontal)
        self.sld_jog_speed.setMinimum(600)
        self.sld_jog_speed.setMaximum(6000)
        self.sld_jog_speed.setSingleStep(100)
        self.sld_jog_speed.setPageStep(300)
        self.sld_jog_speed.setTickInterval(600)
        self.sld_jog_speed.setTickPosition(QSlider.TicksBelow)
        self.sld_jog_speed.setValue(self.jog_feedrate)
        self.sld_jog_speed.valueChanged.connect(self.on_jog_speed_changed)
        jog_speed_layout.addWidget(self.sld_jog_speed)

        layout.addLayout(jog_speed_layout)

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
        self.btn_led_toggle.setChecked(self.led_enabled)
        self.btn_led_toggle.toggled.connect(self.on_led_toggled)
        self.btn_led_toggle.setText("LED: ON" if self.led_enabled else "LED: OFF")
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
        self.stopped = False
        if self.paused:
            self.control_actions.action_resume_print()
            self.paused = False

    def on_pause(self):
        self.control_actions.action_pause_print()
        self.stopped = True
        self.paused = True



    def send_move_command(self, direction):
        if self.stopped:
            return  # do not send anything
        self.control_actions.action_manual_direction_move(direction, step_mm=self.jog_step_mm, feedrate=self.jog_feedrate)

    def _update_jog_timer_interval(self):
        mm_per_min = max(1.0, float(self.jog_feedrate))
        step_mm = max(0.01, float(self.jog_step_mm))
        interval_ms = int(round((step_mm * 60000.0) / mm_per_min))
        interval_ms = max(8, min(120, interval_ms))
        for timer in self.timers.values():
            timer.setInterval(interval_ms)

    def on_jog_speed_changed(self, value: int):
        speed = max(600, min(6000, int(value)))
        speed = int(round(speed / 100.0) * 100)
        if self.sld_jog_speed.value() != speed:
            self.sld_jog_speed.blockSignals(True)
            self.sld_jog_speed.setValue(speed)
            self.sld_jog_speed.blockSignals(False)
        self.jog_feedrate = speed
        self.lbl_jog_speed_value.setText(f"F{speed}")
        self._update_jog_timer_interval()

    def query_config(self):
        if self.g_control.connected:
            self.control_actions.action_query_settings()
        else:
            self.log_widget.append_log("[ERROR] Machine is not connected for configuration query.")

    def _on_direction_pressed(self, direction):
        timer = self.timers.get(direction)
        if timer and not timer.isActive():
            self.send_move_command(direction)
            timer.start()

    def _on_direction_released(self, direction):
        timer = self.timers.get(direction)
        if timer:
            timer.stop()
        self.control_actions.clear_pending_manual_jog_commands()

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

        # 6. Match user request: reconnect should also trigger Start behavior
        self.on_start()



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
            self.control_actions.send_via_command_sender(cmd)

        self.gcode_input.clear()



    def emergency_stop(self):
        self.control_actions.clear_pending_manual_jog_commands()
        self.control_actions.action_emergency_stop(stop_context=self, send_reset=True)

    def send_home_command(self):
        self.control_actions.action_home()

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
        self.control_actions.action_led_pwm(s)

    def on_led_value_changed(self, val: int):
        """Update display and send for wheel/keyboard changes when LED is ON."""
        pct = int(round(val / 255 * 100))
        self.lbl_led_value.setText(f"{pct}%")
        self.led_last_pwm = val

        # Wheel/keyboard changes do not emit sliderReleased, so send here
        # only when the handle is not actively dragged.
        if self.btn_led_toggle.isChecked() and not self.sld_led.isSliderDown():
            self._send_led_pwm_if_changed(val)

    def on_led_slider_released(self):
        """Send M106 only on slider release when LED is enabled."""
        val = self.sld_led.value()
        self.led_last_pwm = val
        config_manager.save_led_settings(led_pwm=self.led_last_pwm, led_enabled=self.btn_led_toggle.isChecked())
        if self.btn_led_toggle.isChecked():
            self._send_led_pwm_if_changed(val)
        else:
            # In OFF state do not send, only store the new target value
            self.log_widget.append_log(f"[LED] New target PWM stored (OFF state): S{val}")

    def on_led_toggled(self, checked: bool):
        """Toggle button: ON -> send last PWM, OFF -> S0."""
        self.led_enabled = bool(checked)
        if checked:
            # if accidentally set to 0, start with 255
            if self.led_last_pwm == 0:
                self.led_last_pwm = 255
                self.sld_led.setValue(255)
            self.btn_led_toggle.setText("LED: ON")
            self._send_led_pwm_if_changed(self.led_last_pwm)
        else:
            self.btn_led_toggle.setText("LED: OFF")
            self.send_fan_pwm(0)
            self.led_last_sent_pwm = 0
        config_manager.save_led_settings(led_pwm=self.led_last_pwm, led_enabled=self.led_enabled)

    def _send_led_pwm_if_changed(self, val: int):
        """Send PWM only if it differs from the last sent value."""
        pwm = max(0, min(255, int(val)))
        if self.led_last_sent_pwm == pwm:
            return
        self.send_fan_pwm(pwm)
        self.led_last_sent_pwm = pwm

