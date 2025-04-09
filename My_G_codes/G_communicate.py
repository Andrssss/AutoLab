import threading
import time
import queue

class GCodeControl:
    def __init__(self, lock=None, serial_obj=None):
        self.serial = serial_obj
        self.lock = lock
        self.connected = False

        # Parancs sorok minden szálhoz
        self.x_motor_queue = queue.Queue()
        self.y_motor_queue = queue.Queue()
        self.aux_queue = queue.Queue()

        self.running = True

    def set_connected(self, connected):
        self.connected = connected
        print(f"Serial port connected - {self.connected}")

    def send_command(self, command, wait_for_completion=False):
        if self.connected:
            with self.lock:
                self.serial.write(command.encode('utf-8'))
            time.sleep(0.1)
            if wait_for_completion:
                with self.lock:
                    self.serial.write("M400 \n".encode('utf-8'))
                time.sleep(0.1)
                return self.wait_for_ok(timeout=5)
        else:
            print("send_command - not connected")

    def wait_for_ok(self, timeout=5):
        start_time = time.time()
        while True:
            with self.lock:
                response = self.serial.readline().decode('utf-8', errors='ignore').strip().lower()
            if "ok" in response:
                return response
            if time.time() - start_time > timeout:
                print("G wait_for_ok TIMEOUT")
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

        self.x_thread.join()
        self.y_thread.join()
        self.aux_thread.join()

    # 💡 Parancsokhoz tartozó logikák
    def set_aux_output(self):
        if(self.connected):
            for _ in range(3):
                self.send_command("M42 P58 S200 \n")
                self.send_command("M42 P58 S0 \n")
        else:
            print("start_threads - not connected")

    def query_endstops(self):
        if (self.connected):
            with self.lock:
                self.serial.write("M119 \n".encode('utf-8'))
            time.sleep(0.1)
            response = self.serial.read_all().decode('utf-8', errors='ignore')
            return response
        else:
            print("start_threads - not connected")

    def new_command(self, command: str):
        if (self.connected):
            # Új G-kód fogadása: irány szerint sorba állítja a megfelelő queue-ba.
            cmd_upper = command.upper()

            # Előfeldolgozás: eltávolítjuk a kommenteket, üres helyeket
            cmd_clean = cmd_upper.strip()

            if "G1" in cmd_clean or "G0" in cmd_clean:
                if "X" in cmd_clean and "Y" not in cmd_clean:
                    print("[DISPATCH] X_motor_queue ←", cmd_clean)
                    self.send_to_x.put(command)
                elif "Y" in cmd_clean and "X" not in cmd_clean:
                    print("[DISPATCH] Y_motor_queue ←", cmd_clean)
                    self.send_to_y.put(command)
                else:
                    print("[DISPATCH] AUX_queue (összetett vagy nem irányított) ←", cmd_clean)
                    self.send_aux.put(command)
            else:
                print("[DISPATCH] AUX_queue (nem mozgásparancs) ←", cmd_clean)
                self.send_aux.put(command)
        else:
            print("start_threads - not connected")


    # 💬 Külső parancsküldés
    def send_to_x(self, gcode): self.x_motor_queue.put(gcode)
    def send_to_y(self, gcode): self.y_motor_queue.put(gcode)
    def send_aux(self, action): self.aux_queue.put(action)

