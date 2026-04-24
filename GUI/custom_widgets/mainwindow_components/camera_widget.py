import time
import threading

import cv2, os
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QSizePolicy
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap
import yaml
from File_managers import config_manager
from GUI.custom_widgets.photo_pipeline.manual_steps.manual_pipeline_widget import PipelineWidget
from GUI.custom_widgets.mainwindow_components.CameraSettingsWidget import CameraSettingsWidget


class CameraWorker(QThread):
    """Opens, reads, and closes its own cv2.VideoCapture entirely in the background thread."""
    frame_ready = pyqtSignal(object)   # emits numpy BGR frame
    error       = pyqtSignal(str)

    def __init__(self, camera_index: int):
        super().__init__()
        self._index   = camera_index
        self._fps     = 30
        self._running = False

    def run(self):
        cap = cv2.VideoCapture(self._index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.error.emit(f"[ERROR] Could not open camera {self._index}.")
            return
        self._running = True  
        while self._running:
            ret, frame = cap.read()
            if ret:
                self.frame_ready.emit(frame)
            else:
                self.error.emit("[WARN] Camera read failed (no frame).")
                time.sleep(0.1)
                continue
            time.sleep(1.0 / self._fps ) #  30 FPS -> circa 33 ms per frame 
        cap.release()

    def request_stop(self):
        """Non-blocking: signal the loop to exit. Thread dies on its own."""
        self._running = False


class CameraWidget(QWidget):
    playPressed     = pyqtSignal()
    stopPressed     = pyqtSignal()
    snapshotPressed = pyqtSignal()
    _cameras_ready  = pyqtSignal(list)   # emitted by detect thread → main thread

    def __init__(self, log_widget, main_window, camera_index=None, available_cams=None, parent=None):
        super().__init__(parent)
        self.camera_index    = camera_index   # may be None until camera is selected
        self.available_cams  = available_cams or []
        self.main_window     = main_window
        self.log_widget      = log_widget
        self.capture_after_led = False
        self.frames_to_skip    = 0
        self.current_frame     = None

        # Load saved settings (default index 0 for initial load)
        _idx = camera_index if camera_index is not None else 0
        camera_settings = config_manager.load_camera_settings(_idx)
        self.zoom_level    = camera_settings.get("zoom_level", 1.0)
        self.zoom_offset_x = camera_settings.get("offset_x",   0.0)
        self.zoom_offset_y = camera_settings.get("offset_y",   0.0)
        self.blur_enabled  = camera_settings.get("blur",       False)
        self.gain          = camera_settings.get("gain",       0.0)
        self.exposure      = camera_settings.get("exposure",  -6.0)

        self._worker: CameraWorker | None = None
        self._is_running = False   # tracks whether capture is active

        # wire the detection-done signal (must be done before initUI calls populate_camera_list)
        self._cameras_ready.connect(self._on_cameras_detected)

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

    def detect_cameras(self):
        if self.available_cams:
            return self.available_cams

        self.log_widget.append_log("[INFO] Camera detection started (probing indexes 0, 1, 2 in order)...")
        available = []

        for idx in range(3):
            self.log_widget.append_log(f"[INFO] Probing camera index {idx}...")
            cap = None
            found = False
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                opened = cap.isOpened()
                self.log_widget.append_log(f"[INFO] Camera {idx}: isOpened={opened}")
                if opened:
                    for attempt in range(5):
                        ret, _ = cap.read()
                        if ret:
                            found = True
                            self.log_widget.append_log(f"[OK] Camera {idx} found (frame OK on attempt {attempt}).")
                            break
                    if not found:
                        self.log_widget.append_log(f"[WARN] Camera {idx}: opened but no valid frame after 5 attempts.")
                else:
                    self.log_widget.append_log(f"[INFO] Camera {idx}: not present.")
            except Exception as exc:
                self.log_widget.append_log(f"[ERROR] Camera {idx} probe exception: {exc}")
            finally:
                if cap is not None:
                    cap.release()

            if found:
                available.append(idx)

        self.log_widget.append_log(f"[INFO] Camera detection finished. Found: {available}")
        return available

    def populate_camera_list(self):
        """Detect cameras in a background thread, then populate the combo on the main thread."""
        self.combo_cameras.setEnabled(False)
        self.combo_cameras.addItem("Detecting cameras...")

        def _detect():
            cams = self.detect_cameras()
            self._cameras_ready.emit(cams)   # thread-safe: crosses to main thread via Qt signal

        threading.Thread(target=_detect, daemon=True, name="camera-detect").start()

    def _on_cameras_detected(self, available_cams):
        self.available_cams = available_cams
        self.combo_cameras.blockSignals(True)
        self.combo_cameras.clear()
        for index in self.available_cams:
            self.combo_cameras.addItem(f"Camera {index}", index)
        self.combo_cameras.blockSignals(False)
        self.combo_cameras.setEnabled(True)
        if self.available_cams:
            self.combo_cameras.setCurrentIndex(0)
            self.load_camera_index_from_yaml()
            if not self._is_running:
                self.on_play()

    def set_camera(self, index):
        """Load settings for index. Does NOT start capture (no blocking cap open)."""
        self._load_camera_settings(index)
        self.camera_index = index
        self.log_widget.append_log(f"[INFO] Camera {index} settings loaded.")

    def _load_camera_settings(self, index):
        camera_settings = config_manager.load_camera_settings(index)
        self.zoom_level    = camera_settings.get("zoom_level", 1.0)
        self.zoom_offset_x = camera_settings.get("offset_x",   0.0)
        self.zoom_offset_y = camera_settings.get("offset_y",   0.0)
        self.blur_enabled  = camera_settings.get("blur",       False)
        self.gain          = camera_settings.get("gain",       0.0)
        self.exposure      = camera_settings.get("exposure",  -6.0)

    # ------------------------------------------------------------------
    # Worker management (non-blocking stop)
    # ------------------------------------------------------------------
    def _start_worker(self, index: int):
        """Start capture for *index*. Always non-blocking."""
        self._kill_worker()
        self.camera_index = index
        self._worker = CameraWorker(index)
        self._worker.frame_ready.connect(self._on_frame_ready)
        self._worker.error.connect(self.log_widget.append_log)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()
        self._is_running = True
        self.log_widget.append_log(f"[INFO] Camera {index}: capture thread started.")

    def _kill_worker(self):
        """Signal the worker to stop without blocking the main thread."""
        if self._worker is not None:
            try:
                self._worker.frame_ready.disconnect()
            except Exception:
                pass
            self._worker.request_stop()
            self._worker = None
        self._is_running = False

    # kept for external code that calls _stop_worker
    def _stop_worker(self):
        self._kill_worker()

    # ------------------------------------------------------------------
    # Play / Stop
    # ------------------------------------------------------------------
    def on_play(self):
        current_index = self.combo_cameras.currentData()
        if current_index is None:
            self.log_widget.append_log("[WARN] No camera selected.")
            return
        if self._is_running and current_index == self.camera_index:
            self.log_widget.append_log(f"[INFO] Camera {current_index} is already running. Ignoring Play.")
            return
        self.playPressed.emit()
        self._load_camera_settings(current_index)
        self._start_worker(current_index)

    def on_stop(self):
        self.log_widget.append_log("[INFO] Camera: Stop pressed")
        self.stopPressed.emit()
        self._kill_worker()
        self.current_frame = None
        self.label_camera.clear()
        self.label_camera.setText("Camera Feed")

    def _on_frame_ready(self, frame):
        """Runs on the main thread – display + deferred capture logic only."""
        self.current_frame = frame
        frame_to_show = self.apply_zoom_and_blur(frame)
        rgb_image = cv2.cvtColor(frame_to_show, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        qimg = QImage(rgb_image.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(self.label_camera.size(), Qt.KeepAspectRatio)
        self.label_camera.setPixmap(pixmap)

        if self.capture_after_led:
            if self.frames_to_skip > 0:
                self.frames_to_skip -= 1
            else:
                self.capture_after_led = False
                self.capture_image()
                self._send_led_pwm(0)


    def on_snapshot(self):
        led_cfg = config_manager.load_led_settings(default_pwm=255, default_enabled=False)
        s = int(led_cfg.get("led_pwm", 255)) if bool(led_cfg.get("led_enabled", False)) else 0
        self._send_led_pwm(s)
        self.frames_to_skip    = 3
        self.capture_after_led = True
        self.snapshotPressed.emit()

    def _send_led_pwm(self, s_value: int):
        g_control = getattr(self.main_window, "g_control", None)
        if g_control:
            g_control.send_led_pwm(s_value)

    def open_camera_settings(self):
        if self.camera_index is None:
            self.log_widget.append_log("No active camera index.")
            return
        was_running = self._is_running
        self._kill_worker()
        dialog = CameraSettingsWidget(
            self.camera_index,
            self.zoom_level, self.zoom_offset_x, self.zoom_offset_y,
            self.blur_enabled, self.gain, self.exposure,
            self.log_widget, self.main_window, self,
        )
        dialog.exec_()
        if hasattr(dialog, "result"):
            self.zoom_level    = dialog.result.get("zoom_level", 1.0)
            self.zoom_offset_x = dialog.result.get("offset_x",   0)
            self.zoom_offset_y = dialog.result.get("offset_y",   0)
            self.blur_enabled  = dialog.result.get("blur",       False)
            self.gain          = dialog.result.get("gain",       0.0)
            self.exposure      = dialog.result.get("exposure",  -6.0)
            self.log_widget.append_log("[INFO] Camera settings applied.")
        if was_running:
            self._start_worker(self.camera_index)

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
        self.analyzer_window.pipeline_finished.connect(self._on_pipeline_finished)
        self.analyzer_window.setWindowState(self.analyzer_window.windowState() & ~Qt.WindowFullScreen)
        self.analyzer_window.showMaximized()

    def _on_pipeline_finished(self):
        if self.analyzer_window:
            self.analyzer_window.close()
            self.analyzer_window = None
    '''
    # The old version 
    def open_bacteria_analyzer(self, image_path):
        self.analyzer_window = BacteriaAnalyzerWidget(image_path)
        self.analyzer_window.show()
    '''


    def on_camera_change(self, i):
        index = self.combo_cameras.itemData(i)
        if index is not None and index != self.camera_index:
            was_running = self._is_running
            if was_running:
                self._kill_worker()
                self.log_widget.append_log(f"Camera {self.camera_index} stopped.")
                self.stopPressed.emit()
            self.set_camera(index)
            if was_running:
                self._start_worker(index)
                self.log_widget.append_log(f"Camera {index} started.")
                self.playPressed.emit()

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
        if index == self.camera_index:
            self.log_widget.append_log(f"Camera {index} is already active, no switch needed.")
            return False
        idx = self.combo_cameras.findData(index)
        if idx != -1:
            self.combo_cameras.setCurrentIndex(idx)
            self.on_play()
            self.playPressed.emit()
            return True
        else:
            self.log_widget.append_log(f"Camera index {index} is not in the list.")
            return False

    def pause_camera(self):
        self._kill_worker()

    def resume_camera(self):
        if self.camera_index is not None:
            self._start_worker(self.camera_index)

    # kept for any external callers that used the old QTimer interface
    def update_frame(self):
        pass

    # kept for compatibility – timer.isActive() checks
    @property
    def timer(self):
        class _T:
            def __init__(self_, active): self_._a = active
            def isActive(self_): return self_._a
        return _T(self._is_running)

