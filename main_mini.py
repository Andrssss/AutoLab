import serial
import time

def main():
    try:
        #  todo
        print("szöveg")
    except serial.SerialException as e:
        print(f"[ERROR] Nem valami: {e}")

if __name__ == "__main__":
    main()
