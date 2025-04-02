import sys
import serial
import serial.tools.list_ports
import cv2

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings


# Példa dummy osztályok – helyettesítsd saját implementációddal!
class GCodeControl:
    def __init__(self, ser):
        self.ser = ser


class ThreadControl:
    def __init__(self, gcode_control, lock_type):
        self.gc = gcode_control
        self.lock_type = lock_type

    def start_threads(self):
        print(f"Szálak elindítva lock-kal: {self.lock_type}")


lock_map = {
    "G-code_lock": None,
    "Camera_lock": None,
    "common": None
}


class SettingsWidget(QWidget):
    cameraSelected = pyqtSignal(int)
    valueChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.available_cams = []
        self.selected_port = None
        self.initUI()
        self.settings = QSettings("MyCompany", "MyApp")
        self.cameraSelected.connect(self.save_camera_to_settings)
        self.valueChanged.connect(self.save_text_to_settings)

    def initUI(self):
        layout = QVBoxLayout()

        # Kamera kiválasztás
        self.combo_cameras = QComboBox()
        self.populate_camera_list()
        layout.addWidget(QLabel("Kamera kiválasztása:"))
        layout.addWidget(self.combo_cameras)

        # Egyedi érték
        layout.addWidget(QLabel("Állítsd be az értéket:"))
        self.input_value = QLineEdit()
        self.input_value.setPlaceholderText("Pl. új érték")
        layout.addWidget(self.input_value)



        # USB rész
        layout.addWidget(QLabel("Connect to device:"))

        btn_layout = QHBoxLayout()
        self.btn_autoconnect = QPushButton("Autoconnect")
        self.btn_select = QPushButton("Select")
        self.btn_connect = QPushButton("Connect")

        btn_layout.addWidget(self.btn_autoconnect)
        btn_layout.addWidget(self.btn_select)
        btn_layout.addWidget(self.btn_connect)
        layout.addLayout(btn_layout)


        # Státusz kijelző
        self.label_status = QLabel("")
        self.label_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label_status)

        self.setLayout(layout)

        self.btn_apply = QPushButton("Alkalmaz")
        layout.addWidget(self.btn_apply)


        # Kapcsolások
        self.combo_cameras.currentIndexChanged.connect(self.emit_camera_selected)
        self.btn_apply.clicked.connect(self.emit_value_changed)
        self.btn_autoconnect.clicked.connect(self.autoconnect)
        self.btn_select.clicked.connect(self.show_port_list)
        self.btn_connect.clicked.connect(self.connect_selected_port)

    def populate_camera_list(self):
        self.combo_cameras.clear()
        self.available_cams = []
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                self.combo_cameras.addItem(f"Camera {i}", i)
                self.available_cams.append(i)
                cap.release()
        if not self.available_cams:
            self.combo_cameras.addItem("No camera found", -1)

    def emit_camera_selected(self, index):
        camera_index = self.combo_cameras.itemData(index)
        if camera_index != -1:
            self.cameraSelected.emit(camera_index)
            self.settings.setValue("selected_camera", camera_index)
            print(f"Kamera index {camera_index} mentve a regiszterbe.")

    def emit_value_changed(self):
        value = self.input_value.text()
        self.settings.setValue("saved_text", value)  # mentés minden esetben
        self.valueChanged.emit(value)
        print(f"Szöveg '{value}' mentve a regiszterbe.")
        self.input_value.clear()

    def autoconnect(self):
        baud_rates = [250000, 125000, 500000]  # sorrendben próbáljuk
        ports = serial.tools.list_ports.comports()

        if not ports:
            self.label_status.setText("Nem található soros eszköz.")
            return

        for port in ports:
            port_name = port.device
            for baud in baud_rates:
                try:
                    with serial.Serial(port_name, baud, timeout=1) as ser:
                        ser.write(b'\n')  # Teszt parancs, szükség szerint változtasd
                        response = ser.readline()

                        if response:
                            # Sikeres csatlakozás
                            gcode_control = GCodeControl(ser)
                            lock_type = "G-code_lock"
                            thread_ctrl = ThreadControl(gcode_control, lock_type)
                            thread_ctrl.start_threads()

                            self.label_status.setText(
                                f"Sikeres csatlakozás: {port_name} @ {baud} baud"
                            )
                            return  # Sikeres csatlakozás után kilép

                except Exception as e:
                    print(f"Hiba: {port_name} @ {baud} baud - {e}")

        # Ha minden próbálkozás sikertelen
        self.label_status.setText("Nem sikerült csatlakozni egyetlen soros porthoz sem.")




    def show_port_list(self):
        ports = serial.tools.list_ports.comports()
        if not ports:
            QMessageBox.information(self, "Soros portok", "Nincs elérhető soros port.")
            self.selected_port = None
            self.label_status.setText("Port kiválasztása: nincs elérhető")
            return

        # Lista popup helyett comboboxból választás
        self.combo_ports = QComboBox()
        for port in ports:
            self.combo_ports.addItem(f"{port.device} - {port.description}", port.device)

        # Egyszerű popup dialógus helyett: automatikus kiválasztás
        self.selected_port = self.combo_ports.itemData(0)
        self.label_status.setText(f"Kiválasztott port: {self.selected_port}")

    def connect_selected_port(self):
        if not self.selected_port:
            self.label_status.setText("Nincs kiválasztott port!")
            return
        self.connect_to_port(self.selected_port)

    def connect_to_port(self, port_name):
        try:
            ser = serial.Serial(port_name, 250000, timeout=1)
            gcode_control = GCodeControl(ser)
            lock_type = "G-code_lock"
            thread_ctrl = ThreadControl(gcode_control, lock_type)
            thread_ctrl.start_threads()

            self.label_status.setText(f"Sikeres csatlakozás: {port_name}")
        except Exception as e:
            self.label_status.setText(f"Hiba: {str(e)}")

    def save_camera_to_settings(self, camera_index):
        self.settings.setValue("selected_camera_from_signal", camera_index)
        print(f"Kamera {camera_index} regiszterbe mentve (signal-ból)!")

    def save_text_to_settings(self, text):
        self.settings.setValue("text_from_signal", text)
        print(f"Szöveg '{text}' regiszterbe mentve (signal-ból)!")