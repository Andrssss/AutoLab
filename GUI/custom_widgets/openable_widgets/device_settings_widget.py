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
    def __init__(self, g_control, camera_widget, available_cams, parent=None):
        super().__init__(parent)
        self.g_control = g_control
        self.camera_widget = camera_widget
        self.camera_widget.pause_camera()
        self.selected_port = None
        self.initUI()
        self.populate_camera_list()
        self.available_cams = available_cams
        cameraChanged = pyqtSignal(int)  # <- emitted when camera selection changes

    def initUI(self):
        layout = QVBoxLayout()

        # Camera selection
        self.combo_cameras = QComboBox()
        layout.addWidget(QLabel("Select camera:"))
        layout.addWidget(self.combo_cameras)

        # Custom value
        layout.addWidget(QLabel("Set value:"))
        self.input_value = QLineEdit()
        self.input_value.setPlaceholderText("e.g. new value")
        layout.addWidget(self.input_value)

        # USB section
        layout.addWidget(QLabel("Connect to device:"))
        btn_layout = QHBoxLayout()
        self.btn_autoconnect = QPushButton("Autoconnect")

        self.btn_select = QPushButton("Select")
        self.btn_select.setMenu(QMenu())  # attach menu to button

        self.btn_connect = QPushButton("Connect")
        btn_layout.addWidget(self.btn_autoconnect)
        btn_layout.addWidget(self.btn_select)
        btn_layout.addWidget(self.btn_connect)
        layout.addLayout(btn_layout)

        # Status label
        self.label_status = QLabel("")
        self.label_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label_status)

        self.setLayout(layout)

        self.btn_apply = QPushButton("Apply")
        layout.addWidget(self.btn_apply)

        # Connections
        self.btn_apply.clicked.connect(self.emit_value_changed)
        self.btn_autoconnect.clicked.connect(self.autoconnect)
        self.btn_connect.clicked.connect(self.connect_selected_port)

        # Reload ports when menu opens
        self.btn_select.menu().aboutToShow.connect(self.populate_port_menu)

    def populate_port_menu(self):
        self.btn_select.menu().clear()
        ports = serial.tools.list_ports.comports()

        if not ports:
            no_ports_action = QAction("No ports", self)
            no_ports_action.setEnabled(False)
            self.btn_select.menu().addAction(no_ports_action)
            self.selected_port = None
            self.label_status.setText("Port selection: none available")
            return

        for port in ports:
            action = QAction(f"{port.device} - {port.description}", self)
            action.triggered.connect(lambda checked, p=port.device: self.set_selected_port(p))
            self.btn_select.menu().addAction(action)

    # Camera detection on a separate thread
    def populate_camera_list(self):
        self.combo_cameras.clear()
        self.combo_cameras.addItem("Searching for cameras...", -1)

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
                print(f"Camera {i} failed: {e}")

        self.on_cameras_scanned(found)

    def set_selected_port(self, port_name):
        self.selected_port = port_name
        self.label_status.setText(f"Selected port: {self.selected_port}")

    def on_cameras_scanned(self, cameras):
        self.combo_cameras.clear()
        self.available_cams = cameras
        if cameras:
            for cam in cameras:
                self.combo_cameras.addItem(f"Camera {cam}", cam)
            self.combo_cameras.setCurrentIndex(0)
        else:
            self.combo_cameras.addItem("No camera found", -1)

        # Safe to load YAML here
        self.load_all_from_yaml()

    def emit_value_changed(self):
        self.save_all_to_yaml()
        self.input_value.clear()
        # Close window
        self.close()

    def autoconnect(self):
        baud_rates = [250000, 125000, 500000]
        ports = serial.tools.list_ports.comports()

        if not ports:
            self.label_status.setText("No serial device found.")
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
                        self.label_status.setText(f"Connected successfully: {port_name} @ {baud} baud")
                        return
                    else:
                        ser.close()

                except Exception as e:
                    print(f"Error: {port_name} @ {baud} baud - {e}")

        self.label_status.setText("Failed to connect to any serial port.")

    def show_port_list(self):
        ports = serial.tools.list_ports.comports()
        if not ports:
            QMessageBox.information(self, "Serial ports", "No serial ports available.")
            self.selected_port = None
            self.label_status.setText("Port selection: none available")
            return

        self.combo_ports = QComboBox()
        for port in ports:
            self.combo_ports.addItem(f"{port.device} - {port.description}", port.device)

        self.selected_port = self.combo_ports.itemData(0)
        self.label_status.setText(f"Selected port: {self.selected_port}")

    def connect_selected_port(self):
        if not self.selected_port:
            self.label_status.setText("No port selected!")
            return
        self.g_control.set_connected(True)
        self.connect_to_port(self.selected_port)

    def connect_to_port(self, port_name):
        try:
            baud_rates = [250000, 125000, 500000]
            ser = serial.Serial(port_name, 250000, timeout=1)

            # Update existing g_control object
            self.g_control.ser = ser

            # Start threads from existing thread control
            self.g_control.set_connected(True)
            self.label_status.setText(f"Connected successfully: {port_name}")

        except Exception as e:
            self.label_status.setText(f"Error: {str(e)}")

    def save_all_to_yaml(self, filepath="settings.yaml"):
        config_manager.update_settings({
            "camera_index": self.combo_cameras.currentData(),
            "selected_port": self.selected_port,
            "text_value": self.input_value.text()
        })
        self.camera_widget.select_camera_by_index(self.combo_cameras.currentData())




    def load_all_from_yaml(self, filepath="settings.yaml"):
        if not os.path.exists(filepath):
            print("settings.yaml does not exist.")
            return

        try:
            with open(filepath, "r") as file:
                data = yaml.safe_load(file)

            # Camera setting
            cam_idx = data.get("camera_index", -1)
            if cam_idx in self.available_cams:
                index = self.combo_cameras.findData(cam_idx)
                if index != -1:
                    self.combo_cameras.setCurrentIndex(index)

            # Text
            text_val = data.get("text_value", "")
            self.input_value.setText(text_val)

            # Serial port
            self.selected_port = data.get("selected_port", None)
            if self.selected_port:
                self.label_status.setText(f"Previously selected port: {self.selected_port}")

            print(f"Settings loaded from YAML: {data}")

        except Exception as e:
            print(f"Error while loading YAML: {e}")



    def closeEvent(self, event):
        # If the window is closed via "X", do not save anything here.
        print("Settings window closed by user (X), save skipped.")
        self.camera_widget.resume_camera()
        event.accept()  # Allow close

