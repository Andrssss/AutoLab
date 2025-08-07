from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit, QApplication, QHBoxLayout
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QEventLoop
import cv2

class StepPickingWidget(QWidget):
    finished = pyqtSignal()

    def __init__(self, context, image_path=None, main_window=None):
        super().__init__()
        self.context = context
        self.main_window = main_window

        # UI setup
        layout = QVBoxLayout()

        self.image_label = QLabel("No Image")
        self.image_label.setFixedHeight(200)
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        # Get external dependencies
        try:
            self.command_sender = main_window.get_command_sender()
        except Exception as e:
            self.command_sender = None
            self.log_box.append(f"[HIBA] command_sender lekérése sikertelen: {e}")

        try:
            self.g_control = main_window.get_g_control()
        except Exception as e:
            self.g_control = None
            self.log_box.append(f"[HIBA] g_control lekérése sikertelen: {e}")

        self.display_image = None
        self.original_image = None

        # Buttons
        self.start_btn = QPushButton("▶ Start picking")
        self.pause_btn = QPushButton("⏸ Pause")
        self.stop_btn = QPushButton("🛑 STOP")
        self.prev_btn = QPushButton("◀ Előző")
        self.finish_btn = QPushButton("✓ Finish")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.pause_btn)
        button_layout.addWidget(self.stop_btn)

        layout.addLayout(button_layout)
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.finish_btn)

        self.setLayout(layout)

        # Connect buttons
        self.start_btn.clicked.connect(self.start_picking)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.stop_btn.clicked.connect(self.stop_picking)
        self.finish_btn.clicked.connect(self.on_finish)

        self._picking_active = False
        self._picking_paused = False

        self._load_image_from_context()

    def _load_image_from_context(self):
        if self.context.image is not None:
            self.original_image = self.context.image.copy()
            self.display_image = self.original_image.copy()
            self.update_image_display()
        else:
            self.log_box.append("[HIBA] ROI kép nem elérhető a context-ben.")

    def update_image_display(self, current_index=None):
        if self.original_image is None:
            return

        image = self.original_image.copy()

        for i, (x, y) in enumerate(self.context.roi_points):
            color = (0, 0, 255) if i == current_index else (0, 0, 0)
            cv2.drawMarker(image, (x, y), color, markerType=cv2.MARKER_TILTED_CROSS, markerSize=8, thickness=2)

        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image).scaled(
            self.image_label.width(), self.image_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        self.image_label.setPixmap(pixmap)

    def delay(self, ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec_()

    def start_picking(self):
        roi_points = self.context.roi_points or []
        if not roi_points:
            self.log_box.append("[HIBA] Nincsenek ROI pontok.")
            return

        if not self.command_sender or not self.g_control:
            self.log_box.append("[HIBA] Gépvezérlő vagy küldő nincs beállítva.")
            return

        if not self.g_control.connected:
            self.log_box.append("[INFO] Automatikus újracsatlakozás...")
            try:
                self.g_control.autoconnect()
            except Exception as e:
                self.log_box.append(f"[HIBA] Autoconnect hiba: {e}")
                return
        else:
            try:
                port = self.g_control.ser.port if self.g_control.ser else "ismeretlen port"
                self.log_box.append(f"[INFO] Már csatlakozva ({port}).")
            except Exception as e:
                self.log_box.append(f"[HIBA] Port lekérdezése sikertelen: {e}")

        if not self.g_control.connected:
            self.log_box.append("[HIBA] A gép nem elérhető.")
            return

        self._picking_active = True
        self._picking_paused = False

        for i, (x, y) in enumerate(roi_points):
            if not self._picking_active:
                self.log_box.append("[INFO] Pipettázás megszakítva.")
                return

            self.log_box.append(f"[LÉPÉS] {i + 1}. ROI → X:{x}, Y:{y}")
            self.command_sender.sendCommand.emit(f"G0 X{x} Y{y} F3000\n")
            self.update_image_display(current_index=i)
            QApplication.processEvents()

            for _ in range(30):  # 3 seconds total, 100ms intervals
                if not self._picking_active:
                    self.log_box.append("[INFO] Pipettázás megszakítva a késleltetés közben.")
                    return
                while self._picking_paused:
                    QApplication.processEvents()
                    self.delay(100)
                QApplication.processEvents()
                self.delay(100)

        self.log_box.append("[KÉSZ] Összes ROI pozíció meglátogatva.")

    def toggle_pause(self):
        self._picking_paused = not self._picking_paused
        state = "⏸ Szünet" if self._picking_paused else "▶ Folytatás"
        self.log_box.append(f"[INFO] {state}")

    def stop_picking(self):
        if self._picking_active:
            self._picking_active = False
            self.log_box.append("[INFO] Pipettázás manuálisan leállítva.")

    def on_finish(self):
        self._picking_active = False
        self.log_box.append("[INFO] Kézi pipettázás befejezve.")
        self.finished.emit()

    def closeEvent(self, event):
        if self._picking_active:
            self._picking_active = False
            self._picking_paused = False
            self.log_box.append("[INFO] Ablak bezárva — pipettázás megszakítva.")
        event.accept()
