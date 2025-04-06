import threading
from threading import Lock

# Előre definiált zárolások
lock_map = {
    "G-code_lock": Lock(),
    "Camera_lock": Lock(),
    "common": Lock()
}

class ThreadControl:
    def __init__(self,  gcode_control=None, lock_type="common"):
        """
        gcode_control: egy GCodeControl objektum
        lock_type: string, amely meghatározza a lock típusát (pl. "G-code_lock")
        """
        if lock_type not in lock_map:
            raise ValueError(f"Ismeretlen lock típus: {lock_type}")

        #self.lock = lock_map[lock_type]  # A megfelelő lock kiválasztása
        #self.gcode_control = gcode_control
        #self.gcode_control.set_lock(self.lock)  # A lock továbbadása az objektumnak

    def start_threads(self):
        """Elindítja a motorvezérlési parancsokhoz tartozó szálakat."""
        x_motor_thread = threading.Thread(target=self.gcode_control.control_x_motor)
        aux_thread = threading.Thread(target=self.gcode_control.set_aux_output)

        x_motor_thread.start()
        aux_thread.start()

        x_motor_thread.join()
        aux_thread.join()

if __name__ == "__main__":
    print("Ez a thread_control modul tesztfuttatása.")
