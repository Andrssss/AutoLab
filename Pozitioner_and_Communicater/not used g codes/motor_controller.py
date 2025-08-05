import time # File jó linux-on is
import serial
import re
#from Pozitioner_and_Communicater.trigger import Endstop

class MotorController:
    def __init__(self, port, baudrate=250000, timeout=1):
        self.ser = serial.Serial(port, 250000, timeout=timeout)
        time.sleep(2)  # várakozás a kapcsolat stabilizálására
        # Jelenlegi pozíciók (relatív mód esetén ezek összeadódnak)
        self.current_position = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        # Endstop objektumok az egyes tengelyekhez
        self.endstops = {
            #'x_min': Endstop('x', 'min'),
            #'x_max': Endstop('x', 'max'),
            #'y_min': Endstop('y', 'min'),
            #'y_max': Endstop('y', 'max'),
            #'z_min': Endstop('z', 'min'),
            #'z_max': Endstop('z', 'max')
        }

    def close(self):
        self.ser.close()

    def parse_axes(self, cmd: str) -> dict:
        """
        Kivonatolja a parancsban szereplő tengelymozgásokat,
        például {'x': 500.0, 'y': -200.0}.
        """
        axes = {}
        for axis in ['X', 'Y', 'Z']:
            pattern = r'%s(-?\d+\.?\d*)' % axis
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                try:
                    axes[axis.lower()] = float(match.group(1))
                except ValueError:
                    pass
        return axes

    def modify_command(self, cmd: str) -> str:
        """
        A parancsban szereplő tengelymozgásokat úgy módosítja,
        hogy ha egy adott tengelyre tiltott mozgás irányt kérünk:
         - Ha pozitív mozgás (delta > 0) esetén a MAX endstop triggerelve van,
           akkor a pozitív mozgást eltiltja (delta = 0).
         - Ha negatív mozgás (delta < 0) esetén a MIN endstop triggerelve van,
           akkor a negatív mozgást eltiltja.
        """
        axes = self.parse_axes(cmd)
        modified = False
        for axis, delta in axes.items():
            if delta > 0:
                if self.endstops[f"{axis}_max"].is_triggered(self.ser):
                    print(f"{axis.upper()}_MAX endstop triggerelve! Pozitív mozgás blokkolva.")
                    axes[axis] = 0.0
                    modified = True
            elif delta < 0:
                if self.endstops[f"{axis}_min"].is_triggered(self.ser):
                    print(f"{axis.upper()}_MIN endstop triggerelve! Negatív mozgás blokkolva.")
                    axes[axis] = 0.0
                    modified = True

        if modified:
            feed_match = re.search(r'F(-?\d+\.?\d*)', cmd, re.IGNORECASE)
            feed_str = f" F{feed_match.group(1)}" if feed_match else ""
            cmd_type_match = re.search(r'^(G0|G1)', cmd, re.IGNORECASE)
            cmd_type = cmd_type_match.group(1) if cmd_type_match else "G1"
            new_cmd = cmd_type
            for axis in ['x', 'y', 'z']:
                if axis in axes:
                    new_cmd += f" {axis.upper()}{axes[axis]}"
            new_cmd += feed_str + "\n"
            print("Módosított parancs:", new_cmd.strip())
            return new_cmd
        else:
            return cmd

    def send_command(self, cmd: str):
        """
        A parancs elküldése a firmware-nek a módosítás után, a válasz feldolgozása,
        és az aktuális pozíció frissítése.
        """
        cmd_to_send = self.modify_command(cmd)
        print("Küldött parancs:", cmd_to_send.strip())
        self.ser.write(cmd_to_send.encode())
        time.sleep(0.1)

        response_start = time.time()
        while True:
            if self.ser.in_waiting:
                line = self.ser.readline().decode('ascii', errors='ignore').strip()
                if line:
                    print("Firmware válasz:", line)
                    if line.lower().startswith("ok"):
                        break
            if time.time() - response_start > 5:
                print("Időtúllépés a válaszban.")
                break
            time.sleep(0.1)

        axes = self.parse_axes(cmd_to_send)
        for axis, delta in axes.items():
            self.current_position[axis] += delta
