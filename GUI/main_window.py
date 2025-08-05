import cv2
from PyQt5.QtWidgets import QMainWindow, QWidget, QDockWidget, QAction
from PyQt5.QtCore import Qt, QTimer

from GUI.custom_widgets.mainwindow_components.camera_widget import CameraWidget  # "." kell, hogy relatív legyen a címzés, ne kérdezd, ez csak úgy kell.
from GUI.custom_widgets.mainwindow_components.log_widget import LogWidget
from GUI.custom_widgets.mainwindow_components.control_widget import ControlWidget
from .camera_dock import CameraDock
from GUI.custom_widgets.openable_widgets.device_settings_widget import SettingsWidget
from GUI.custom_widgets.openable_widgets.manual_control_widget import ManualControlWidget
from GUI.custom_widgets.openable_widgets.marlin_config_window import MarlinConfigWindow  # Importálás a külön fájlból
from File_managers.config_manager import ensure_settings_yaml_exists


class MainWindow(QMainWindow):
    def __init__(self, g_control, locks):
        super().__init__()
        ensure_settings_yaml_exists()  # ✅ Ensure settings file is present
        self.g_control = g_control
        self.locks = locks

        self.setWindowTitle("Main Window with Menu Bar")
        self.setGeometry(100, 100, 1200, 600)

        self.setDockOptions(QMainWindow.AnimatedDocks)
        self.setDockNestingEnabled(False)
        self.custom_value = "Alapértelmezett érték"
        self.manual_saved = False

        self._init_menu()
        self._init_widgets()
        self._connect_signals()


        ## ------------------------------------------------------------------------------
        ## ------------------------------------------------------------------------------
        # Ezen még gondolkozok, hogy hogyan lenne optimálisabb.
        # Mármint hogy csak itt skennelje be az elérhető kamarákat, vagy minden egyes beállítás
        # nyitásnál nézze meg, hogy hátha azóta új camera. Igazából így most mind2 kb. optimális.
        # Csak nem szabad neki új szálat indítani, mert az nagyon lassú.

        # self.available_cams = self.detect_cameras()
        self.available_cams = []
        ## ------------------------------------------------------------------------------
        ## ------------------------------------------------------------------------------


    def _init_menu(self):
        menubar = self.menuBar()

        # Setting fül
        settings_menu = menubar.addMenu("Settings")

        # Devices opció
        open_settings_action = QAction("Devices", self)
        open_settings_action.triggered.connect(self.open_settings_dock)
        settings_menu.addAction(open_settings_action)

        # Marlin config opció
        marlin_config_action = QAction("Marlin config", self)
        marlin_config_action.triggered.connect(self.open_marlin_config)
        settings_menu.addAction(marlin_config_action)

        # Manual Calibration
        manual_menu = menubar.addMenu("Calibration")
        manual_action = QAction("Open Manual Calibration", self)
        manual_action.triggered.connect(self.open_manual_control_dock)
        manual_menu.addAction(manual_action)

        # Open fül a dokk ablakok újranyitására
        open_menu = menubar.addMenu("Open")

        # Logs újranyitása
        open_logs_action = QAction("Logs", self)
        open_logs_action.triggered.connect(lambda: self.log_dock.show())
        open_menu.addAction(open_logs_action)

        # Camera újranyitása
        open_camera_action = QAction("Camera", self)
        open_camera_action.triggered.connect(lambda: self.camera_dock.show())
        open_menu.addAction(open_camera_action)

        # Controls újranyitása
        open_controls_action = QAction("Controls", self)
        open_controls_action.triggered.connect(lambda: self.control_dock.show())
        open_menu.addAction(open_controls_action)



    def _init_widgets(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.log_widget = LogWidget()
        self.log_dock = QDockWidget("Logs", self)
        self.log_dock.setWidget(self.log_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.log_dock)
        self.g_control.log_widget = self.log_widget

        self.camera_widget = CameraWidget()
        self.camera_dock = CameraDock(self.camera_widget, self.log_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.camera_dock)

        self.control_widget = ControlWidget()
        self.control_dock = QDockWidget("Controls", self)
        self.control_dock.setWidget(self.control_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.control_dock)

        self.splitDockWidget(self.camera_dock, self.control_dock, Qt.Vertical)
        self.camera_dock.visibilityChanged.connect(self.handle_camera_visibility)

    def _connect_signals(self):
        self.camera_widget.playPressed.connect(lambda: self.log_widget.append_log("Camera: Play pressed"))
        self.camera_widget.stopPressed.connect(lambda: self.log_widget.append_log("Camera: Stop pressed"))
        self.camera_widget.snapshotPressed.connect(lambda: self.log_widget.append_log("Camera: Snapshot pressed"))

        self.control_widget.btn_picking.clicked.connect(lambda: self.log_widget.append_log("Control: Picking Protocol pressed"))
        self.control_widget.btn_start.clicked.connect(lambda: self.log_widget.append_log("Control: Start pressed"))
        self.control_widget.btn_stop.clicked.connect(lambda: self.log_widget.append_log("Control: Stop pressed"))
        self.control_widget.btn_run.clicked.connect(lambda: self.log_widget.append_log("Control: Run Sterilizing protocol pressed"))

    def handle_camera_visibility(self, visible):
        if not visible:
            QTimer.singleShot(100, self._check_dock_closed)

    def _check_dock_closed(self):
        if not self.camera_dock.isVisible() and not self.camera_dock.isFloating():
            self.camera_widget.on_stop()
            self.log_widget.append_log("Camera panel bezárva, kamera leállítva.")



    """
        -------- OPEN ELEMENTS -----------
    """
    def open_settings_dock(self):
        self.settings_widget = SettingsWidget(self.g_control, self.locks, self.camera_widget,self.available_cams) #
        self.settings_dock = QDockWidget("Settings", self)
        self.settings_dock.setWidget(self.settings_widget)
        self.settings_dock.setFloating(True)
        self.settings_dock.closeEvent = self.settings_close_event
        self.settings_dock.resize(300, 400)
        self.settings_dock.show()

    def settings_close_event(self, event):
        print("📦 Dock closeEvent override → meghívjuk a widget bezárását")
        self.settings_widget.close()  # <-- automatikusan triggereli a closeEvent()-et
        event.accept()

    def open_marlin_config(self):
        self.marlin_config_window = MarlinConfigWindow(self.g_control,self.log_widget)
        self.marlin_config_window.show()
        self._config_refs = getattr(self, "_config_refs", [])
        self._config_refs.append(self.marlin_config_window)  # hogy ne gyűjtse be a GC


    def open_manual_control_dock(self):
        self.manual_widget = ManualControlWidget(self.g_control,self.log_widget)
        self.manual_dock = QDockWidget("Manual Control", self)
        self.manual_dock.setWidget(self.manual_widget)

        # 💡 Fontos: a widget automatikusan törlődjön bezáráskor
        self.manual_dock.setAttribute(Qt.WA_DeleteOnClose)
        self.manual_dock.closeEvent = self.manual_close_event

        # Ne tartsunk meg külső referenciát
        self.manual_dock.setFloating(True)
        self.manual_dock.resize(200, 350)
        self.manual_dock.show()

    # closeEvent
    def manual_close_event(self, event):
        print("📦 📦 Dock closeEvent override → meghívjuk a widget bezárását")
        self.manual_widget.close()  # <-- automatikusan triggereli a closeEvent()-et

        event.accept()

    """
    def set_camera_from_settings(self, index):
        self.camera_widget.combo_cameras.setCurrentIndex(
            self.camera_widget.combo_cameras.findData(index)
        )
        self.log_widget.append_log(f"Settings: Camera {index} kiválasztva")

    def update_custom_value(self, value):
        self.custom_value = value
        self.log_widget.append_log(f"Settings: érték megváltoztatva -> {value}")

        # Zárjuk be a settings dockot, ha létezik
        if hasattr(self, 'settings_dock') and self.settings_dock:
            self.settings_dock.close()
            self.log_widget.append_log("Settings panel bezárva (alkalmazás után).")
    """

    def handle_manual_action(self, action):
        if action == "save":
            self.manual_saved = True
            self.log_widget.append_log("Manual control: érték elmentve (manual_saved = True)")

            # Bezárjuk a dockot
            if hasattr(self, 'manual_dock') and self.manual_dock:
                self.manual_dock.close()
                self.log_widget.append_log("Manual control panel bezárva (mentés után)")
        else:
            self.log_widget.append_log(f"Manual action: {action}")

    def detect_cameras(self):
            available = []
            for i in range(5):  # Próbáljunk 5 lehetséges kameraindexet
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        available.append(i)

                    cap.release()
            available  # Itt állítjuk be
            return available

    def closeEvent(self, event):
        print("⬅️ A widget most záródik be")

        if self.g_control:
            try:
                print("[INFO] Szálak leállítása MainWindow.closeEvent()-ben...")
                self.g_control.stop_threads()
            except Exception as e:
                print(f"[HIBA] Szálak leállítása sikertelen: {e}")

        event.accept()



