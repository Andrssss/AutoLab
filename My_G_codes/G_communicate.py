import time

class GCodeControl:
    def __init__(self, serial_obj, lock):
        self.serial = serial_obj
        self.lock = lock

    def wait_for_ok(self, timeout=5):
        """
        Vár az "ok" visszajelzésre a soros porton.
        timeout: hány másodpercig várjon maximum.
        """
        start_time = time.time()
        while True:
            with self.lock:
                # Olvasunk egy sort a soros porton.
                response = self.serial.readline().decode('utf-8', errors='ignore').strip().lower()
            if "ok" in response:
                return response
            if time.time() - start_time > timeout:
                print("G wait_for_ok TIMEOUT")
                return None


    def send_command(self, command, wait_for_completion=False):
        """
        Küld egy G‑kód parancsot a soros porton keresztül.
        Ha wait_for_completion=True, az M400 parancsot is küldi, hogy megvárja a mozgás befejeződését,
        és az "ok" visszajelzést is figyeli.
        """
        with self.lock:
            self.serial.write(command.encode('utf-8'))
        # Rövid késleltetés a parancs átviteléhez:
        time.sleep(0.1)
        if wait_for_completion:
            with self.lock:
                self.serial.write("M400 \n".encode('utf-8'))
            time.sleep(0.1)
            # Várakozás az "ok" visszajelzésre.
            ok_response = self.wait_for_ok(timeout=5)
            if ok_response is None:
                print("Figyelmeztetés: Az 'ok' visszajelzés nem érkezett meg időn belül.")
            else:
                print("Visszajelzés: ", ok_response)

    def control_x_motor(self):
        """Példa: X motor mozgatása. A mozgás végén várja a befejeződést."""
        self.send_command("G91 \n")  # Relatív mód
        self.send_command("G1 X2000 F15000 \n", wait_for_completion=True)
        self.send_command("G1 X-2000 F15000 \n", wait_for_completion=True)

    def set_aux_output(self):
        """
        Példa: Aux kimenetek ki-/bekapcsolása.
        Itt nem várunk semmire, azaz nem hívjuk az M400-et, így a printer azonnal
        végrehajtja a parancsokat.
        """
        for _ in range(5):
            self.send_command("M42 P58 S200 \n")
            self.send_command("M42 P58 S0 \n")

    def query_endstops(self):
        """
        Lekérdezi az endstopok állapotát az M119 paranccsal, majd visszaolvassa a soros porton érkező választ.
        """
        with self.lock:
            self.serial.write("M119 \n".encode('utf-8'))
        time.sleep(0.1)
        response = self.serial.read_all().decode('utf-8', errors='ignore')
        return response

# Teszt futtatás:
if __name__ == "__main__":
    print("Ez a GCodeControl modul tesztfuttatása.")
