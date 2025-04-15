import threading
import time
import queue
import serial  # pyserial
import serial.tools.list_ports

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
        if self.connected:
            if self.lock:
                with self.lock:
                    self.ser.write(command.encode('utf-8'))  # 🔁 EZ!
            else:
                self.ser.write(command.encode('utf-8'))

            time.sleep(0.1)

            if wait_for_completion:
                if self.lock:
                    with self.lock:
                        self.ser.write("M400\n".encode('utf-8'))
                else:
                    self.ser.write("M400\n".encode('utf-8'))
                time.sleep(0.1)
                return self.wait_for_ok(timeout=5)
        else:
            print("send_command - not connected")

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
                return response

            if time.time() - start_time > timeout:
                print("[HIBA] G-code válasz timeout (nem jött 'ok')")
                return None

    def worker_loop(self, q: queue.Queue, name: str):
        """Általános szálkezelő, ami feldolgozza a queue-ban érkező parancsokat"""
        if(self.connected):
            print(f"[{name}] szál elindult.")
            while self.running:
                try:
                    command = q.get(timeout=1)
                    if command == "STOP":
                        print(f"[{name}] szál leáll.")
                        break
                    if name in ("X_motor", "Y_motor"):
                        print(f"[{name}] → {command}")
                        self.send_command(command, wait_for_completion=True)
                    else:
                        if command == "set_aux":
                            self.set_aux_output()
                        elif command == "get_info":
                            info = self.query_endstops()
                            print(f"[AUX] Endstop info:\n{info}")
                        elif command == "set_something":
                            self.send_command("M42 P5 S255\n")  # Példa
                except queue.Empty:
                    continue
        else:
            print("worker_loop - not connected")

    def start_threads(self):
        if (self.connected):
            """Szálak indítása: X_motor, Y_motor, AUX (egyéb funkciók)"""
            self.x_thread = threading.Thread(target=self.worker_loop, args=(self.x_motor_queue, "X_motor"))
            self.y_thread = threading.Thread(target=self.worker_loop, args=(self.y_motor_queue, "Y_motor"))
            self.aux_thread = threading.Thread(target=self.worker_loop, args=(self.aux_queue, "AUX"))

            self.x_thread.start()
            self.y_thread.start()
            self.aux_thread.start()
        else:
            print("start_threads - not connected")


    def set_lock(self, lock):
        self.lock = lock

    def stop_threads(self):
        """Szálak szabályos leállítása"""
        self.running = False
        self.x_motor_queue.put("STOP")
        self.y_motor_queue.put("STOP")
        self.aux_queue.put("STOP")

        try:
            self.x_thread.join(timeout=2)
            self.y_thread.join(timeout=2)
            self.aux_thread.join(timeout=2)
            print("[INFO] Szálak sikeresen leálltak.")
        except Exception as e:
            print(f"[HIBA] Szálak leállítása közben hiba történt: {e}")

    # 💡 Parancsokhoz tartozó logikák
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
        if (self.connected):
            # Új G-kód fogadása: irány szerint sorba állítja a megfelelő queue-ba.
            cmd_upper = command.upper()

            # Előfeldolgozás: eltávolítjuk a kommenteket, üres helyeket
            cmd_clean = cmd_upper.strip()

            if "G1" in cmd_clean or "G0" in cmd_clean:
                if "X" in cmd_clean and "Y" not in cmd_clean:
                    print("[DISPATCH] X_motor_queue ←", cmd_clean)
                    self.send_to_x(cmd_clean)
                elif "Y" in cmd_clean and "X" not in cmd_clean:
                    print("[DISPATCH] Y_motor_queue ←", cmd_clean)
                    self.send_to_y(cmd_clean)
                else:
                    print("[DISPATCH] AUX_queue ←", cmd_clean)
                    self.send_aux(cmd_clean)
            else:
                print("[DISPATCH] AUX_queue (nem mozgásparancs) ←", cmd_clean)
                self.send_aux(cmd_clean)
        else:
            print("start_threads - not connected")

    def autoconnect(self):
        self.log("[INFO] autoconnect() meghívva")

        # YAML-ból próbálunk először csatlakozni
        try:
            from file_managers import config_manager
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
                    self.start_threads()  # 🔥 Itt indítjuk el a szálakat
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

                        # 🔐 Mentsük a beállításokat
                        config_manager.update_settings({
                            "selected_port": port_name,
                            "baud": baud
                        })

                        self.start_threads()  # 🔥 Itt is indítjuk a szálakat
                        return
                    else:
                        ser.close()

                except Exception as e:
                    self.log(f"[HIBA] {port_name} @ {baud} - {e}")

        if self.label_status:
            self.label_status.setText("Nem sikerült csatlakozni egyetlen soros porthoz sem.")
        self.log("[INFO] Nem sikerült csatlakozni.")

    def log(self, message):
        if self.log_widget:
            self.log_widget.append_log(message)
        else:
            print(message)

    # 💬 Külső parancsküldés
    def send_to_x(self, gcode): self.x_motor_queue.put(gcode)
    def send_to_y(self, gcode): self.y_motor_queue.put(gcode)
    def send_aux(self, action): self.aux_queue.put(action)

