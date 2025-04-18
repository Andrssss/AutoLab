import serial
import time
import platform

# ========== KONFIG ==========
PORT = 'COM6' if platform.system() == 'Windows' else '/dev/ttyUSB0'
BAUDRATE = 250000
Z_OFFSET_VALUE = -1.35
USE_M851 = True  # Állítsd False-ra, ha a nyomtató nem támogatja az M851-et
# =============================

def send_command(ser, command, wait=0.3):
    print(f">>> {command}")
    ser.write((command + '\n').encode())
    time.sleep(wait)
    while ser.in_waiting:
        line = ser.readline().decode(errors='ignore').strip()
        if line:
            print(line)

def main():
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=2)
        time.sleep(2)  # várunk, hogy felálljon a kapcsolat
        ser.reset_input_buffer()

        print("[INFO] Kapcsolódva a nyomtatóhoz.")

        send_command(ser, 'M155 S0')  # disable temp reporting, ha aktív
        send_command(ser, 'M115')     # firmware info
        send_command(ser, 'M503')     # aktuális beállítások kiíratása

        # ========== Z OFFSET BEÁLLÍTÁS ==========
        if USE_M851:
            send_command(ser, f'M851 Z{Z_OFFSET_VALUE:.2f}')
        else:
            send_command(ser, f'M206 Z{Z_OFFSET_VALUE:.2f}')

        # ========== MENTÉS ==========
        send_command(ser, 'M500')  # mentés EEPROM-ba
        send_command(ser, 'M503')  # új értékek lekérdezése

        ser.close()
        print("[INFO] Kész.")
    except serial.SerialException as e:
        print(f"[HIBA] Nem sikerült csatlakozni: {e}")
    except Exception as ex:
        print(f"[HIBA] Általános hiba: {ex}")

if __name__ == "__main__":
    main()
