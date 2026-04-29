import sys
from PyQt5.QtWidgets import QMainWindow, QWidget, QAction, QVBoxLayout, QSplitter, QGroupBox
from PyQt5.QtCore import Qt, QTimer
import threading

from GUI.custom_widgets.mainwindow_components.camera_widget import CameraWidget  # Keep import path this way for reliable module resolution.
from GUI.custom_widgets.mainwindow_components.log_widget import LogWidget
from GUI.custom_widgets.openable_widgets.manual_control_widget import ManualControlWidget
from GUI.custom_widgets.openable_widgets.marlin_config_window import MarlinConfigWindow
from File_managers.config_manager import ensure_settings_yaml_exists
from Pozitioner_and_Communicater.CommandSender import CommandSender
from GUI.custom_widgets.openable_widgets.motion_calibration_window import MotionCalibrationWindow
from GUI.custom_widgets.openable_widgets.pixel_calibration_window import PixelCalibrationWindow


class _StderrToLog:
    def __init__(self, log_widget):
        self.log_widget = log_widget
        self._buffer = ""

    def write(self, text):
        if text is None:
            return 0
        s = str(text)
        self._buffer += s
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                self.log_widget.append_log(line)
        return len(s)

    def flush(self):
        if self._buffer.strip():
            self.log_widget.append_log(self._buffer.rstrip("\r"))
        self._buffer = ""


class MainWindow(QMainWindow):
    def __init__(self, g_control):
        super().__init__()
        ensure_settings_yaml_exists()  # Ensure settings file is present
        self.g_control = g_control
        self._orig_stderr = sys.stderr
        self._stderr_proxy = None

        self.command_sender = CommandSender(self.g_control)
        self.command_sender.start()
        self.g_control.command_sender = self.command_sender

        self.setWindowTitle("Main Window with Menu Bar")
        self.setGeometry(100, 100, 1200, 600)

        self._init_menu()
        self._init_widgets()
        self._install_stderr_logging()
        QTimer.singleShot(250, self._startup_connect_sequence)
        self._connect_signals()


        ## ------------------------------------------------------------------------------
        ## ------------------------------------------------------------------------------
        # Still deciding what is optimal here:
        # scan available cameras only once here, or on every settings open to catch new devices.
        # Current behavior is an acceptable tradeoff.
        # We should avoid starting a new scan thread each time because it is slow.

        # self.available_cams = self.detect_cameras()
        self.available_cams = []
        ## ------------------------------------------------------------------------------
        ## ------------------------------------------------------------------------------


    def _init_menu(self):
        menubar = self.menuBar()

        # Settings menu
        settings_menu = menubar.addMenu("Settings")

        # Marlin config option
        marlin_config_action = QAction("Marlin config", self)
        marlin_config_action.triggered.connect(self.open_marlin_config)
        settings_menu.addAction(marlin_config_action)

        # Pixel / mm calibration
        pixel_calib_action = QAction("Pixel / mm calibration", self)
        pixel_calib_action.triggered.connect(self.open_pixel_calibration)
        settings_menu.addAction(pixel_calib_action)

        # Pipeline fullscreen toggle
        from File_managers import config_manager as _cm
        pf_enabled = _cm.load_settings().get("pipeline_fullscreen", True)
        self.pipeline_fullscreen_action = QAction("Pipeline Maximize", self)
        self.pipeline_fullscreen_action.setCheckable(True)
        self.pipeline_fullscreen_action.setChecked(bool(pf_enabled))
        from PyQt5.QtWidgets import QApplication
        def _on_toggle_pipeline_fullscreen(checked):
            try:
                _cm.update_setting("pipeline_fullscreen", bool(checked))
                # update any existing pipeline widgets/windows to the new state
                try:
                    for w in QApplication.topLevelWidgets():
                        try:
                            ctx = getattr(w, 'context', None)
                            if ctx is not None and getattr(ctx, 'pipeline_fullscreen', None) is not None:
                                ctx.pipeline_fullscreen = bool(checked)
                                # apply to the window itself
                                if bool(checked):
                                    try:
                                        w.showMaximized()
                                    except Exception:
                                        pass
                                else:
                                    try:
                                        w.showNormal()
                                    except Exception:
                                        pass
                        except Exception:
                            continue
                except Exception:
                    pass
            except Exception:
                pass
        self.pipeline_fullscreen_action.toggled.connect(_on_toggle_pipeline_fullscreen)
        settings_menu.addAction(self.pipeline_fullscreen_action)

        # Open menu
        open_menu = menubar.addMenu("Open")

        open_motion_cal_action = QAction("Motion Calibration (X/Y)", self)
        open_motion_cal_action.triggered.connect(self.open_motion_calibration_window)
        open_menu.addAction(open_motion_cal_action)



    def _init_widgets(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        self.setStyleSheet("""
            QGroupBox#sectionLogs,
            QGroupBox#sectionCamera,
            QGroupBox#sectionManual {
                border: 1px solid #9a9a9a;
                border-radius: 4px;
                margin-top: 10px;
                background-color: #f8f8f8;
            }
            QGroupBox#sectionLogs::title,
            QGroupBox#sectionCamera::title,
            QGroupBox#sectionManual::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                padding: 1px 7px;
                color: #ffffff;
                background-color: #6a6a6a;
                font-weight: 600;
                border-radius: 3px;
            }
            QSplitter::handle {
                background-color: #b6b6b6;
            }
        """)

        self.log_widget = LogWidget()
        self.g_control.log_widget = self.log_widget

        self.camera_widget = CameraWidget(self.log_widget, self)

        self.control_widget = ManualControlWidget(self.g_control, self.log_widget, self.command_sender, self)

        # Left panel: logs
        log_group = QGroupBox("Logs")
        log_group.setObjectName("sectionLogs")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 10, 6, 6)
        log_layout.addWidget(self.log_widget)

        # Right top: camera
        camera_group = QGroupBox("Camera")
        camera_group.setObjectName("sectionCamera")
        camera_layout = QVBoxLayout(camera_group)
        camera_layout.setContentsMargins(6, 10, 6, 6)
        camera_layout.addWidget(self.camera_widget)

        # Right bottom: manual control
        control_group = QGroupBox("Manual Control")
        control_group.setObjectName("sectionManual")
        control_layout = QVBoxLayout(control_group)
        control_layout.setContentsMargins(6, 10, 6, 6)
        control_layout.addWidget(self.control_widget)

        # Right side splitter (camera/control)
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setHandleWidth(4)
        right_splitter.addWidget(camera_group)
        right_splitter.addWidget(control_group)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 1)

        # Main splitter (logs vs right side)
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setHandleWidth(4)
        main_splitter.addWidget(log_group)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 5)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([1320, 60])

        root_layout.addWidget(main_splitter)

    def _connect_signals(self):
        self.camera_widget.playPressed.connect(lambda: self.log_widget.append_log("Camera: Play pressed"))
        self.camera_widget.stopPressed.connect(lambda: self.log_widget.append_log("Camera: Stop pressed"))
        self.camera_widget.snapshotPressed.connect(lambda: self.log_widget.append_log("Camera: Snapshot pressed"))

        self.control_widget.actionCommand.connect(self.handle_manual_action)

    def _startup_connect_sequence(self):
        self.log_widget.append_log("[INFO] Startup auto-connect: launching in background thread...")

        def _do_autoconnect():
            self.log_widget.append_log("[INFO] Startup auto-connect attempt...")
            try:
                self.g_control.autoconnect()
            except Exception as e:
                self.log_widget.append_log(f"[ERROR] Startup autoconnect exception: {e}")
            finally:
                QTimer.singleShot(0, self._on_startup_connect_done)

        t = threading.Thread(target=_do_autoconnect, daemon=True, name="startup-autoconnect")
        t.start()

    def _on_startup_connect_done(self):
        if not getattr(self.g_control, "connected", False):
            self.log_widget.append_log("[WARN] Startup auto-connect failed; no device found.")
        else:
            self.log_widget.append_log("[OK] Startup auto-connect succeeded.")

        if hasattr(self, "control_widget") and self.control_widget:
            try:
                self.control_widget.check_connection()
            except Exception:
                pass

    def _install_stderr_logging(self):
        self._stderr_proxy = _StderrToLog(self.log_widget)
        sys.stderr = self._stderr_proxy

    def _restore_stderr_logging(self):
        try:
            if self._stderr_proxy:
                self._stderr_proxy.flush()
        except Exception:
            pass
        sys.stderr = self._orig_stderr



    """
        -------- OPEN ELEMENTS -----------
    """
    def open_marlin_config(self):
        self.marlin_config_window = MarlinConfigWindow(self.g_control,self.log_widget)
        self.marlin_config_window.show()
        self._config_refs = getattr(self, "_config_refs", [])
        self._config_refs.append(self.marlin_config_window)  # hogy ne gyÅ±jtse be a GC
    def handle_manual_action(self, action):
        if action == "save":
            self.log_widget.append_log("[CONTROL_CMD] Manual control save requested")
        elif action in ("in", "out"):
            # Z-tengely vezérlés: IN = Z+, OUT = Z-
            step_mm = getattr(self.control_widget, "jog_step_mm", 15.0)
            feedrate = getattr(self.control_widget, "jog_feedrate", 3000)
            if action == "in":
                cmd = f"G91\nG1 Z{step_mm:g} F{feedrate}\n"
                self.log_widget.append_log(f"[GCODE] G91 | G1 Z+{step_mm:g} F{feedrate}")
            else:
                cmd = f"G91\nG1 Z-{step_mm:g} F{feedrate}\n"
                self.log_widget.append_log(f"[GCODE] G91 | G1 Z-{step_mm:g} F{feedrate}")
            self.command_sender.sendCommand.emit(cmd)
        else:
            self.log_widget.append_log(f"[CONTROL_CMD] Manual control action requested: {action}")

    def closeEvent(self, event):
        self.log_widget.append_log("[INFO] Main window is closing")

        # Graceful shutdown: stop motion + disable steppers, but do NOT send M112.
        # M112 kills Creality/STM32 firmware and requires a power cycle to recover.
        if self.g_control:
            try:
                if self.g_control.ser and self.g_control.ser.is_open:
                    self.g_control.ser.write(b"M410\n")   # quickstop (abort motion)
                    self.g_control.ser.write(b"M107\n")   # fan/LED off
                    self.g_control.ser.write(b"M18\n")    # steppers off
                    self.g_control.ser.flush()
                    self.log_widget.append_log("[INFO] Sent M410+M107+M18 for graceful shutdown.")
            except Exception as e:
                self.log_widget.append_log(f"[WARN] Failed to send shutdown commands: {e}")

            try:
                self.log_widget.append_log("[INFO] Stopping threads in MainWindow.closeEvent()...")
                self.g_control.stop_threads()
            except Exception as e:
                self.log_widget.append_log(f"[ERROR] Failed to stop threads: {e}")
        self._restore_stderr_logging()
        event.accept()

    def set_command_sender(self, new_sender):
        if hasattr(self, 'command_sender') and self.command_sender:
            try:
                if self.command_sender.isRunning():
                    self.log_widget.append_log("[INFO] Stopping previous CommandSender...")
                    self.command_sender.stop()
                    self.command_sender.wait()  # This is CRITICAL
            except Exception as e:
                self.log_widget.append_log(f"[ERROR] Error while stopping CommandSender: {e}")

        self.command_sender = new_sender
        if not self.command_sender.isRunning():
            self.log_widget.append_log("[INFO] Starting new CommandSender...")
            self.command_sender.start()

        self.g_control.command_sender = self.command_sender

    def get_g_control(self):
        return self.g_control

    def get_command_sender(self):
        return self.command_sender

    def open_motion_calibration_window(self):
        self.motion_cal_win = MotionCalibrationWindow(self.g_control, self.log_widget)
        self.motion_cal_win.show()
        # keep a ref so it isn't GC'd
        self._config_refs = getattr(self, "_config_refs", [])
        self._config_refs.append(self.motion_cal_win)

    def open_pixel_calibration(self):
        self.pixel_calib_win = PixelCalibrationWindow(self.g_control, self.camera_widget, self.log_widget)
        self.pixel_calib_win.show()
        self._config_refs = getattr(self, "_config_refs", [])
        self._config_refs.append(self.pixel_calib_win)