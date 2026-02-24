import sys
import serial
import serial.tools.list_ports
import cv2
import yaml
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QHBoxLayout, QMessageBox, QMenu, QAction
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from File_managers import config_manager





class SettingsWidget(QWidget):
    def __init__(self, g_control, locks, camera_widget,available_cams, parent=None):
        super().__init__(parent)
        self.g_control = g_control
        #self.locks = locks
        self.camera_widget = camera_widget
        self.camera_widget.pause_camera()
        self.selected_port = None
        self.initUI()
        self.populate_camera_list()
        self.available_cams = available_cams
        cameraChanged = pyqtSignal(int)  # <- ez a signal fog szólni, ha kamera váltás történik

    def initUI(self):
        layout = QVBoxLayout()

        # Kamera kiválasztás
        self.combo_cameras = QComboBox()
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
        self.btn_select.setMenu(QMenu())  # Menü hozzáadása a gombhoz

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
        self.btn_apply.clicked.connect(self.emit_value_changed)
        self.btn_autoconnect.clicked.connect(self.autoconnect)
        self.btn_connect.clicked.connect(self.connect_selected_port)

        # Újratölti a portokat, amikor megnyitják a menüt
        self.btn_select.menu().aboutToShow.connect(self.populate_port_menu)

    def populate_port_menu(self):
        self.btn_select.menu().clear()
        ports = serial.tools.list_ports.comports()

        if not ports:
            no_ports_action = QAction("No ports", self)
            no_ports_action.setEnabled(False)
            self.btn_select.menu().addAction(no_ports_action)
            self.selected_port = None
            self.label_status.setText("Port kiválasztása: nincs elérhető")
            return

        for port in ports:
            action = QAction(f"{port.device} - {port.description}", self)
            action.triggered.connect(lambda checked, p=port.device: self.set_selected_port(p))
            self.btn_select.menu().addAction(action)

    # Kamera detektálás külön szálon
    def populate_camera_list(self):
        self.combo_cameras.clear()
        self.combo_cameras.addItem("Kamerák keresése...", -1)

        found = []
        for i in range(5):  
            try:
                cap = cv2.VideoCapture(i)
                if cap is not None and cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        found.append(i)
                    cap.release()
            except Exception as e:
                print(f"Kamera {i} hibás: {e}")

        self.on_cameras_scanned(found)

    def set_selected_port(self, port_name):
        self.selected_port = port_name
        self.label_status.setText(f"Kiválasztott port: {self.selected_port}")

    def on_cameras_scanned(self, cameras):
        self.combo_cameras.clear()
        self.available_cams = cameras
        if cameras:
            for cam in cameras:
                self.combo_cameras.addItem(f"Camera {cam}", cam)
            self.combo_cameras.setCurrentIndex(0)
        else:
            self.combo_cameras.addItem("No camera found", -1)

        # Itt már biztonságosan betölthetjük a YAML-t
        self.load_all_from_yaml()

    def emit_value_changed(self):
        self.save_all_to_yaml()
        self.input_value.clear()
        # Ablak bezárása
        self.close()

    def autoconnect(self):
        baud_rates = [250000, 125000, 500000]
        ports = serial.tools.list_ports.comports()

        if not ports:
            self.label_status.setText("Nem található soros eszköz.")
            return

        for port in ports:
            port_name = port.device
            for baud in baud_rates:
                try:
                    ser = serial.Serial(port_name, baud, timeout=1)
                    ser.write(b'\n')
                    response = ser.readline()

                    if response:
                        self.g_control.ser = ser
                        self.g_control.set_connected(True)
                        self.selected_port = port_name 
                        self.label_status.setText(f"Sikeres csatlakozás: {port_name} @ {baud} baud")
                        return
                    else:
                        ser.close()

                except Exception as e:
                    print(f"Hiba: {port_name} @ {baud} baud - {e}")

        self.label_status.setText("Nem sikerült csatlakozni egyetlen soros porthoz sem.")

    def show_port_list(self):
        ports = serial.tools.list_ports.comports()
        if not ports:
            QMessageBox.information(self, "Soros portok", "Nincs elérhető soros port.")
            self.selected_port = None
            self.label_status.setText("Port kiválasztása: nincs elérhető")
            return

        self.combo_ports = QComboBox()
        for port in ports:
            self.combo_ports.addItem(f"{port.device} - {port.description}", port.device)

        self.selected_port = self.combo_ports.itemData(0)
        self.label_status.setText(f"Kiválasztott port: {self.selected_port}")

    def connect_selected_port(self):
        if not self.selected_port:
            self.label_status.setText("Nincs kiválasztott port!")
            return
        self.g_control.set_connected(True)
        self.connect_to_port(self.selected_port)

    def connect_to_port(self, port_name):
        try:
            baud_rates = [250000, 125000, 500000]
            ser = serial.Serial(port_name, 250000, timeout=1)

            # Frissítjük a meglévő g_control objektumot
            self.g_control.ser = ser

            # Elindítjuk a szálakat a meglévő thread_control-ból
            #self.locks.gc = self.g_control
            #self.locks.lock_type = "G-code_lock"
            #self.locks.start_threads()
            self.g_control.set_connected(True)
            self.label_status.setText(f"Sikeres csatlakozás: {port_name}")

        except Exception as e:
            self.label_status.setText(f"Hiba: {str(e)}")

    def save_all_to_yaml(self, filepath="settings.yaml"):
        config_manager.update_settings({
            "camera_index": self.combo_cameras.currentData(),
            "selected_port": self.selected_port,
            "text_value": self.input_value.text()
        })
        self.camera_widget.select_camera_by_index(self.combo_cameras.currentData())




    def load_all_from_yaml(self, filepath="settings.yaml"):
        if not os.path.exists(filepath):
            print("settings.yaml nem létezik.")
            return

        try:
            with open(filepath, "r") as file:
                data = yaml.safe_load(file)

            # Kamera beállítás
            cam_idx = data.get("camera_index", -1)
            if cam_idx in self.available_cams:
                index = self.combo_cameras.findData(cam_idx)
                if index != -1:
                    self.combo_cameras.setCurrentIndex(index)

            # Szöveg
            text_val = data.get("text_value", "")
            self.input_value.setText(text_val)

            # Soros port
            self.selected_port = data.get("selected_port", None)
            if self.selected_port:
                self.label_status.setText(f"Korábban kiválasztott port: {self.selected_port}")

            print(f"Beállítások betöltve YAML-ből: {data}")

        except Exception as e:
            print(f"Hiba a YAML betöltés során: {e}")



    def closeEvent(self, event):
        # Ha az ablakot "X"-szel zárják be, itt NEM mentünk semmit.
        print("Beállítások ablak bezárva felhasználó által (X), mentés kihagyva.")
        self.camera_widget.resume_camera()
        event.accept()  # Engedélyezzük a bezárást
