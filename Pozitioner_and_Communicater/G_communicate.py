import threading
import time
import queue
import serial  # pyserial
import serial.tools.list_ports
from File_managers import marlin_config_manager
from File_managers import config_manager
from Pozitioner_and_Communicater.gcode_presets import MARLIN_COMMAND_MAP


# Marlin doesn’t auto-calibrate steps → you set/adjust them with M92, test a move, measure, then refine.
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
        self.label_status = None  # ezt kívülről lehet beállítani (pl. a GUI-ból)
        self.log_widget = None  # Ezt majd kívülről beállítod a MainWindow-ban


        # Parancs sorok minden szálhoz
        self.x_motor_queue = queue.Queue()
        self.y_motor_queue = queue.Queue()
        self.aux_queue = queue.Queue()
        self.control_queue = queue.Queue()

        self.running = True

    def __del__(self):
        print("[INFO] GCodeControl destruktor meghívva")

        # Szálak leállítása, ha még futnak
        try:
            self.stop_threads()
            print("[INFO] Szálak leállítva")
        except Exception as e:
            print(f"[WARN] Szálak leállítása sikertelen: {e}")

        # Soros port bezárása
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                print("[INFO] Soros port bezárva")
        except Exception as e:
            print(f"[WARN] Nem sikerült bezárni a soros portot: {e}")

    def set_connected(self, connected):
        self.connected = connected
        print(f"Serial port connected - {self.connected}")



    def send_command(self, command, wait_for_completion=False):
        if not self.connected:
            print("send_command - not connected")
            return None

        # mindig küldjük ki
        if not command.endswith("\n"):
            command += "\n"

        if self.lock:
            with self.lock:
                self.ser.write(command.encode('utf-8'))
        else:
            self.ser.write(command.encode('utf-8'))

        time.sleep(0.05)

        if wait_for_completion:
            # csak ekkor küld M400-at és vár választ
            if self.lock:
                with self.lock:
                    self.ser.write(b"M400\n")
            else:
                self.ser.write(b"M400\n")

            time.sleep(0.05)
            return self.wait_for_ok(timeout=5)

        return None  # parancs kiment, de nem várunk rá




    def wait_for_ok(self, timeout=5):
        if not self.ser:
            print("[HIBA] Nincs érvényes soros kapcsolat (ser = None)")
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
                print("[HIBA] G-code válasz timeout (nem jött 'ok')")
                return None

    def worker_loop(self, q: queue.Queue, name: str):
        if self.connected:
            print(f"[{name}] szál elindult.")
            while self.running:
                try:
                    command = q.get(timeout=1)
                    if command == "STOP":
                        print(f"[{name}] szál leáll.")
                        break
                    if name in ("X_motor", "Y_motor"): # Csak itt várunk, mert a többi helyen nem küld RAMPS választ
                        print(f"[{name}] → {command}")
                        self.send_command(command, wait_for_completion=True)
                    elif name == "AUX":
                        # M42 vezérlés specifikusan
                        if command.startswith("M42"):
                            print(f"[AUX] M42 parancs: {command}")
                            self.send_command(command, wait_for_completion=False)
                    elif name == "CONTROL":
                        print(f"[CONTROL] → {command}")
                        self.send_command(command, wait_for_completion=False)
                except queue.Empty:
                    continue
        else:
            print(f"{name} - not connected")

    def start_threads(self):
        if (self.connected):
            """Szálak indítása: X_motor, Y_motor, AUX (egyéb funkciók)"""
            # Ne indíts új szálakat, ha már vannak futók
            if hasattr(self, 'x_thread') and self.x_thread.is_alive():
                self.log("[WARN] Szálak már futnak, újraindítás előtt le kell állítani őket.")
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
            print("start_threads - not connected")


    def set_lock(self, lock):
        self.lock = lock


    # Parancsokhoz tartozó logikák
    def set_aux_output(self):
        if(self.connected):
            for _ in range(3):
                self.send_command("M42 P58 S200 \n")
                self.send_command("M42 P58 S0 \n")
        else:
            print("start_threads - not connected")

    def query_endstops(self):
        if self.connected:
            if not self.ser:
                print("[HIBA] Nincs érvényes soros kapcsolat (ser = None)")
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
            print("[INFO] query_endstops - not connected")
            return ""

    def new_command(self, command: str):
        if self.connected:
            cmd_upper = command.upper().strip()

            if "G1" in cmd_upper or "G0" in cmd_upper:
                if "X" in cmd_upper and "Y" not in cmd_upper:
                    print("[DISPATCH] X_motor_queue ←", cmd_upper)
                    self.send_to_x(cmd_upper)
                elif "Y" in cmd_upper and "X" not in cmd_upper:
                    print("[DISPATCH] Y_motor_queue ←", cmd_upper)
                    self.send_to_y(cmd_upper)
                else:
                    print("[DISPATCH] CONTROL_queue (XY kevert vagy más) ←", cmd_upper)
                    self.send_to_control(cmd_upper)
            elif cmd_upper.startswith("M42"):
                print("[DISPATCH] AUX_queue (M42) ←", cmd_upper)
                self.send_to_aux(cmd_upper)
            else:
                print("[DISPATCH] CONTROL_queue ←", cmd_upper)
                self.send_to_control(cmd_upper)
        else:
            print("new_command - not connected")


    def autoconnect(self):
        self.log("[INFO] autoconnect() meghívva")

        # Meglévő szálak leállítása, ha futnak
        if hasattr(self, 'x_thread') and self.x_thread.is_alive():
            self.log("[INFO] Korábbi szálak leállítása reconnect előtt...")
            self.stop_threads()
            # újra engedélyezni kell a running flaget
            self.running = True


        # YAML-ból próbálunk először csatlakozni
        try:
            settings = config_manager.load_settings()
            preferred_port = settings.get("selected_port", None)
            preferred_baud = settings.get("baud", None)
        except Exception as e:
            self.log(f"[WARN] Nem sikerült betölteni a beállításokat: {e}")
            preferred_port = preferred_baud = None

        # Először próbáljuk az elmentett beállítást
        if preferred_port and preferred_baud:
            self.log(f"[INFO] Előző beállítás próbálása: {preferred_port} @ {preferred_baud}")
            try:
                ser = serial.Serial(preferred_port, preferred_baud, timeout=1)
                ser.write(b'\n')
                response = ser.readline()
                if response:
                    self.ser = ser
                    self.set_connected(True)
                    if self.label_status:
                        self.label_status.setText(f"Sikeres csatlakozás: {preferred_port} @ {preferred_baud} baud")
                    self.log(f"[INFO] Sikeres csatlakozás (elmentett): {preferred_port} @ {preferred_baud}")
                    self.start_threads()  # Itt indítjuk el a szálakat
                    self.start_response_listener()
                    self.load_marlin_config()
                    return
                else:
                    ser.close()
            except Exception as e:
                self.log(f"[HIBA] Elmentett port sikertelen: {e}")

        # Fallback: minden port/baud kipróbálása
        self.log("[INFO] Fallback: automatikus keresés indul...")
        baud_rates = [250000, 125000, 500000]
        ports = serial.tools.list_ports.comports()

        if not ports:
            if self.label_status:
                self.label_status.setText("Nem található soros eszköz.")
            self.log("[INFO] Nem található soros eszköz.")
            return

        for port in ports:
            port_name = port.device
            for baud in baud_rates:
                try:
                    self.log(f"[INFO] Próbálkozás: {port_name} @ {baud}")
                    ser = serial.Serial(port_name, baud, timeout=1)
                    ser.write(b'\n')
                    response = ser.readline()

                    if response:
                        self.ser = ser
                        self.set_connected(True)
                        if self.label_status:
                            self.label_status.setText(f"Sikeres csatlakozás: {port_name} @ {baud} baud")
                        self.log(f"[INFO] Sikeres csatlakozás: {port_name} @ {baud} baud")

                        # Mentsük a beállításokat
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
                    self.log(f"[HIBA] {port_name} @ {baud} - {e}")

        if self.label_status:
            self.label_status.setText("Nem sikerült csatlakozni egyetlen soros porthoz sem.")
        self.log("[INFO] Nem sikerült csatlakozni.")

    def start_response_listener(self):
        if hasattr(self, "response_thread") and self.response_thread.is_alive():
            self.log("[INFO] Válaszfigyelő szál már fut.")
            return

        self.response_running = True
        self.response_thread = threading.Thread(target=self.response_loop, daemon=True)
        self.response_thread.start()
        self.log("[INFO] Válaszfigyelő szál elindítva.")

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
                self.log(f"[HIBA] Válasz olvasási hiba: {e}")
                break

    def load_marlin_config(self):
        # Betöltjük és alkalmazzuk a beállításokat
        try:
            marlin_config = marlin_config_manager.load_settings()
            self.apply_marlin_settings(marlin_config)
            self.log("[INFO] Marlin beállítások betöltve és alkalmazva.")
        except Exception as e:
            self.log(f"[HIBA] Marlin beállítások betöltése sikertelen: {e}")


    def log(self, message):
        if self.log_widget:
            self.log_widget.append_log(message)
        else:
            print(message)

    # Külső parancsküldés
    def send_to_x(self, gcode): self.x_motor_queue.put(gcode)
    def send_to_y(self, gcode): self.y_motor_queue.put(gcode)
    def send_to_aux(self, action): self.aux_queue.put(action)
    def send_to_control(self, gcode): self.control_queue.put(gcode)



    def apply_marlin_settings(self, settings: dict):
        if not self.connected:
            self.log("[HIBA] Nem lehet beállításokat alkalmazni – nincs kapcsolat.")
            return

        # key: a szótár kulcsa (pl. "motor_current", "feedrate", "steps_per_mm")
        # meta: a kulcshoz tartozó érték, ami egy további szótár
        for key, meta in MARLIN_COMMAND_MAP.items():
            if key not in settings: # Ellenőrzi, hogy szerepel-e a settings-ben
                continue

            value = settings[key]
            cmd = meta["cmd"] # kiolvassa az adott konfigurációhoz tartozó G-code parancs nevét a meta szótárból. PL.: M906

            if "format" in meta: # ellenőrzi, hogy a meta nevű szótár (dictionary) tartalmazza-e a "format" kulcsot.
                formatted = meta["format"](value) # Egyedi formázás (pl. G1 F1500 vagy M204 P500 T500)
                self.send_command(f"{cmd} {formatted}\n")
                self.log(f"[GCODE] {cmd} {formatted}")
            # "type": "dict"
            elif meta.get("type") == "dict" and isinstance(value, dict):
                axes = meta.get("axes", "")
                parts = [f"{axis}{value[axis]}" for axis in axes if axis in value] # ha tengelyenként eltérő értékeket tartalmaz.
                if parts:
                    full = f"{cmd} {' '.join(parts)}"
                    self.send_command(full + "\n")
                    self.log(f"[GCODE] {full}")
            # "type": "value"
            elif meta.get("type") == "value" and isinstance(value, (int, float)):
                # Pl. motor_current → M906 X800 Y800 ...
                axes = meta.get("axes", "")
                parts = [f"{axis}{value}" for axis in axes]  # ha minden tengelyre ugyanaz
                if parts:
                    full = f"{cmd} {' '.join(parts)}"
                    self.send_command(full + "\n")
                    self.log(f"[GCODE] {full}")


    def stop_threads(self):
        """Szálak szabályos leállítása ÉS kapcsolatbontás"""
        try:
            self.send_command("M107\n") # D9 OFF
            time.sleep(0.05)  # kis szünet, hogy biztosan kimenjen
            self.send_command("M0\n")  # Pause
            time.sleep(0.05)  # kis szünet, hogy biztosan kimenjen
            self.send_command("M18\n")  # Motor kikapcs
            time.sleep(0.05)  # kis szünet, hogy biztosan kimenjen
        except Exception as e:
            print(f"[WARN] Leállító parancsok küldése nem sikerült: {e}")


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
            self.log("[INFO] Szálak sikeresen leálltak.")
        except Exception as e:
            self.log(f"[HIBA] Szálak leállítása közben hiba történt: {e}")

        # --- Kapcsolat bontás ---
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                self.log("[INFO] Soros port szabályosan bezárva.")
        except Exception as e:
            self.log(f"[HIBA] Port lezárása nem sikerült: {e}")

        self.ser = None
        self.set_connected(False)

        self.response_running = False
        if hasattr(self, "response_thread"):
            self.response_thread.join(timeout=2)
            self.log("[INFO] Válaszfigyelő szál leállítva.")

