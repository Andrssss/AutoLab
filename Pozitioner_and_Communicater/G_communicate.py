import threading
import time
import queue
import logging
import serial  # pyserial
import serial.tools.list_ports
from File_managers import marlin_config_manager
from File_managers import config_manager
from Pozitioner_and_Communicater.gcode_presets import MARLIN_COMMAND_MAP


# Marlin doesnâ€™t auto-calibrate steps â†’ you set/adjust them with M92, test a move, measure, then refine.
# Marlin can store settings in EEPROM (M500) and print them (M503)
# Field size (soft limits) is mostly firmware compile-time (Configuration.h: X_BED_SIZE, Y_BED_SIZE,
# or X_MIN/MAX_POS, Y_MIN/MAX_POS). You can disable soft endstops during calibration with M211 S0, then re-enable with M211 S1.
# Using G0/G1; positions are mm, feedrate F is mm/min.


class GCodeControl:
    def __init__(self, lock=None):
        self.lock = lock
        self.ser = None
        self.lock = lock
        self.connected = False
        self.label_status = None  # can be set externally (e.g., from the GUI)
        self.log_widget = None  # set externally in MainWindow


        # Command queues for each thread
        self.x_motor_queue = queue.Queue()
        self.y_motor_queue = queue.Queue()
        self.aux_queue = queue.Queue()
        self.control_queue = queue.Queue()
        self._worker_busy = {
            "X_motor": False,
            "Y_motor": False,
            "AUX": False,
            "CONTROL": False,
        }
        self._worker_busy_lock = threading.Lock()

        self.running = True
        self._emergency_latched = False
        self._emergency_lock = threading.Lock()

    def __del__(self):
        self.log("[INFO] GCodeControl destructor called")

        # Stop threads if still running
        try:
            self.stop_threads()
            self.log("[INFO] Threads stopped")
        except Exception as e:
            self.log(f"[WARN] Failed to stop threads: {e}")

        # Close serial port
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                self.log("[INFO] Serial port closed")
        except Exception as e:
            self.log(f"[WARN] Failed to close serial port: {e}")

    def set_connected(self, connected):
        self.connected = connected
        self.log(f"[INFO] Serial port connected - {self.connected}")

    def _probe_marlin_connection(self, ser, timeout=3.5):
        """Best-effort RAMPS/Marlin probe: waits for boot chatter and sends M115 if needed."""
        try:
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except Exception:
                pass

            # Many boards reset on open; allow boot time.
            time.sleep(1.2)
            ser.write(b"\n")
            ser.flush()

            start = time.time()
            m115_sent = False

            while (time.time() - start) < timeout:
                if (not m115_sent) and (time.time() - start) > 0.6:
                    try:
                        ser.write(b"M115\n")
                        ser.flush()
                        m115_sent = True
                    except Exception:
                        pass

                if getattr(ser, "in_waiting", 0):
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        low = line.lower()
                        if (
                            "ok" in low
                            or "firmware_name" in low
                            or "marlin" in low
                            or "echo:" in low
                            or ("x:" in low and "y:" in low)
                        ):
                            return True
                else:
                    time.sleep(0.05)

            return False
        except Exception as e:
            self.log(f"[WARN] Probe failed: {e}")
            return False

    def _command_for_log(self, command: str) -> str:
        parts = [p.strip() for p in str(command).replace("\r", "\n").split("\n") if p.strip()]
        return " | ".join(parts)

    def _is_emergency_allowed_command(self, command: str) -> bool:
        cmd = self._command_for_log(command).upper().strip()
        if not cmd:
            return False
        return cmd.startswith("M112") or cmd.startswith("M999")

    def set_emergency_latched(self, latched: bool):
        with self._emergency_lock:
            self._emergency_latched = bool(latched)

    def is_emergency_latched(self) -> bool:
        with self._emergency_lock:
            return bool(self._emergency_latched)

    def are_command_threads_alive(self) -> bool:
        thread_names = ("x_thread", "y_thread", "aux_thread", "control_thread")
        for name in thread_names:
            thread = getattr(self, name, None)
            if thread is None or not thread.is_alive():
                return False
        return True

    def _set_worker_busy(self, name: str, busy: bool):
        with self._worker_busy_lock:
            if name in self._worker_busy:
                self._worker_busy[name] = bool(busy)

    def has_pending_motion_commands(self) -> bool:
        try:
            if not self.x_motor_queue.empty() or not self.y_motor_queue.empty() or not self.control_queue.empty():
                return True
        except Exception:
            return False

        with self._worker_busy_lock:
            return bool(
                self._worker_busy.get("X_motor")
                or self._worker_busy.get("Y_motor")
                or self._worker_busy.get("CONTROL")
            )

    def _is_xy_move_command(self, command: str) -> bool:
        line = self._command_for_log(command).upper().strip()
        if not line:
            return False
        if not (line.startswith("G0") or line.startswith("G1")):
            return False
        return " X" in f" {line}" and " Y" in f" {line}"

    def _is_manual_jog_command(self, command: str) -> bool:
        parts = [p.strip().upper() for p in str(command).replace("\r", "\n").split("\n") if p.strip()]
        if len(parts) != 2:
            return False
        if parts[0] != "G91":
            return False
        second = parts[1]
        return second.startswith("G1 ") and (" X" in f" {second}" or " Y" in f" {second}")

    def _is_motion_command(self, command: str) -> bool:
        if not command:
            return False
        parts = [p.strip().upper() for p in str(command).replace("\r", "\n").split("\n") if p.strip()]
        if not parts:
            return False
        if self._is_manual_jog_command(command):
            return True
        return any(p.startswith("G0") or p.startswith("G1") for p in parts)

    def _filter_queue(self, q: queue.Queue, predicate):
        kept = []
        removed = 0
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break

            if item == "STOP":
                kept.append(item)
                continue

            if predicate(item):
                removed += 1
            else:
                kept.append(item)

        for item in kept:
            q.put(item)

        return removed

    def clear_all_pending_commands(self) -> int:
        removed = 0
        removed += self._filter_queue(self.x_motor_queue, lambda _cmd: True)
        removed += self._filter_queue(self.y_motor_queue, lambda _cmd: True)
        removed += self._filter_queue(self.aux_queue, lambda _cmd: True)
        removed += self._filter_queue(self.control_queue, lambda _cmd: True)
        return removed

    def _coalesce_axis_jog_queue(self, q: queue.Queue):
        """Keep only non-jog items in axis queue so the latest jog can be appended once."""
        kept = []
        removed = 0
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break

            if item == "STOP":
                kept.append(item)
            elif self._is_manual_jog_command(item):
                removed += 1
            else:
                kept.append(item)

        for item in kept:
            q.put(item)

        return removed

    def clear_pending_manual_jog_commands(self) -> int:
        removed = 0
        removed += self._coalesce_axis_jog_queue(self.x_motor_queue)
        removed += self._coalesce_axis_jog_queue(self.y_motor_queue)
        return removed

    def clear_pending_motion_commands(self) -> int:
        removed = 0
        removed += self._filter_queue(self.x_motor_queue, self._is_motion_command)
        removed += self._filter_queue(self.y_motor_queue, self._is_motion_command)
        removed += self._filter_queue(self.control_queue, self._is_motion_command)
        return removed



    def send_command(self, command, wait_for_completion=False):
        if not self.connected:
            self.log("[WARN] send_command - not connected")
            return None

        if self.is_emergency_latched() and not self._is_emergency_allowed_command(command):
            self.log(f"[EMERGENCY] Blocked command while latched: {self._command_for_log(command)}")
            return None

        # always send command
        if not command.endswith("\n"):
            command += "\n"

        if self.lock:
            with self.lock:
                self.ser.write(command.encode('utf-8'))
        else:
            self.ser.write(command.encode('utf-8'))

        time.sleep(0.05 if wait_for_completion else 0.005)

        if wait_for_completion:
            # only then send M400 and wait for response
            if self.lock:
                with self.lock:
                    self.ser.write(b"M400\n")
            else:
                self.ser.write(b"M400\n")

            time.sleep(0.05)
            return self.wait_for_ok(timeout=5)

        return None  # command sent, no wait requested




    def wait_for_ok(self, timeout=5):
        if not self.ser:
            self.log("[ERROR] No valid serial connection (ser = None)")
            return None

        start_time = time.time()
        while True:
            if self.lock:
                with self.lock:
                    response = self.ser.readline().decode('utf-8', errors='ignore').strip().lower()
            else:
                response = self.ser.readline().decode('utf-8', errors='ignore').strip().lower()

            if "ok" in response:
                # return None
                return response

            if time.time() - start_time > timeout:
                self.log("[ERROR] G-code response timeout (no 'ok' received)")
                return None

    def worker_loop(self, q: queue.Queue, name: str):
        if self.connected:
            self.log(f"[{name}] thread started.")
            while self.running:
                try:
                    command = q.get(timeout=1)
                    self._set_worker_busy(name, True)
                    if command == "STOP":
                        self.log(f"[{name}] thread stopping.")
                        break
                    if self.is_emergency_latched() and not self._is_emergency_allowed_command(command):
                        continue
                    cmd_log = self._command_for_log(command)
                    if name in ("X_motor", "Y_motor"): # Wait only here; other paths may not return RAMPS responses
                        is_jog = self._is_manual_jog_command(command)
                        if not is_jog:
                            self.log(f"[{name}] -> {cmd_log}")
                        wait_move = not is_jog
                        self.send_command(command, wait_for_completion=wait_move)
                    elif name == "AUX":
                        # Specifically for M42 control
                        if command.startswith("M42"):
                            self.log(f"[AUX] M42 command: {cmd_log}")
                            self.send_command(command, wait_for_completion=False)
                    elif name == "CONTROL":
                        if not command.lstrip().upper().startswith("M106"):
                            self.log(f"[CONTROL] -> {cmd_log}")
                        self.send_command(command, wait_for_completion=self._is_xy_move_command(command))
                except queue.Empty:
                    continue
                finally:
                    self._set_worker_busy(name, False)
        else:
            self.log(f"[WARN] {name} - not connected")

    def start_threads(self):
        if (self.connected):
            """Start threads: X_motor, Y_motor, AUX (other functions)."""
            # Do not start new threads if they are already running
            if hasattr(self, 'x_thread') and self.x_thread.is_alive():
                self.log("[WARN] Threads are already running; stop them before restarting.")
                return

            self.x_thread = threading.Thread(target=self.worker_loop, args=(self.x_motor_queue, "X_motor"))
            self.y_thread = threading.Thread(target=self.worker_loop, args=(self.y_motor_queue, "Y_motor"))
            self.aux_thread = threading.Thread(target=self.worker_loop, args=(self.aux_queue, "AUX"))
            self.control_thread = threading.Thread(target=self.worker_loop, args=(self.control_queue, "CONTROL"))

            self.control_thread.start()
            self.x_thread.start()
            self.y_thread.start()
            self.aux_thread.start()
        else:
            self.log("[WARN] start_threads - not connected")


    def set_lock(self, lock):
        self.lock = lock


    # Command-related logic
    def set_aux_output(self):
        if(self.connected):
            for _ in range(3):
                self.send_command("M42 P58 S200 \n")
                self.send_command("M42 P58 S0 \n")
        else:
            self.log("[WARN] start_threads - not connected")

    def query_endstops(self):
        if self.connected:
            if not self.ser:
                self.log("[ERROR] No valid serial connection (ser = None)")
                return ""

            if self.lock:
                with self.lock:
                    self.ser.write("M119\n".encode('utf-8'))
            else:
                self.ser.write("M119\n".encode('utf-8'))

            time.sleep(0.1)
            if self.lock:
                with self.lock:
                    response = self.ser.read_all().decode('utf-8', errors='ignore')
            else:
                response = self.ser.read_all().decode('utf-8', errors='ignore')

            return response
        else:
            self.log("[INFO] query_endstops - not connected")
            return ""

    def new_command(self, command: str):
        if self.connected:
            if self.is_emergency_latched() and not self._is_emergency_allowed_command(command):
                self.log(f"[EMERGENCY] Queue reject while latched: {self._command_for_log(command)}")
                return False

            cmd_upper = command.upper().strip()
            cmd_log = self._command_for_log(cmd_upper)
            is_jog = self._is_manual_jog_command(cmd_upper)

            if "G1" in cmd_upper or "G0" in cmd_upper:
                if "X" in cmd_upper and "Y" not in cmd_upper:
                    if is_jog:
                        self._coalesce_axis_jog_queue(self.x_motor_queue)
                    if not is_jog:
                        self.log(f"[DISPATCH] X_motor_queue <- {cmd_log}")
                    self.send_to_x(cmd_upper)
                    return True
                elif "Y" in cmd_upper and "X" not in cmd_upper:
                    if is_jog:
                        self._coalesce_axis_jog_queue(self.y_motor_queue)
                    if not is_jog:
                        self.log(f"[DISPATCH] Y_motor_queue <- {cmd_log}")
                    self.send_to_y(cmd_upper)
                    return True
                else:
                    self.log(f"[DISPATCH] CONTROL_queue (mixed XY or other) <- {cmd_log}")
                    self.send_to_control(cmd_upper)
                    return True
            elif cmd_upper.startswith("M42"):
                self.log(f"[DISPATCH] AUX_queue (M42) <- {cmd_log}")
                self.send_to_aux(cmd_upper)
                return True
            else:
                self.log(f"[DISPATCH] CONTROL_queue <- {cmd_log}")
                self.send_to_control(cmd_upper)
                return True
        else:
            self.log("[WARN] new_command - not connected")
            return False


    def autoconnect(self):
        self.log("[INFO] autoconnect() called")

        # Stop existing threads if they are running
        if hasattr(self, 'x_thread') and self.x_thread.is_alive():
            self.log("[INFO] Stopping previous threads before reconnect...")
            self.stop_threads()
            # running flag needs to be enabled again
            self.running = True


        # First try connecting using YAML-saved settings
        try:
            settings = config_manager.load_settings()
            preferred_port = settings.get("selected_port", None)
            preferred_baud = settings.get("baud", None)
        except Exception as e:
            self.log(f"[WARN] Failed to load settings: {e}")
            preferred_port = preferred_baud = None

        try:
            available_ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception as e:
            self.log(f"[WARN] Failed to enumerate serial ports: {e}")
            available_ports = []

        fallback_bauds = [250000, 125000, 500000, 115200]

        def _to_int_baud(value, default=250000):
            try:
                return int(value)
            except Exception:
                return int(default)

        def _unique_bauds(first_baud):
            ordered = [_to_int_baud(first_baud)] + fallback_bauds
            unique = []
            for b in ordered:
                if b not in unique:
                    unique.append(b)
            return unique

        def _try_connect_port(port_name, baud_list, source_label):
            for baud in baud_list:
                try:
                    self.log(f"[INFO] Trying {source_label}: {port_name} @ {baud}")
                    ser = serial.Serial(port_name, int(baud), timeout=1, write_timeout=1, rtscts=False, dsrdtr=False)
                    if self._probe_marlin_connection(ser, timeout=5.0):
                        self.ser = ser
                        self.set_connected(True)
                        if self.label_status:
                            self.label_status.setText(f"Connected successfully: {port_name} @ {baud} baud")
                        self.log(f"[INFO] Successful connection ({source_label}): {port_name} @ {baud} baud")
                        config_manager.update_settings({
                            "selected_port": port_name,
                            "baud": int(baud)
                        })
                        self.start_threads()
                        self.start_response_listener()
                        self.load_marlin_config()
                        return True
                    ser.close()
                    self.log(f"[WARN] Probe timeout/no valid response: {port_name} @ {baud}")
                except Exception as e:
                    self.log(f"[WARN] {source_label} failed: {port_name} @ {baud} - {e}")
            return False

        # Try saved settings first
        if preferred_port:
            if available_ports and preferred_port not in available_ports:
                self.log(f"[WARN] Saved port {preferred_port} not currently listed. Available: {available_ports}")
            if _try_connect_port(preferred_port, _unique_bauds(preferred_baud), "saved"):
                return

        # Fallback: try all port/baud combinations
        self.log("[INFO] Fallback: automatic scan started...")
        baud_rates = fallback_bauds
        ports = serial.tools.list_ports.comports()

        if not ports:
            if self.label_status:
                self.label_status.setText("No serial device found.")
            self.log("[INFO] No serial device found.")
            return

        for port in ports:
            port_name = port.device
            if preferred_port and port_name == preferred_port:
                continue
            for baud in baud_rates:
                try:
                    self.log(f"[INFO] Trying: {port_name} @ {baud}")
                    ser = serial.Serial(port_name, baud, timeout=1, write_timeout=1, rtscts=False, dsrdtr=False)
                    if self._probe_marlin_connection(ser, timeout=5.0):
                        self.ser = ser
                        self.set_connected(True)
                        if self.label_status:
                            self.label_status.setText(f"Connected successfully: {port_name} @ {baud} baud")
                        self.log(f"[INFO] Successful connection: {port_name} @ {baud} baud")

                        # Save settings
                        config_manager.update_settings({
                            "selected_port": port_name,
                            "baud": baud
                        })

                        self.start_threads()
                        self.start_response_listener()
                        self.load_marlin_config()
                        return
                    else:
                        ser.close()

                except Exception as e:
                    self.log(f"[ERROR] {port_name} @ {baud} - {e}")

        if self.label_status:
            self.label_status.setText("Failed to connect to any serial port.")
        self.log("[INFO] Connection failed.")

    def reconnect_saved(self, fallback: bool = True) -> bool:
        """Reconnect using saved selected_port + baud from settings, optional fallback scan."""
        try:
            settings = config_manager.load_settings()
            preferred_port = settings.get("selected_port", None)
            preferred_baud = int(settings.get("baud", 250000))
        except Exception as e:
            self.log(f"[WARN] Failed to load saved connection settings: {e}")
            preferred_port = None
            preferred_baud = 250000

        if not preferred_port:
            self.log("[WARN] No saved port found in settings.")
            if fallback:
                self.autoconnect()
                return bool(self.connected)
            return False

        if hasattr(self, 'x_thread') and self.x_thread.is_alive():
            self.log("[INFO] Stopping previous threads before reconnect_saved...")
            self.stop_threads()
            self.running = True

        try:
            self.log(f"[INFO] reconnect_saved: trying {preferred_port} @ {preferred_baud}")
            ser = serial.Serial(preferred_port, preferred_baud, timeout=1, write_timeout=1, rtscts=False, dsrdtr=False)
            if self._probe_marlin_connection(ser, timeout=5.0):
                self.ser = ser
                self.set_connected(True)
                if self.label_status:
                    self.label_status.setText(f"Connected successfully: {preferred_port} @ {preferred_baud} baud")
                self.log(f"[INFO] reconnect_saved success: {preferred_port} @ {preferred_baud}")

                config_manager.update_settings({
                    "selected_port": preferred_port,
                    "baud": int(preferred_baud)
                })

                self.start_threads()
                self.start_response_listener()
                self.load_marlin_config()
                return True

            ser.close()
            self.log(f"[WARN] reconnect_saved probe failed: {preferred_port} @ {preferred_baud}")
        except Exception as e:
            self.log(f"[WARN] reconnect_saved failed: {preferred_port} @ {preferred_baud} - {e}")

        if fallback:
            self.log("[INFO] reconnect_saved fallback -> autoconnect()")
            self.autoconnect()
            return bool(self.connected)

        return False

    def start_response_listener(self):
        if hasattr(self, "response_thread") and self.response_thread.is_alive():
            self.log("[INFO] Response listener thread is already running.")
            return

        self.response_running = True
        self.response_thread = threading.Thread(target=self.response_loop, daemon=True)
        self.response_thread.start()
        self.log("[INFO] Response listener thread started.")

    def response_loop(self):
        while self.response_running and self.connected and self.ser:
            try:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        if line != "ok" :
                            self.log(f"[RESPONSE] {line}")
                else:
                    time.sleep(0.05)
            except Exception as e:
                self.log(f"[ERROR] Response read error: {e}")
                break

    def load_marlin_config(self):
        # Load and apply settings
        try:
            marlin_config = marlin_config_manager.load_settings()
            self.apply_marlin_settings(marlin_config)
            self.log("[INFO] Marlin settings loaded and applied.")
        except Exception as e:
            self.log(f"[ERROR] Failed to load Marlin settings: {e}")


    def log(self, message):
        if self.log_widget:
            self.log_widget.append_log(message)
        else:
            logging.getLogger(__name__).info(str(message))

    # External command dispatch
    def send_to_x(self, gcode): self.x_motor_queue.put(gcode)
    def send_to_y(self, gcode): self.y_motor_queue.put(gcode)
    def send_to_aux(self, action): self.aux_queue.put(action)
    def send_to_control(self, gcode): self.control_queue.put(gcode)



    def apply_marlin_settings(self, settings: dict):
        if not self.connected:
            self.log("[ERROR] Cannot apply settings - no connection.")
            return

        # key: dictionary key (e.g. "motor_current", "feedrate", "steps_per_mm")
        # meta: metadata dictionary for the key
        for key, meta in MARLIN_COMMAND_MAP.items():
            if key not in settings: # Check whether key exists in settings
                continue

            value = settings[key]
            cmd = meta["cmd"] # Read the G-code command name from metadata, e.g. M906

            if "format" in meta: # Check whether metadata contains a "format" key.
                formatted = meta["format"](value) # Custom formatting (e.g. G1 F1500 or M204 P500 T500)
                self.send_command(f"{cmd} {formatted}\n")
                self.log(f"[GCODE] {cmd} {formatted}")
            # "type": "dict"
            elif meta.get("type") == "dict" and isinstance(value, dict):
                axes = meta.get("axes", "")
                parts = [f"{axis}{value[axis]}" for axis in axes if axis in value] # when values differ by axis
                if parts:
                    full = f"{cmd} {' '.join(parts)}"
                    self.send_command(full + "\n")
                    self.log(f"[GCODE] {full}")
            # "type": "value"
            elif meta.get("type") == "value" and isinstance(value, (int, float)):
                # Pl. motor_current â†’ M906 X800 Y800 ...
                axes = meta.get("axes", "")
                parts = [f"{axis}{value}" for axis in axes]  # when all axes use same value
                if parts:
                    full = f"{cmd} {' '.join(parts)}"
                    self.send_command(full + "\n")
                    self.log(f"[GCODE] {full}")


    def stop_threads(self):
        """Stop threads cleanly and close the connection."""
        try:
            self.send_command("M107\n") # D9 OFF
            time.sleep(0.05)  # short delay to ensure command is sent
            self.send_command("M0\n")  # Pause
            time.sleep(0.05)  # short delay to ensure command is sent
            self.send_command("M18\n")  # Motor kikapcs
            time.sleep(0.05)  # short delay to ensure command is sent
        except Exception as e:
            self.log(f"[WARN] Failed to send shutdown commands: {e}")


        self.running = False
        self.x_motor_queue.put("STOP")
        self.y_motor_queue.put("STOP")
        self.aux_queue.put("STOP")
        self.control_queue.put("STOP")

        try:
            self.x_thread.join(timeout=2)
            self.y_thread.join(timeout=2)
            self.aux_thread.join(timeout=2)
            self.control_thread.join(timeout=2)
            self.log("[INFO] Threads stopped successfully.")
        except Exception as e:
            self.log(f"[ERROR] Error occurred while stopping threads: {e}")

        # --- Disconnect ---
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                self.log("[INFO] Serial port closed cleanly.")
        except Exception as e:
            self.log(f"[ERROR] Failed to close port: {e}")

        self.ser = None
        self.set_connected(False)

        self.response_running = False
        if hasattr(self, "response_thread"):
            self.response_thread.join(timeout=2)
            self.log("[INFO] Response listener thread stopped.")


