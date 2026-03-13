from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QSlider
from PyQt5.QtCore import pyqtSignal, QTimer, QThread, pyqtSlot
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QPen
import time
import threading
from GUI.custom_widgets.mainwindow_components.CommandSender import CommandSender
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

    def __init__(self, g_control, log_widget, command_sender, main_window, control_actions=None, parent=None):
        super().__init__(parent)
        self.stopped = False  # Stop state
        self.paused = False
        self.led_last_pwm = 255  # last brightness value (0..255)
        self.jog_step_mm = 15.0
        self.jog_feedrate = 3000
        self.jog_interval_ms = 20

        self.log_widget = log_widget
        self.g_control = g_control
        self.command_sender = command_sender
        self.main_window = main_window
        self.control_actions = control_actions
        self._extruder_motion_prepared = False
        self.auto_disable_steppers_on_idle = True
        self.idle_disable_delay_ms = 1200

        self.status_label = QLabel("Checking connection...")
        self._reconnecting = False
        self._idle_disable_timer = QTimer(self)
        self._idle_disable_timer.setSingleShot(True)
        self._idle_disable_timer.setInterval(self.idle_disable_delay_ms)
        self._idle_disable_timer.timeout.connect(self._disable_steppers_if_idle)
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
        self.gcode_input.returnPressed.connect(self.send_custom_gcode)
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

        step_mm = self._current_jog_step_mm()
        command = None
        if direction == "up":
            command = f"G91\nG1 X{step_mm:g} F{self.jog_feedrate}\n"       # X+
        elif direction == "down":
            command = f"G91\nG1 X-{step_mm:g} F{self.jog_feedrate}\n"      # X-
        elif direction == "right":
            command = f"G91\nG1 Y{step_mm:g} F{self.jog_feedrate}\n"       # Y+
        elif direction == "left":
            command = f"G91\nG1 Y-{step_mm:g} F{self.jog_feedrate}\n"      # Y-

        if command:
            log_cmd = " | ".join([p.strip() for p in command.strip().splitlines() if p.strip()])
            self.log_widget.append_log(f"[GCODE] {log_cmd}")
            self.command_sender.sendCommand.emit(command)

    def _update_jog_timer_interval(self):
        interval_ms = self._effective_jog_interval_ms()
        for timer in self.timers.values():
            timer.setInterval(interval_ms)

    def _effective_jog_interval_ms(self) -> int:
        f = int(self.jog_feedrate)
        if f >= 4500:
            return 14
        if f >= 3000:
            return 16
        return int(self.jog_interval_ms)

    def _current_jog_step_mm(self) -> float:
        # step = speed(mm/min) * dt(min)
        interval_ms = self._effective_jog_interval_ms()
        step = float(self.jog_feedrate) * (float(interval_ms) / 60000.0)
        # Keep tiny moves above numerical noise, but still smooth at low speeds.
        return max(0.04, step)

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
            self.log_widget.append_log("[INFO] Querying configuration...")
            # Response logging is handled by CommandSender
            self.g_control.send_command("M503\n") # Marlin: M503 prints settings
        else:
            self.log_widget.append_log("[ERROR] Machine is not connected for configuration query.")

    def _on_direction_pressed(self, direction):
        if self._idle_disable_timer.isActive():
            self._idle_disable_timer.stop()
        timer = self.timers.get(direction)
        if timer and not timer.isActive():
            self.send_move_command(direction)
            timer.start()
            self._prime_continuous_jog(direction)

    def _on_direction_released(self, direction):
        timer = self.timers.get(direction)
        if timer:
            timer.stop()
        self._clear_pending_jog_commands()
        self._schedule_idle_disable()

    def _schedule_idle_disable(self):
        if not self.auto_disable_steppers_on_idle:
            return
        if any(t.isActive() for t in self.timers.values()):
            return
        self._idle_disable_timer.start()

    def _disable_steppers_if_idle(self):
        if not self.auto_disable_steppers_on_idle:
            return
        if not self.g_control.connected:
            return
        if any(t.isActive() for t in self.timers.values()):
            return

        has_pending = False
        pending_fn = getattr(self.g_control, "has_pending_motion_commands", None)
        if callable(pending_fn):
            try:
                has_pending = bool(pending_fn())
            except Exception:
                has_pending = False
        if has_pending:
            self._schedule_idle_disable()
            return

        self.command_sender.sendCommand.emit("M18\n")
        self.log_widget.append_log("[INFO] Idle detected - steppers disabled (M18).")

    def _prime_continuous_jog(self, direction: str):
        """Queue one extra jog shortly after press to reduce startup lag on long holds."""
        if self.jog_feedrate < 2400:
            return
        timer = self.timers.get(direction)
        if timer is None:
            return

        def _send_if_still_holding():
            if timer.isActive() and not self.stopped:
                self.send_move_command(direction)

        QTimer.singleShot(25, _send_if_still_holding)

    def _is_manual_xy_jog_command(self, command: str) -> bool:
        lines = [line.strip().upper() for line in str(command).splitlines() if line.strip()]
        if len(lines) != 2:
            return False
        if lines[0] != "G91":
            return False
        second = lines[1]
        if not second.startswith("G1 "):
            return False
        return " X" in f" {second}" or " Y" in f" {second}"

    def _clear_pending_jog_commands(self):
        removed_total = 0

        clear_sender = getattr(self.command_sender, "clear_pending_commands", None)
        if callable(clear_sender):
            try:
                removed_total += int(clear_sender(self._is_manual_xy_jog_command))
            except Exception:
                pass

        clear_gc = getattr(self.g_control, "clear_pending_manual_jog_commands", None)
        if callable(clear_gc):
            try:
                removed_total += int(clear_gc())
            except Exception:
                pass

        if removed_total > 0:
            self.log_widget.append_log(f"[INFO] Cleared {removed_total} pending jog command(s).")

    def check_connection(self):
        ser = getattr(self.g_control, "ser", None)
        if self.g_control.connected and ser:
            port = getattr(ser, "port", "unknown port")
            self.status_label.setText(f"Connected: {port}")
            if hasattr(self, "btn_reconnect"):
                self.btn_reconnect.setText("Reconnect")
                self.btn_reconnect.setEnabled(True)
        else:
            self.status_label.setText("X - No connection")
            if hasattr(self, "btn_reconnect"):
                self.btn_reconnect.setText("Connect")
                self.btn_reconnect.setEnabled(True)

    def reconnect(self):
        if self._reconnecting:
            self.log_widget.append_log("[WARN] Reconnect already in progress – ignoring duplicate request.")
            return
        self._reconnecting = True
        self.log_widget.append_log("[INFO] Reconnect button pressed.")

        # Disable button to prevent double-clicks during the async attempt
        self.btn_reconnect.setEnabled(False)
        self.btn_reconnect.setText("Connecting...")
        self.status_label.setText("Connecting...")

        # 1. Stop old CommandSender if it's running
        if self.command_sender and self.command_sender.isRunning():
            self.log_widget.append_log("[INFO] Stopping previous CommandSender thread...")
            self.command_sender.stop()
            self.command_sender.wait()
            self.log_widget.append_log("[INFO] Previous CommandSender stopped.")

        # 2. Run autoconnect() in a background thread so the UI stays responsive
        self.log_widget.append_log("[INFO] Starting autoconnect in background thread...")

        def _do_connect():
            self.log_widget.append_log("[INFO] Background: calling g_control.autoconnect()...")
            try:
                self.g_control.autoconnect()
            except Exception as exc:
                self.log_widget.append_log(f"[ERROR] autoconnect() raised an exception: {exc}")
            finally:
                # Post result back to the main thread via a single-shot timer
                QTimer.singleShot(0, self._on_reconnect_done)

        self._reconnect_thread = threading.Thread(target=_do_connect, daemon=True, name="reconnect-thread")
        self._reconnect_thread.start()
        self.log_widget.append_log("[INFO] Waiting for connection result (non-blocking)...")

    @pyqtSlot()
    def _on_reconnect_done(self):
        """Called on the main thread once autoconnect() finishes."""
        self.log_widget.append_log(
            f"[INFO] autoconnect() finished. connected={self.g_control.connected}"
        )

        if self.g_control.connected:
            # 3. Create and start a new CommandSender
            self.log_widget.append_log("[INFO] Creating new CommandSender...")
            new_sender = CommandSender(self.g_control)
            new_sender.start()
            self.log_widget.append_log("[INFO] New CommandSender started.")

            # 4. Update self + inform main window
            self.command_sender = new_sender
            if hasattr(self, "main_window") and self.main_window:
                self.main_window.set_command_sender(new_sender)
                self.log_widget.append_log("[INFO] CommandSender reference updated in MainWindow.")
            self._extruder_motion_prepared = False
            self.log_widget.append_log("[OK] Reconnect successful.")
        else:
            self.log_widget.append_log("[ERROR] Reconnect failed – device not found or no response.")

        # 5. Re-enable button and update status label
        self._reconnecting = False
        self.btn_reconnect.setEnabled(True)
        self.check_connection()

    def _is_extruder_move_command(self, command: str) -> bool:
        cmd = str(command or "").strip().upper()
        if not cmd:
            return False
        if not (cmd.startswith("G0") or cmd.startswith("G1")):
            return False
        return " E" in f" {cmd}"

    def _queue_extruder_preflight(self, select_t0: bool = True):
        if not self.g_control.connected:
            self.log_widget.append_log("[ERROR] Machine is not connected (extruder preflight skipped).")
            return False

        preflight = ["M302 S0", "M17"]
        if select_t0:
            preflight.append("T0")

        for cmd in preflight:
            self.log_widget.append_log(f"[AUTO PREP] {cmd}")
            self.command_sender.sendCommand.emit(cmd + "\n")

        self._extruder_motion_prepared = True
        return True



    def send_custom_gcode(self):
        gcode = self.gcode_input.text()
        if not gcode or not gcode.strip():
            return

        if not self.g_control.connected:
            self.log_widget.append_log("[ERROR] Machine is not connected.")

            return

        # Split before each new G/M/T command (keep the letter)
        commands = [c.strip() for c in re.split(r'(?=[GMT]\d+)', gcode, flags=re.I) if c.strip()]

        needs_extruder_move = any(self._is_extruder_move_command(c) for c in commands)
        has_explicit_tool = any(re.match(r'^\s*T\d+\b', c, flags=re.I) for c in commands)
        has_explicit_extruder_mode = any(re.match(r'^\s*M8[23]\b', c, flags=re.I) for c in commands)

        if needs_extruder_move and not self._extruder_motion_prepared:
            if not self._queue_extruder_preflight(select_t0=not has_explicit_tool):
                return

        # Keep E moves repeatable: if user didn't specify M82/M83, force relative-extruder mode.
        if needs_extruder_move and not has_explicit_extruder_mode:
            self.log_widget.append_log("[AUTO PREP] M83")
            self.command_sender.sendCommand.emit("M83\n")

        for cmd in commands:
            if not cmd.endswith('\n'):
                cmd += '\n'
            self.log_widget.append_log(f"[CUSTOM GCODE -> QUEUE] {cmd.strip()}")

            self.command_sender.sendCommand.emit(cmd)

        self.gcode_input.clear()



    def emergency_stop(self):
        self.log_widget.append_log("[EMERGENCY STOP] Immediate machine stop!")

        # M410 = quickstop (halts all motion immediately, firmware stays alive)
        # M18  = disable all steppers
        # We deliberately do NOT send M112 – that kills the firmware and requires
        # a power cycle to recover (especially on STM32-based boards like Ender 3 V3 SE).
        try:
            if self.g_control.ser and self.g_control.ser.is_open:
                self.g_control.ser.write(b"M410\n")
                self.g_control.ser.write(b"M18\n")
                self.g_control.ser.flush()
                self.log_widget.append_log("[EMERGENCY STOP] M410 + M18 sent – motion stopped, connection kept.")
            else:
                self.log_widget.append_log("[EMERGENCY STOP] Not connected – nothing to stop.")
        except Exception as exc:
            self.log_widget.append_log(f"[EMERGENCY STOP] Write error: {exc}")
        self.check_connection()

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

