from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QSlider, QHBoxLayout,
    QFileDialog, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, pyqtSignal
from Image_processing.petri_detector import PetriDetector
from Image_processing.overlay_draw import draw_mask_outline, blend_mask_fill
import cv2


class StepCaptureWidget(QWidget):
    go_to_start = pyqtSignal()

    def __init__(self, context, image_path=None, log_widget=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bacterial Analyzer")

        self.context = context
        self.image_path = image_path
        self.log_widget = log_widget

        self.original_image = None
        self.processed_image = None
        self.petri_mask = None
        self.petri_detector = PetriDetector(mode="round")

        # ---- Visualization style (BGR) ----
        self.overlay_color = (255, 255, 0)   # cyan in BGR
        self.overlay_thickness = 2
        self.overlay_fill_alpha = 0.0        # 0 → only outline; >0 → translucent fill

        self.initUI()

        if self.image_path:
            self.load_and_process_image(self.image_path)

    def initUI(self):
        layout = QVBoxLayout()

        # Image display
        self.image_label = QLabel("Loading image...")
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)

        # Open image button
        btn_open = QPushButton("Open Image")
        btn_open.clicked.connect(self.open_image)
        layout.addWidget(btn_open)

        # --- Petri shape selector (Round / Rectangle / Auto) ---
        shape_layout = QHBoxLayout()
        shape_layout.addWidget(QLabel("Petri shape:"))

        self.radio_round = QRadioButton("Round")
        self.radio_rectangle = QRadioButton("Rectangle")
        self.radio_auto = QRadioButton("Auto")
        self.radio_round.setChecked(True)

        self.shape_group = QButtonGroup(self)
        self.shape_group.addButton(self.radio_round)
        self.shape_group.addButton(self.radio_rectangle)
        self.shape_group.addButton(self.radio_auto)

        self.radio_round.toggled.connect(lambda checked: self.on_shape_changed("round", checked))
        self.radio_rectangle.toggled.connect(lambda checked: self.on_shape_changed("rectangle", checked))
        self.radio_auto.toggled.connect(lambda checked: self.on_shape_changed("auto", checked))

        shape_layout.addWidget(self.radio_round)
        shape_layout.addWidget(self.radio_rectangle)
        shape_layout.addWidget(self.radio_auto)
        shape_layout.addStretch()
        layout.addLayout(shape_layout)

        # Petri detection sliders
        circle_layout = QHBoxLayout()
        self.circle_blur_slider = QSlider(Qt.Horizontal)
        self.circle_blur_slider.setMinimum(1)
        self.circle_blur_slider.setMaximum(31)
        self.circle_blur_slider.setValue(7)
        self.circle_blur_slider.setSingleStep(2)
        self.circle_blur_slider.setTickPosition(QSlider.TicksBelow)
        self.circle_blur_slider.setToolTip("Gaussian blur kernel size (odd). Higher = smoother.")
        self.circle_blur_slider.valueChanged.connect(self.update_petri_params)
        circle_layout.addWidget(QLabel("Petri blur"))
        circle_layout.addWidget(self.circle_blur_slider)

        self.circle_slider = QSlider(Qt.Horizontal)
        self.circle_slider.setMinimum(10)
        self.circle_slider.setMaximum(100)
        self.circle_slider.setValue(30)
        self.circle_slider.setTickPosition(QSlider.TicksBelow)
        self.circle_slider.setToolTip("Detection sensitivity. Higher = stricter edges.")
        self.circle_slider.valueChanged.connect(self.update_petri_params)
        circle_layout.addWidget(QLabel("Petri sensitivity"))
        circle_layout.addWidget(self.circle_slider)
        layout.addLayout(circle_layout)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self.go_to_start.emit)
        self.next_btn = QPushButton("Next ▶")
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        layout.addLayout(nav_layout)

        self.setLayout(layout)
        self.layout = layout

    # --- shape change handler ---
    def on_shape_changed(self, mode: str, checked: bool):
        if not checked:
            return
        self.petri_detector.set_mode(mode)
        if self.log_widget:
            self.log_widget.append_log(f"[INFO] Petri detection mode set to: {mode}")
        if self.original_image is not None:
            # force re-detect on mode change
            self.update_petri_params(force_detect=True)

    def open_image(self):
        default_dir = r"C:\\Users\\Public\\Pictures\\MyCaptures"
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select image", default_dir, "Images (*.png *.xpm *.jpg *.bmp)"
        )
        if file_path:
            self.load_and_process_image(file_path)

    def update_petri_params(self, force_detect=False):
        blur = self.circle_blur_slider.value()
        sensitivity = self.circle_slider.value()
        if blur % 2 == 0:
            blur += 1

        self.petri_detector.set_params(blur, sensitivity)

        if self.original_image is not None:
            if force_detect or self.petri_mask is None:
                petri_mask = self.petri_detector.detect(self.original_image)
                if petri_mask is None or cv2.countNonZero(petri_mask) == 0:
                    if self.log_widget:
                        self.log_widget.append_log("[WARNING] Petri detection failed. Showing original image.")
                    self.petri_mask = None
                    self.processed_image = None
                    self.display_image(self.original_image)
                    self.image_label.repaint()
                    return
                else:
                    self.petri_mask = petri_mask
                    if self.log_widget:
                        metrics = self.petri_detector.get_last_metrics()
                        picked = metrics.get("picked", metrics.get("detector", "unknown"))
                        score = metrics.get("score", None)
                        if score is not None:
                            self.log_widget.append_log(f"[DEBUG] Detector={picked}, Score={score:.2f}")
                        else:
                            self.log_widget.append_log(f"[DEBUG] Detector={picked}")

            # ---- draw via overlay helpers ----
            if self.overlay_fill_alpha > 0.0:
                self.processed_image = blend_mask_fill(
                    self.original_image, self.petri_mask,
                    color=self.overlay_color,
                    alpha=float(self.overlay_fill_alpha),
                    outline_color=self.overlay_color,
                    outline_thickness=int(self.overlay_thickness),
                )
            else:
                self.processed_image = self.original_image.copy()
                draw_mask_outline(
                    self.processed_image, self.petri_mask,
                    color=self.overlay_color,
                    thickness=int(self.overlay_thickness),
                )

            self.display_image(self.processed_image)

    def display_image(self, image):
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image).scaled(640, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pixmap)

    def load_and_process_image(self, path):
        self.image_path = path
        self.original_image = cv2.imread(path)
        if self.original_image is not None:
            self.petri_mask = None
            self.update_petri_params(force_detect=True)

    def get_image(self):
        return self.original_image

    def get_mask(self):
        return self.petri_mask

    def save_to_context(self):
        self.context.image = self.original_image
        self.context.mask = self.petri_mask
        self.context.filtered_image = self.processed_image

        # Save Petri detection parameters + shape mode
        shape_mode = "auto" if self.radio_auto.isChecked() else (
            "rectangle" if self.radio_rectangle.isChecked() else "round")
        self.context.settings["petri_params"] = {
            "circle_blur": self.circle_blur_slider.value(),
            "circle_sensitivity": self.circle_slider.value(),
            "shape_mode": shape_mode,
            "overlay_color_bgr": self.overlay_color,
            "overlay_thickness": self.overlay_thickness,
            "overlay_fill_alpha": self.overlay_fill_alpha,
        }

        self.context.analysis = {
            "preview_image": self.processed_image,
            "petri_only": True
        }
        if self.log_widget:
            self.log_widget.append_log(
                f"[DEBUG] StepCapture saved Petri detection settings: {self.context.settings['petri_params']}"
            )

    def load_from_context(self):
        petri_params = self.context.settings.get("petri_params", {})
        self.circle_blur_slider.setValue(petri_params.get("circle_blur", 7))
        self.circle_slider.setValue(petri_params.get("circle_sensitivity", 30))

        # restore mode
        mode = petri_params.get("shape_mode", "round")
        if mode == "auto":
            self.radio_auto.setChecked(True)
        elif mode == "rectangle":
            self.radio_rectangle.setChecked(True)
        else:
            self.radio_round.setChecked(True)
        self.petri_detector.set_mode(mode)

        # restore overlay style if present
        self.overlay_color = tuple(petri_params.get("overlay_color_bgr", self.overlay_color))
        self.overlay_thickness = int(petri_params.get("overlay_thickness", self.overlay_thickness))
        self.overlay_fill_alpha = float(petri_params.get("overlay_fill_alpha", self.overlay_fill_alpha))

        if self.context.image is not None:
            self.original_image = self.context.image
        if self.context.mask is not None:
            self.petri_mask = self.context.mask
            self.update_petri_params()



