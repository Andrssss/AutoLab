import cv2
from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QImage, QPixmap
from file_managers import config_manager  # ha még nem volt


class CameraSettingsDialog(QDialog):
    def __init__(self, camera_index, zoom_level, zoom_offset_x, zoom_offset_y, blur_enabled, gain,exposure, parent=None):
        super().__init__(parent)
        self.zoom_level = zoom_level
        self.gain = gain
        self.zoom_offset_x = zoom_offset_x
        self.zoom_offset_y = zoom_offset_y
        self.blur_enabled = blur_enabled
        self.exposure = exposure  # amit a paraméterként kapsz vagy .get("exposure", -6.0)

        self.setWindowTitle("Kamera Beállítások")
        self.camera_index = camera_index

        self.cap = cv2.VideoCapture(self.camera_index)  # most már biztonságos!
        if not self.cap.isOpened():
            print("[HIBA] Nem sikerült megnyitni a kamerát a settings dialogban.")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.current_frame = None

        # Előnézet
        self.label_preview = QLabel("Camera Preview")
        self.label_preview.setFixedSize(400, 300)
        self.label_preview.setStyleSheet("background-color: black;")

        # Gombok
        self.btn_focus_up = QPushButton("ZOOM IN")
        self.btn_focus_down = QPushButton("ZOOM OUT")


        # Egyszeri kattintásra is működjön
        self.btn_focus_up.clicked.connect(self.increase_focus)
        self.btn_focus_down.clicked.connect(self.decrease_focus)




        # BLUR -------------------------------------------------------------
        self.btn_blur = QPushButton("Blur")
        self.btn_blur.clicked.connect(self.apply_blur)



        layout = QVBoxLayout()
        layout.addWidget(self.label_preview)

        controls = QHBoxLayout()
        controls.addWidget(self.btn_focus_down)
        controls.addWidget(self.btn_focus_up)
        controls.addWidget(self.btn_blur)
        layout.addLayout(controls)

        # Nyilak panorámázáshoz
        pan_layout = QHBoxLayout()
        self.btn_left = QPushButton("←")
        self.btn_right = QPushButton("→")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")

        self.btn_left.clicked.connect(lambda: self.pan_view("left"))
        self.btn_right.clicked.connect(lambda: self.pan_view("right"))
        self.btn_up.clicked.connect(lambda: self.pan_view("up"))
        self.btn_down.clicked.connect(lambda: self.pan_view("down"))

        self.pan_timers = {
            "left": QTimer(self),
            "right": QTimer(self),
            "up": QTimer(self),
            "down": QTimer(self)
        }

        for direction, timer in self.pan_timers.items():
            timer.setInterval(100)  # kb. 10x/sec
            timer.timeout.connect(lambda dir=direction: self.pan_view(dir))

        self.btn_left.pressed.connect(lambda: self.pan_timers["left"].start())
        self.btn_left.released.connect(lambda: self.pan_timers["left"].stop())

        self.btn_right.pressed.connect(lambda: self.pan_timers["right"].start())
        self.btn_right.released.connect(lambda: self.pan_timers["right"].stop())

        self.btn_up.pressed.connect(lambda: self.pan_timers["up"].start())
        self.btn_up.released.connect(lambda: self.pan_timers["up"].stop())

        self.btn_down.pressed.connect(lambda: self.pan_timers["down"].start())
        self.btn_down.released.connect(lambda: self.pan_timers["down"].stop())

        self.zoom_timers = {
            "in": QTimer(self),
            "out": QTimer(self)
        }

        self.zoom_timers["in"].setInterval(100)
        self.zoom_timers["in"].timeout.connect(self.increase_focus)

        self.zoom_timers["out"].setInterval(100)
        self.zoom_timers["out"].timeout.connect(self.decrease_focus)

        # Hosszú nyomásra: pressed / released
        self.btn_focus_up.pressed.connect(lambda: self.zoom_timers["in"].start())
        self.btn_focus_up.released.connect(lambda: self.zoom_timers["in"].stop())

        self.btn_focus_down.pressed.connect(lambda: self.zoom_timers["out"].start())
        self.btn_focus_down.released.connect(lambda: self.zoom_timers["out"].stop())

        # GAIN gombok
        self.btn_gain_up = QPushButton("GAIN +")
        self.btn_gain_down = QPushButton("GAIN -")

        self.gain_timers = {
            "up": QTimer(self),
            "down": QTimer(self)
        }
        self.gain_timers["up"].setInterval(100)
        self.gain_timers["up"].timeout.connect(self.increase_gain)
        self.gain_timers["down"].setInterval(100)
        self.gain_timers["down"].timeout.connect(self.decrease_gain)

        self.btn_gain_up.pressed.connect(lambda: self.gain_timers["up"].start())
        self.btn_gain_up.released.connect(lambda: self.gain_timers["up"].stop())

        self.btn_gain_down.pressed.connect(lambda: self.gain_timers["down"].start())
        self.btn_gain_down.released.connect(lambda: self.gain_timers["down"].stop())


        # ======= EXPOSURE beállítás =======
        self.exposure = self.cap.get(cv2.CAP_PROP_EXPOSURE) or -6.0  # alapérték, ha nincs

        self.btn_expo_up = QPushButton("EXPO +")
        self.btn_expo_down = QPushButton("EXPO -")
        self.btn_expo_up.clicked.connect(self.increase_exposure)
        self.btn_expo_down.clicked.connect(self.decrease_exposure)

        expo_layout = QHBoxLayout()
        expo_layout.addWidget(self.btn_expo_down)
        expo_layout.addWidget(self.btn_expo_up)
        layout.addLayout(expo_layout)

        # ======= GAIN & EXPO kijelzők =======
        value_layout = QHBoxLayout()
        self.label_gain = QLabel(f"GAIN: {self.gain:.1f}")
        self.label_expo = QLabel(f"EXPO: {self.exposure:.1f}")
        value_layout.addWidget(self.label_gain)
        value_layout.addWidget(self.label_expo)
        layout.addLayout(value_layout)

        gain_layout = QHBoxLayout()
        gain_layout.addWidget(self.btn_gain_down)
        gain_layout.addWidget(self.btn_gain_up)
        layout.addLayout(gain_layout)


        # Elrendezés: ↑ középen, ← → oldalt
        v_pan = QVBoxLayout()
        h_pan = QHBoxLayout()
        v_pan.addWidget(self.btn_up, alignment=Qt.AlignCenter)
        h_pan.addWidget(self.btn_left)
        h_pan.addWidget(self.btn_right)
        v_pan.addLayout(h_pan)
        v_pan.addWidget(self.btn_down, alignment=Qt.AlignCenter)

        layout.addLayout(v_pan)

        self.setLayout(layout)
        self.timer.start(30)

    def update_frame(self):
        if self.cap and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_GAIN, self.gain)
            ret, frame = self.cap.read()
            if ret:
                self.current_frame = frame
                frame_to_show = self.apply_zoom_and_blur(frame)
                rgb_image = cv2.cvtColor(frame_to_show, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qimg = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg).scaled(self.label_preview.size(), Qt.KeepAspectRatio)
                self.label_preview.setPixmap(pixmap)

    def apply_zoom_and_blur(self, frame):
        h, w = frame.shape[:2]

        if self.zoom_level > 1.0:
            new_w, new_h = int(w / self.zoom_level), int(h / self.zoom_level)

            # 🧠 Offszetek alapján számolt középpont
            center_x = w // 2 + int(self.zoom_offset_x * (w // 2 - new_w // 2))
            center_y = h // 2 + int(self.zoom_offset_y * (h // 2 - new_h // 2))

            x1 = max(center_x - new_w // 2, 0)
            y1 = max(center_y - new_h // 2, 0)
            x2 = min(x1 + new_w, w)
            y2 = min(y1 + new_h, h)

            frame = frame[y1:y2, x1:x2]

        # Blur, ha be van kapcsolva
        if self.blur_enabled:
            frame = cv2.GaussianBlur(frame, (15, 15), 0)
        return frame

    def increase_focus(self):
        self.zoom_level = min(self.zoom_level + 0.1, 5.0)
        print(f"[ZOOM] Zoom in → {self.zoom_level:.1f}x")

    def decrease_focus(self):
        self.zoom_level = max(self.zoom_level - 0.1, 1.0)
        print(f"[ZOOM] Zoom out → {self.zoom_level:.1f}x")

    def apply_blur(self):
        self.blur_enabled = not self.blur_enabled
        print(f"[BLUR] Blur {'bekapcsolva' if self.blur_enabled else 'kikapcsolva'}")

    def pan_view(self, direction):
        step = 0.05
        if self.zoom_level <= 1.0:
            print("[INFO] Nem lehet panorámázni alap zoomnál.")
            return

        if direction == "left":
            self.zoom_offset_x = max(self.zoom_offset_x - step, -1.0)
        elif direction == "right":
            self.zoom_offset_x = min(self.zoom_offset_x + step, 1.0)
        elif direction == "up":
            self.zoom_offset_y = max(self.zoom_offset_y - step, -1.0)
        elif direction == "down":
            self.zoom_offset_y = min(self.zoom_offset_y + step, 1.0)

        print(f"[PAN] X: {self.zoom_offset_x:.2f}, Y: {self.zoom_offset_y:.2f}")

    def increase_gain(self):
        self.gain = min(self.gain + 1.0, 255.0)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_GAIN, self.gain)
        self.label_gain.setText(f"GAIN: {self.gain:.1f}")
        print(f"[GAIN] Növelve: {self.gain:.1f}")

    def decrease_gain(self):
        self.gain = max(self.gain - 1.0, -255.0)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_GAIN, self.gain)
        self.label_gain.setText(f"GAIN: {self.gain:.1f}")
        print(f"[GAIN] Csökkentve: {self.gain:.1f}")

    def increase_exposure(self):
        self.exposure = min(self.exposure + 1.0, 13.0)  # 0.0 = max expó (gyártófüggő)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # manuális mód (Windows, UVC)
            self.cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)
        print(f"[EXPO] Növelve: {self.exposure:.1f}")
        self.label_expo.setText(f"EXPO: {self.exposure:.1f}")

    def decrease_exposure(self):
        self.exposure = max(self.exposure - 1.0, -13.0)  # túl kis értéken fekete lesz
        if self.cap:
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
            self.cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)
        print(f"[EXPO] Csökkentve: {self.exposure:.1f}")
        self.label_expo.setText(f"EXPO: {self.exposure:.1f}")

    def closeEvent(self, event):
        self.timer.stop()
        if self.cap:
            self.cap.release()
        from file_managers import config_manager  # ha még nem volt

        settings_data = {
            "zoom_level": self.zoom_level,
            "offset_x": self.zoom_offset_x,
            "offset_y": self.zoom_offset_y,
            "blur": self.blur_enabled,
            "gain": self.gain,
            "exposure": self.exposure
        }
        config_manager.save_camera_settings(self.camera_index, settings_data)
        self.result = settings_data

        event.accept()

