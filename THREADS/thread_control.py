import threading

class ThreadControl:
    def __init__(self, gcode_control):
        """
        gcode_control: egy GCodeControl objektum, melynek metódusait párhuzamosan szeretnénk futtatni.
        """
        self.gcode_control = gcode_control

    def start_threads(self):
        """Elindítja a motorvezérlési parancsokhoz tartozó szálakat."""
        # Szál az X motor mozgatásához
        x_motor_thread = threading.Thread(target=self.gcode_control.control_x_motor)
        # Szál az aux kimenetek vezérléséhez
        aux_thread = threading.Thread(target=self.gcode_control.set_aux_output)

        # Szálak indítása
        x_motor_thread.start()
        aux_thread.start()

        # Megvárjuk, amíg mindkét szál befejeződik
        x_motor_thread.join()
        aux_thread.join()

if __name__ == "__main__":
    print("Ez a thread_control modul tesztfuttatása.")
