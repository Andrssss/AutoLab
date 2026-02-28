import time

import cv2, os
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QSizePolicy
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
import yaml
from File_managers import config_manager
from GUI.custom_widgets.photo_pipeline.pipeline_widget import PipelineWidget


from GUI.custom_widgets.mainwindow_components.CameraSettingsDialog import CameraSettingsDialog


class CameraWidget(QWidget):
    playPressed = pyqtSignal()
    stopPressed = pyqtSignal()
    snapshotPressed = pyqtSignal()

    def __init__(self, g_control, log_widget, command_sender, main_window, camera_index=None, available_cams=None, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index or 0  # vagy 0, ha None
        self.available_cams = available_cams or []
        self.main_window = main_window
        self.g_control = g_control
        self.log_widget = log_widget
        self.command_sender = command_sender
        self.capture_after_led = False
        self.frames_to_skip = 0

        # Load saved settings
        from File_managers import config_manager
        camera_settings = config_manager.load_camera_settings(self.camera_index)
        self.zoom_level = camera_settings.get("zoom_level", 1.0)
        self.zoom_offset_x = camera_settings.get("offset_x", 0.0)
        self.zoom_offset_y = camera_settings.get("offset_y", 0.0)
        self.blur_enabled = camera_settings.get("blur", False)
        self.gain = camera_settings.get("gain", 0.0)
        self.exposure = camera_settings.get("exposure", -6.0)

        self.cap = cv2.VideoCapture(self.camera_index)

        if self.cap and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_GAIN, self.gain)


        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.current_frame = None
        self.camera_index = camera_index
        self.available_cams = available_cams or []  # empty list if not provided
        self.initUI()


    def initUI(self):
        layout = QVBoxLayout()

        # Dropdown list for available cameras
        self.combo_cameras = QComboBox()
        self.combo_cameras.currentIndexChanged.connect(self.on_camera_change)
        layout.addWidget(self.combo_cameras)

        # Camera image display
        self.label_camera = QLabel("Camera Feed")
        self.label_camera.setMinimumSize(400, 200)
        self.label_camera.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.label_camera.setStyleSheet("background-color: black;")
        self.label_camera.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label_camera)

        # Gombok: Play, Stop, Snapshot
        btn_layout = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.btn_stop = QPushButton("Stop")
        self.btn_snapshot = QPushButton("Snapshot")

        # settings button
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(24, 24)
        self.btn_settings.setToolTip("Camera settings")
        self.btn_settings.setStyleSheet("padding: 0px; margin-left: 4px;")

        btn_layout.addWidget(self.btn_play)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_snapshot)
        btn_layout.addWidget(self.btn_settings)  

        self.btn_play.clicked.connect(self.on_play)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_snapshot.clicked.connect(self.on_snapshot)
        self.btn_settings.clicked.connect(self.open_camera_settings)

        layout.addLayout(btn_layout)  # add buttons to layout
        self.setLayout(layout)
        self.populate_camera_list()

    def detect_cameras(self): # -----------------------------------------------------TODO
        if not self.available_cams:  # If list is empty, detect available devices
            available = []
            # Try 5 possible camera indexes
            for i in range(5):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        available.append(i)
                    cap.release()
            return available
        else:
            return self.available_cams

    def populate_camera_list(self):
        self.available_cams = self.detect_cameras()
        self.combo_cameras.clear()
        for index in self.available_cams:
            self.combo_cameras.addItem(f"Camera {index}", index)
        if self.available_cams:
            self.combo_cameras.setCurrentIndex(0)
            self.load_camera_index_from_yaml()  # load from YAML here
            self.on_play() # start immediately

    def set_camera(self, index):
        self.camera_index = index
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(index)

        # Load settings for the selected camera index
        camera_settings = config_manager.load_camera_settings(self.camera_index)
        self.zoom_level = camera_settings.get("zoom_level", 1.0)
        self.zoom_offset_x = camera_settings.get("offset_x", 0.0)
        self.zoom_offset_y = camera_settings.get("offset_y", 0.0)
        self.blur_enabled = camera_settings.get("blur", False)
        self.gain = camera_settings.get("gain", 0.0)
        self.exposure = camera_settings.get("exposure", -6.0)

        if self.cap and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_GAIN, self.gain)

        self.log_widget.append_log(f"[INFO] Camera {index} settings loaded.")

    def on_play(self):
        current_index = self.combo_cameras.currentData()
        # Don't restart if it's already running and the selected camera is active
        if self.timer.isActive() and current_index == self.camera_index:
            self.log_widget.append_log(f"[INFO] Camera {current_index} is already running. Ignoring Play.")
            return
        self.playPressed.emit()
        if current_index is not None:
            self.set_camera(current_index)
        if not self.timer.isActive():
            self.timer.start(30)

    def on_stop(self):
        self.stopPressed.emit()
        if self.timer.isActive():
            self.timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        self.label_camera.clear()
        self.label_camera.setText("Camera Feed")

    def on_snapshot(self):
        # read desired LED level (per camera)
        cam_set = config_manager.load_camera_settings(self.camera_index)
        s = cam_set.get("led_pwm", 255)

        if not self.g_control.connected:
            self.log_widget.append_log("[ERROR] Machine is not connected (M106 skipped).")
        else:
            # 1) LED ON (async)
            cmd_on = f"M106 S{s}\n" if s > 0 else "M106 S0\n"
            self.log_widget.append_log(f"[LED] ON -> {cmd_on.strip()}")
            self.command_sender.sendCommand.emit(cmd_on)

        # 2) Arm a capture a few frames later so exposure/AE can settle
        #    (2-3 frames is usually fine at 30 fps: ~66-100 ms)
        self.frames_to_skip = 3
        self.capture_after_led = True

        # optional: mark UI/log
        self.snapshotPressed.emit()

    def open_camera_settings(self):
        if self.camera_index is not None:
            self.pause_camera()
            dialog = CameraSettingsDialog(self.camera_index,self.zoom_level,self.zoom_offset_x,self.zoom_offset_y,self.blur_enabled,self.gain,self.exposure,self.g_control, self.log_widget, self.command_sender, self)
            dialog.exec_()
            self.resume_camera()

            if hasattr(dialog, "result"):
                # Apply returned settings
                self.zoom_level = dialog.result.get("zoom_level", 1.0)
                self.zoom_offset_x = dialog.result.get("offset_x", 0)
                self.zoom_offset_y = dialog.result.get("offset_y", 0)
                self.blur_enabled = dialog.result.get("blur", False)
                self.gain = dialog.result.get("gain", 0.0)
                self.exposure = dialog.result.get("exposure", -6.0)

                self.log_widget.append_log("[INFO] Camera settings applied:")
                self.log_widget.append_log(f"Zoom: {self.zoom_level}, Offset X: {self.zoom_offset_x}, Offset Y: {self.zoom_offset_y}, Blur: {self.blur_enabled}")

        else:
            self.log_widget.append_log("No active camera index.")

    def update_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.current_frame = frame
                frame_to_show = self.apply_zoom_and_blur(frame)
                rgb_image = cv2.cvtColor(frame_to_show, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qimg = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg).scaled(self.label_camera.size(), Qt.KeepAspectRatio)
                self.label_camera.setPixmap(pixmap)

                # ---- deferred capture after LED ON ----
                if self.capture_after_led:
                    if self.frames_to_skip > 0:
                        self.frames_to_skip -= 1
                    else:
                        # take the photo from the *current* lit frame
                        self.capture_after_led = False
                        self.capture_image()

                        # LED OFF
                        self.command_sender.sendCommand.emit("M106 S0\n")
                        self.log_widget.append_log("[LED] OFF -> M106 S0")

    def apply_zoom_and_blur(self, frame):
        h, w = frame.shape[:2]

        # Crop zoomed image
        if self.zoom_level > 1.0:
            new_w, new_h = int(w / self.zoom_level), int(h / self.zoom_level)

            center_x = w // 2 + int(self.zoom_offset_x * (w // 2 - new_w // 2))
            center_y = h // 2 + int(self.zoom_offset_y * (h // 2 - new_h // 2))

            x1 = max(center_x - new_w // 2, 0)
            y1 = max(center_y - new_h // 2, 0)
            x2 = min(x1 + new_w, w)
            y2 = min(y1 + new_h, h)

            frame = frame[y1:y2, x1:x2]

        # Apply blur if enabled
        if self.blur_enabled:
            frame = cv2.GaussianBlur(frame, (15, 15), 0)

        return frame

    def capture_image(self):
        if self.current_frame is not None:
            processed_frame = self.apply_zoom_and_blur(self.current_frame)

            base_dir = r"C:\Users\Public\Pictures\MyCaptures"
            date_folder = datetime.now().strftime("%Y.%m.%d")
            save_folder = os.path.join(base_dir, date_folder)
            os.makedirs(save_folder, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = os.path.join(save_folder, f"capture_cam{self.camera_index}_{timestamp}.jpg")

            cv2.imwrite(filename, processed_frame)
            self.log_widget.append_log(f"Image saved: {filename}")

            # Open the image in the analyzer
            self.open_bacteria_analyzer(filename)

    def open_bacteria_analyzer(self, image_path=None):
        self.analyzer_window = PipelineWidget(self.main_window, image_path, self.log_widget)
        self.analyzer_window.setWindowState(self.analyzer_window.windowState() & ~Qt.WindowFullScreen)
        self.analyzer_window.showMaximized()
    '''
    # The old version 
    def open_bacteria_analyzer(self, image_path):
        self.analyzer_window = BacteriaAnalyzerWidget(image_path)
        self.analyzer_window.show()
    '''


    def on_camera_change(self, i):
        index = self.combo_cameras.itemData(i)
        if index is not None and index != self.camera_index:
            was_running = self.timer.isActive()
            if was_running:
                self.on_stop()
                self.log_widget.append_log(f"Camera {self.camera_index} stopped.")

                self.stopPressed.emit()  # Log jele
            self.set_camera(index)
            if was_running:
                self.timer.start(30)
                self.log_widget.append_log(f"Camera {self.camera_index} started.")
                self.playPressed.emit()  # Log jele

    def load_camera_index_from_yaml(self, filepath="settings.yaml"):
        if not os.path.exists(filepath):
            self.log_widget.append_log("settings.yaml not found.")
            return

        try:
            with open(filepath, "r") as f:
                data = yaml.safe_load(f)
            index_from_yaml = data.get("camera_index", None)

            if index_from_yaml in self.available_cams:
                idx = self.combo_cameras.findData(index_from_yaml)
                if idx != -1:
                    self.combo_cameras.setCurrentIndex(idx)
                    self.log_widget.append_log(f"Camera index set from YAML: {index_from_yaml}")
            else:
                self.log_widget.append_log(f"The loaded camera index ({index_from_yaml}) is not available.")
        except Exception as e:
            self.log_widget.append_log(f"Error reading settings.yaml: {e}")

    def select_camera_by_index(self, index):
        # If this camera is already active, do nothing
        if index == self.camera_index:
            self.log_widget.append_log(f"Camera {index} is already active, no switch needed.")
            return False

        idx = self.combo_cameras.findData(index)
        if idx != -1:
            was_running = self.timer.isActive()

            if was_running and self.combo_cameras.setCurrentIndex(idx)!=index:
                self.on_stop()
                self.log_widget.append_log(f"Camera {self.camera_index} stopped due to external switch.")
                self.stopPressed.emit()

            self.combo_cameras.setCurrentIndex(idx)  # triggers the switch
            self.on_play()
            self.playPressed.emit()
            return True
        else:
            self.log_widget.append_log(f"Camera index {index} is not in the list.")
            return False

    def pause_camera(self):
        self.log_widget.append_log("[INFO] Camera temporarily stopped for settings.")
        self.on_stop()

    def resume_camera(self):
        self.log_widget.append_log("[INFO] Restarting camera after settings.")
        self.on_play()  # restart with same index

