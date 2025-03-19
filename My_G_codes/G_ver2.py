import time

class GCodeControl:
    def __init__(self, serial_obj, lock):
        """
        serial_obj: egy pySerial Serial objektum, pl. serial.Serial('COM6', 250000, timeout=1)
        lock: threading.Lock objektum a szinkronizált kommunikációhoz
        """
        self.serial = serial_obj
        self.lock = lock

    def send_command(self, command, wait_for_completion=False):
        """
        Küld egy G‑kód parancsot a soros porton keresztül.
        Ha wait_for_completion=True, az M400 parancsot is küldi, hogy megvárja a mozgás befejeződését.
        Az alapértelmezett, wait_for_completion=False esetén csak elküldi a parancsot (és röviden vár, hogy ne
        kerüljenek egymásra a soros üzenetek).
        """
        with self.lock:
            self.serial.write(command.encode('utf-8'))
        # Rövid késleltetés a parancs átviteléhez:
        time.sleep(0.1)
        if wait_for_completion:
            with self.lock:
                self.serial.write("M400 \n".encode('utf-8'))
            time.sleep(0.1)

    def control_x_motor(self):
        """Példa: X motor mozgatása. A mozgás végén várja a befejeződést."""
        self.send_command("G91 \n")  # Relatív mód
        self.send_command("G1 X2000 F15000 \n", wait_for_completion=True)
        self.send_command("G1 X-2000 F15000 \n", wait_for_completion=True)

    def set_aux_output(self):
        """
        Példa: Aux kimenetek ki-/bekapcsolása.
        Itt nem várunk semmire, azaz nem hívjuk az M400-et, így a printer azonnal
        végrehajtja a parancsokat, függetlenül attól, hogy a kimenet be- vagy kikapcsolódik-e.
        """
        for _ in range(3):
            self.send_command("M42 P58 S200 \n")  # Aux kimenet bekapcsolása
            self.send_command("M42 P58 S0 \n")    # Aux kimenet kikapcsolása

    def query_endstops(self):
        """
        Lekérdezi az endstopok állapotát az M119 paranccsal, majd visszaolvassa a soros porton érkező választ.
        """
        with self.lock:
            self.serial.write("M119 \n".encode('utf-8'))
        time.sleep(0.1)
        # Feltételezzük, hogy a pySerial read_all() visszaolvassa a választ
        response = self.serial.read_all().decode('utf-8')
        return response

# Teszt futtatás:
if __name__ == "__main__":
    print("Ez a GCodeControl modul tesztfuttatása.")
