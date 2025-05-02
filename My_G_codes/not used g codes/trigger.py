import time # File jó linux-on is


class Endstop:
    def __init__(self, axis: str, direction: str):
        """
        axis: 'x', 'y' vagy 'z'
        direction: 'min' vagy 'max'
        """
        self.axis = axis.lower()
        self.direction = direction.lower()
        self.identifier = f"{self.axis}_{self.direction}"

    def is_triggered(self, ser) -> bool:
        """
        Lekéri az endstop státuszt (M119 parancs) és ellenőrzi,
        hogy az adott tengelyhez tartozó endstop triggerelve van-e.
        Például: "x_min: TRIGGERED"
        """
        ser.write("M119\n".encode())
        time.sleep(0.2)  # rövid várakozás a válaszra
        while ser.in_waiting:
            line = ser.readline().decode('ascii', errors='ignore').strip()
            # Ellenőrizzük, hogy a válasz tartalmazza-e az adott endstop állapotát
            if self.identifier in line.lower() and "triggered" in line.lower():
                return True
        return False
