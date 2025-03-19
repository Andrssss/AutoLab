import sys
import serial
from threading import Lock

from My_G_codes.G_code_control import GCodeControl
from THREADS.thread_control import ThreadControl


def main():
    # Inicializáljuk a soros kommunikációt a megfelelő COM porttal
    try:
        ser = serial.Serial('COM6', 250000, timeout=1)
    except Exception as e:
        print(f"Hiba a soros port megnyitásakor: {e}")
        sys.exit(1)

    lock = Lock()
    gcode_control = GCodeControl(ser, lock)

    thread_ctrl = ThreadControl(gcode_control)
    thread_ctrl.start_threads()

    # Végül zárjuk a soros portot
    ser.close()


if __name__ == "__main__":
    main()
