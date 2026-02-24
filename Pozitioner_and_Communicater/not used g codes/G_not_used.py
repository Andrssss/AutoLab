import time  # File jó linux-on is

class GCodeControl:
    def __init__(self, serial_obj, lock):
        """
        serial_obj: egy pySerial Serial objektum, pl. serial.Serial('COM6', 250000, timeout=1)
        lock: threading.Lock objektum a szinkronizált kommunikációhoz
        """
        self.serial = serial_obj
        self.lock = lock

    def send_command(self, command):
        """Küld egy G‑kód parancsot a soros porton keresztül, majd 0.1 másodpercet vár."""
        with self.lock:
            self.serial.write(command.encode('utf-8'))
        time.sleep(0.1)

    def control_x_motor(self):
        """Példa: X motor mozgatása."""
        self.send_command("G91 \n")  # Relatív mód
        self.send_command("G1 X2000 F15000 \n")
        self.send_command("G1 X-500 F15000 \n")

    def set_aux_output(self):
        """Példa: Aux kimenetek ki/be kapcsolása."""
        for _ in range(3):
            self.send_command("M42 P58 S200 \n")
            self.send_command("M42 P58 S0 \n")

# Ha önállóan akarod futtatni tesztelve:
if __name__ == "__main__":
    print("Ez a G_code_control modul tesztfuttatása.")
