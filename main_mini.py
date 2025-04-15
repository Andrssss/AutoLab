import serial
import time

def main():
    try:
        print("[INFO] Soros port nyitása: COM6 @ 250000 baud")
        ser = serial.Serial('COM6', 250000, timeout=2)

        time.sleep(2)  # Arduino/firmware reset miatt ajánlott kis várakozás

        command = "G1 X100 F3000\n"
        print(f"[SEND] {command.strip()}")
        ser.write(command.encode('utf-8'))

        # Várjuk a választ
        time.sleep(0.2)
        response = ser.read_all().decode('utf-8', errors='ignore')
        print(f"[RECEIVED] {response.strip()}")

        ser.close()
        print("[INFO] Port bezárva.")

    except serial.SerialException as e:
        print(f"[ERROR] Nem sikerült megnyitni a portot: {e}")

if __name__ == "__main__":
    main()
