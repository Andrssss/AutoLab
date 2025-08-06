from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QSlider, QHBoxLayout, QFileDialog
from PyQt5.QtCore import Qt, pyqtSignal
from Image_processing.petri_detector import PetriDetector
import cv2

class StepCaptureWidget(QWidget):
    go_to_start = pyqtSignal()

    def __init__(self, context, image_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bacterial Analyzer")

        self.context = context
        self.image_path = image_path
        self.original_image = None
        self.processed_image = None
        self.petri_mask = None
        self.petri_detector = PetriDetector()

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

        # Petri detection sliders
        circle_layout = QHBoxLayout()
        self.circle_blur_slider = QSlider(Qt.Horizontal)
        self.circle_blur_slider.setMinimum(1)
        self.circle_blur_slider.setMaximum(31)
        self.circle_blur_slider.setValue(7)
        self.circle_blur_slider.setSingleStep(2)
        self.circle_blur_slider.setTickPosition(QSlider.TicksBelow)
        self.circle_blur_slider.valueChanged.connect(self.update_petri_params)
        circle_layout.addWidget(QLabel("Petri blur"))
        circle_layout.addWidget(self.circle_blur_slider)

        self.circle_slider = QSlider(Qt.Horizontal)
        self.circle_slider.setMinimum(10)
        self.circle_slider.setMaximum(100)
        self.circle_slider.setValue(30)
        self.circle_slider.setTickPosition(QSlider.TicksBelow)
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

    def open_image(self):
        default_dir = r"C:\\Users\\Public\\Pictures\\MyCaptures"
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select image", default_dir, "Images (*.png *.xpm *.jpg *.bmp)"
        )
        if file_path:
            self.image_path = file_path
            self.original_image = cv2.imread(file_path)
            self.petri_mask = None
            self.update_petri_params(force_detect=True)

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
                    print("[WARNING] Petri detection failed. Showing original image.")
                    self.petri_mask = None
                    self.processed_image = None
                    self.display_image(self.original_image)
                    self.image_label.repaint()
                    return
                else:
                    self.petri_mask = petri_mask

            # Draw petri mask contour on top of original image
            self.processed_image = self.original_image.copy()
            contours, _ = cv2.findContours(self.petri_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(self.processed_image, contours, -1, (0, 255, 255), 2)  # Cyan color
            self.display_image(self.processed_image)

    def display_image(self, image):
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image).scaled(640, 480, Qt.KeepAspectRatio)
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

        # 🟢 Save Petri detection parameters
        self.context.settings["petri_params"] = {
            "circle_blur": self.circle_blur_slider.value(),
            "circle_sensitivity": self.circle_slider.value()
        }

        self.context.analysis = {
            "preview_image": self.processed_image,
            "petri_only": True
        }

        print("[DEBUG] StepCapture saved Petri detection settings:", self.context.settings["petri_params"])

    def load_from_context(self):
        petri_params = self.context.settings.get("petri_params", {})
        self.circle_blur_slider.setValue(petri_params.get("circle_blur", 7))
        self.circle_slider.setValue(petri_params.get("circle_sensitivity", 30))

        if self.context.image is not None:
            self.original_image = self.context.image
        if self.context.mask is not None:
            self.petri_mask = self.context.mask
            self.update_petri_params()

