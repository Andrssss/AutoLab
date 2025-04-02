import sys
import serial
from My_G_codes.G_not_used import GCodeControl
from THREADS.thread_control import ThreadControl

def main():
    if sys.platform.startswith('win'):
        port_name = 'COM6'
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        port_name = '/dev/ttyUSB0'
    else:
        print(f"Nem támogatott platform: {sys.platform}")
        sys.exit(1)



    try:
        ser = serial.Serial(port_name, 250000, timeout=1)
    except Exception as e:
        print(f"Hiba a soros port megnyitásakor: {e}")
        sys.exit(1)



    # GCodeControl objektum létrehozása és szál elindítása.
    gcode_control = GCodeControl(ser)

    # "G-code_lock": Lock(),
    # "Camera_lock": Lock(),
    # "common":      Lock()
    lock_type = "G-code_lock"  # Változtathatod pl. "Camera_lock" vagy "common"-ra
    thread_ctrl = ThreadControl(gcode_control, lock_type)
    thread_ctrl.start_threads()


    ser.close()
if __name__ == "__main__":
    main()
