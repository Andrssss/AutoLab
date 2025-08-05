import cv2
from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QImage, QPixmap
from File_managers import config_manager  # ne töröld ki, kell
import platform
from functools import partial


class CameraSettingsDialog(QDialog):
    def __init__(self, camera_index, zoom_level, zoom_offset_x, zoom_offset_y, blur_enabled, gain, exposure,
                 parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.zoom_level = zoom_level
        self.zoom_offset_x = zoom_offset_x
        self.zoom_offset_y = zoom_offset_y
        self.blur_enabled = blur_enabled
        self.gain = gain
        self.exposure = exposure

        self.setWindowTitle("Kamera Beállítások")
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            print("[HIBA] Nem sikerült megnyitni a kamerát.")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.current_frame = None

        self.label_preview = QLabel("Camera Preview")
        self.label_preview.setFixedSize(400, 300)
        self.label_preview.setStyleSheet("background-color: black;")

        # Érték kijelzők
        self.label_gain = QLabel(f"GAIN: {self.gain:.1f}")
        self.label_expo = QLabel(f"EXPO: {self.exposure:.1f}")

        self.btn_reset = QPushButton("Reset")
        # Lépés 1: UI felépítés
        self._create_buttons()
        self._setup_layout()

        # Lépés 2: Interakciók, időzítők beállítása
        self._setup_timers_and_connections()

        self.timer.start(30)

    def _create_buttons(self):
        self.btn_focus_up = QPushButton("ZOOM IN")
        self.btn_focus_down = QPushButton("ZOOM OUT")
        self.btn_blur = QPushButton("Blur")

        self.btn_gain_up = QPushButton("GAIN +")
        self.btn_gain_down = QPushButton("GAIN -")

        self.btn_expo_up = QPushButton("EXPO +")
        self.btn_expo_down = QPushButton("EXPO -")

        self.btn_left = QPushButton("←")
        self.btn_right = QPushButton("→")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")

    def _setup_layout(self):
        layout = QVBoxLayout()
        layout.addWidget(self.label_preview)

        # Zoom / Blur
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(self.btn_focus_down)
        zoom_layout.addWidget(self.btn_focus_up)
        zoom_layout.addWidget(self.btn_blur)
        zoom_layout.addWidget(self.btn_reset)
        layout.addLayout(zoom_layout)

        # Gain
        gain_btn_layout = QHBoxLayout()
        gain_btn_layout.addWidget(self.btn_gain_down)
        gain_btn_layout.addWidget(self.btn_gain_up)
        layout.addLayout(gain_btn_layout)

        gain_display = QHBoxLayout()
        gain_display.addWidget(self.label_gain)
        layout.addLayout(gain_display)

        # Exposure
        expo_btn_layout = QHBoxLayout()
        expo_btn_layout.addWidget(self.btn_expo_down)
        expo_btn_layout.addWidget(self.btn_expo_up)
        layout.addLayout(expo_btn_layout)

        expo_display = QHBoxLayout()
        expo_display.addWidget(self.label_expo)
        layout.addLayout(expo_display)




        # Pan nyilak
        v_pan = QVBoxLayout()
        h_pan = QHBoxLayout()
        v_pan.addWidget(self.btn_up, alignment=Qt.AlignCenter)
        h_pan.addWidget(self.btn_left)
        h_pan.addWidget(self.btn_right)
        v_pan.addLayout(h_pan)
        v_pan.addWidget(self.btn_down, alignment=Qt.AlignCenter)
        layout.addLayout(v_pan)



        self.setLayout(layout)

    def _setup_timers_and_connections(self):
        # --- Zoom ---
        self.zoom_timers = {
            "in": QTimer(self),
            "out": QTimer(self)
        }
        self.zoom_timers["in"].timeout.connect(self.increase_focus)
        self.zoom_timers["out"].timeout.connect(self.decrease_focus)
        self.zoom_timers["in"].setInterval(50)
        self.zoom_timers["out"].setInterval(50)
        self.btn_focus_up.pressed.connect(self.zoom_timers["in"].start)
        self.btn_focus_up.released.connect(self.zoom_timers["in"].stop)
        self.btn_focus_down.pressed.connect(self.zoom_timers["out"].start)
        self.btn_focus_down.released.connect(self.zoom_timers["out"].stop)

        # --- Gain ---
        self.gain_timers = {
            "up": QTimer(self),
            "down": QTimer(self)
        }
        self.gain_timers["up"].timeout.connect(self.increase_gain)
        self.gain_timers["down"].timeout.connect(self.decrease_gain)
        self.gain_timers["up"].setInterval(50)
        self.gain_timers["down"].setInterval(50)
        self.btn_gain_up.pressed.connect(self.gain_timers["up"].start)
        self.btn_gain_up.released.connect(self.gain_timers["up"].stop)
        self.btn_gain_down.pressed.connect(self.gain_timers["down"].start)
        self.btn_gain_down.released.connect(self.gain_timers["down"].stop)

        # --- Exposure ---
        self.expo_timers = {
            "up": QTimer(self),
            "down": QTimer(self)
        }
        self.expo_timers["up"].timeout.connect(self.increase_exposure)
        self.expo_timers["down"].timeout.connect(self.decrease_exposure)
        self.expo_timers["up"].setInterval(100)
        self.expo_timers["down"].setInterval(100)
        self.btn_expo_up.pressed.connect(self.expo_timers["up"].start)
        self.btn_expo_up.released.connect(self.expo_timers["up"].stop)
        self.btn_expo_down.pressed.connect(self.expo_timers["down"].start)
        self.btn_expo_down.released.connect(self.expo_timers["down"].stop)

        # --- Pan ---
        self.pan_timers = {
            "left": QTimer(self),
            "right": QTimer(self),
            "up": QTimer(self),
            "down": QTimer(self)
        }
        # Timer beállítása és működés hozzárendelés
        for direction in self.pan_timers:
            timer = self.pan_timers[direction]
            timer.setInterval(50)
            timer.timeout.connect(partial(self.pan_view, direction))  # FIX: direction lezárása

        self.btn_left.pressed.connect(lambda: self.pan_timers["left"].start())
        self.btn_left.released.connect(lambda: self.pan_timers["left"].stop())
        self.btn_right.pressed.connect(lambda: self.pan_timers["right"].start())
        self.btn_right.released.connect(lambda: self.pan_timers["right"].stop())
        self.btn_up.pressed.connect(lambda: self.pan_timers["up"].start())
        self.btn_up.released.connect(lambda: self.pan_timers["up"].stop())
        self.btn_down.pressed.connect(lambda: self.pan_timers["down"].start())
        self.btn_down.released.connect(lambda: self.pan_timers["down"].stop())
        self.btn_reset.clicked.connect(self.reset_to_defaults)

        # --- Egykattintásos funkciók ---
        self.btn_blur.clicked.connect(self.apply_blur)
        self.btn_gain_up.clicked.connect(self.increase_gain)
        self.btn_gain_down.clicked.connect(self.decrease_gain)
        self.btn_expo_up.clicked.connect(self.increase_exposure)
        self.btn_expo_down.clicked.connect(self.decrease_exposure)
        self.btn_focus_up.clicked.connect(self.increase_focus)
        self.btn_focus_down.clicked.connect(self.decrease_focus)
        self.btn_reset.clicked.connect(self.reset_to_defaults)

    def update_frame(self):
        if self.cap and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_GAIN, self.gain) # Minden egyes képkocka frissítés előtt beállítja a gain értéket
            ret, frame = self.cap.read() # Lekér egy új képkockát a kamerából.
            if ret: # ret azt jelzi, sikerült-e olvasni (True vagy False).
                self.current_frame = frame
                frame_to_show = self.apply_zoom_and_blur(frame)
                rgb_image = cv2.cvtColor(frame_to_show, cv2.COLOR_BGR2RGB) # OpenCV alapból BGR színteret használ, de a Qt QImage RGB-t vár. Ez az átalakítás elengedhetetlen.
                h, w, ch = rgb_image.shape # height, width, channels
                bytes_per_line = ch * w # Egy sorban hány byte található.
                                        # Ez fontos infó a QImage számára, mert tudnia kell, hogy hol ér véget egy sor.
                qimg = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg).scaled(self.label_preview.size(), Qt.KeepAspectRatio)
                self.label_preview.setPixmap(pixmap) # Végül frissíti a QLabelet, hogy mutassa az élő képet.



    def apply_zoom_and_blur(self, frame):
        frame = self.apply_zoom(frame)
        frame = self.apply_blurr(frame)
        return frame

    def apply_zoom(self, frame):
        h, w = frame.shape[:2]

        if self.zoom_level > 1.0:
            new_w = int(w / self.zoom_level)
            new_h = int(h / self.zoom_level)

            center_x = w // 2 + int(self.zoom_offset_x * (w // 2 - new_w // 2))
            center_y = h // 2 + int(self.zoom_offset_y * (h // 2 - new_h // 2))

            x1 = max(center_x - new_w // 2, 0)
            y1 = max(center_y - new_h // 2, 0)
            x2 = min(x1 + new_w, w)
            y2 = min(y1 + new_h, h)

            frame = frame[y1:y2, x1:x2]

        return frame

    def reset_to_defaults(self):
        self.zoom_level = 1.0
        self.zoom_offset_x = 0.0
        self.zoom_offset_y = 0.0
        self.blur_enabled = False
        self.gain = 0.0
        self.exposure = -4.0

        if self.cap:
            self.cap.set(cv2.CAP_PROP_GAIN, self.gain)
            if platform.system() == "Linux":
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
            else:
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
            self.cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)

        self.label_gain.setText(f"GAIN: {self.gain:.1f}")
        self.label_expo.setText(f"EXPO: {self.exposure:.1f}")

        print("[RESET] Minden érték alaphelyzetbe állítva.")

    def apply_blurr(self, frame):
        if self.blur_enabled:
            frame = cv2.GaussianBlur(frame, (31, 31), 0)  # drasztikusabb blur
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


    def increase_gain(self):
        self.gain = min(self.gain + 1.0, 255.0)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_GAIN, self.gain)
        # A GUI-n megjelenő `QLabel`-t frissíti, hogy lásd, aktuálisan mennyi a gai
        self.label_gain.setText(f"GAIN: {self.gain:.1f}")

    def decrease_gain(self):
        self.gain = max(self.gain - 1.0, -255.0)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_GAIN, self.gain)
        self.label_gain.setText(f"GAIN: {self.gain:.1f}")


    def increase_exposure(self):
        self.exposure = min(self.exposure + 1.0, 13.0)
        if self.cap:
            if platform.system() == "Linux":
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)  # Linuxon 1 a manuális mód
            else:
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # Windowson 0.25
            self.cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)
        self.label_expo.setText(f"EXPO: {self.exposure:.1f}")

    def decrease_exposure(self):
        self.exposure = max(self.exposure - 1.0, -13.0)
        if self.cap:
            if platform.system() == "Linux":
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)  # Linux
            else:
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # Windows
            self.cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)
        self.label_expo.setText(f"EXPO: {self.exposure:.1f}")

    def closeEvent(self, event):
        self.timer.stop()
        if self.cap:
            self.cap.release()
        from File_managers import config_manager  # ha még nem volt

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

