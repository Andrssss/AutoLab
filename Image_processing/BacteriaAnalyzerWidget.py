# main widget structure for separation
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QSlider, QHBoxLayout, QFileDialog
from PyQt5.QtCore import Qt
from .bac_detector import BacteriaDetector
from .petri_detector import PetriDetector
import cv2

class BacteriaAnalyzerWidget(QWidget):
    def __init__(self, image_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bacterial Analyzer")

        # Attribútumok
        self.image_path = image_path
        self.original_image = None
        self.processed_image = None
        self.petri_mask = None
        self.petri_detector = PetriDetector()
        self.bac_detector = BacteriaDetector()

        self.hue_ranges = [(0, 30), (30, 90), (90, 150), (150, 179)]
        self.size_ranges = [(100, 500), (500, 1500), (1500, 99999)]

        self.initUI()
        if self.image_path:
            self.load_and_process_image(self.image_path)

    def initUI(self):
        layout = QVBoxLayout()

        self.image_label = QLabel("Loading image...")
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)

        btn_open = QPushButton("Open Image")
        btn_open.clicked.connect(self.open_image)
        layout.addWidget(btn_open)

        circle_layout = QHBoxLayout()
        self.circle_blur_slider = QSlider(Qt.Horizontal)
        self.circle_blur_slider.setMinimum(1)
        self.circle_blur_slider.setMaximum(31)
        self.circle_blur_slider.setValue(7)
        self.circle_blur_slider.setSingleStep(2)
        self.circle_blur_slider.setTickPosition(QSlider.TicksBelow)
        self.circle_blur_slider.valueChanged.connect(self.update_petri_params)
        circle_layout.addWidget(QLabel("Petri blur")) # Elmosási érték a kör detekcióhoz
        circle_layout.addWidget(self.circle_blur_slider)

        self.circle_slider = QSlider(Qt.Horizontal)
        self.circle_slider.setMinimum(10)
        self.circle_slider.setMaximum(100)
        self.circle_slider.setValue(30)
        self.circle_slider.setTickPosition(QSlider.TicksBelow)
        self.circle_slider.valueChanged.connect(self.update_petri_params)
        circle_layout.addWidget(QLabel("Petri sensitivity")) # Érzékenység Hough körkereséshez
        circle_layout.addWidget(self.circle_slider)
        layout.addLayout(circle_layout)

        size_layout = QHBoxLayout()
        self.min_size_slider = QSlider(Qt.Horizontal)
        self.min_size_slider.setMinimum(10)
        self.min_size_slider.setMaximum(3000)
        self.min_size_slider.setValue(100)
        self.min_size_slider.valueChanged.connect(self.update_bac_params)
        size_layout.addWidget(QLabel("Min size"))
        size_layout.addWidget(self.min_size_slider)

        self.max_size_slider = QSlider(Qt.Horizontal)
        self.max_size_slider.setMinimum(10)
        self.max_size_slider.setMaximum(10000)
        self.max_size_slider.setValue(1500)
        self.max_size_slider.valueChanged.connect(self.update_bac_params)
        size_layout.addWidget(QLabel("Max size"))
        size_layout.addWidget(self.max_size_slider)
        layout.addLayout(size_layout)
        self.setLayout(layout)

        self.split_thresh_slider = QSlider(Qt.Horizontal)
        self.split_thresh_slider.setMinimum(10)
        self.split_thresh_slider.setMaximum(1000)
        self.split_thresh_slider.setValue(1)  # default threshold (% of distance transform max)
        self.split_thresh_slider.valueChanged.connect(self.update_bac_params)

        split_layout = QHBoxLayout()
        split_layout.addWidget(QLabel("Split Sensitivity")) # Választó érzékenység (baktérium szétválasztásnál, pl. watershed)
        split_layout.addWidget(self.split_thresh_slider)
        layout.addLayout(split_layout)

    def open_image(self):
        default_dir = r"C:\Users\Public\Pictures\MyCaptures"
        file_path, _ = QFileDialog.getOpenFileName(self, "Select image", default_dir, "Images (*.png *.xpm *.jpg *.bmp)")
        if file_path:
            self.image_path = file_path
            self.original_image = cv2.imread(file_path)
            self.petri_mask = None  # Reset mask
            self.update_petri_params(force_detect=False)

    def update_petri_params(self, force_detect=False):
        blur = self.circle_blur_slider.value()
        sensitivity = self.circle_slider.value()
        if blur % 2 == 0: # cv2.GaussianBlur(img, (6, 6), 0) - nem fog működni, csak páratlan számokkal
            blur += 1

        self.petri_detector.set_params(blur, sensitivity)

        if self.original_image is not None:
            if force_detect or self.petri_mask is None:
                petri_mask = self.petri_detector.detect(self.original_image)

                # ha nincs kör, akkor eredeti képet jeleníti meg, jelezve, hogy nem detektálta.
                if petri_mask is None or cv2.countNonZero(petri_mask) == 0:
                    #cv2.countNonZero(petri_mask) == 0 --> Ez megszámolja a maszkban lévő nem nulla pixeleket. Ha az eredmény 0, akkor a maszk teljesen üres – tehát semmit nem fed le.
                    print("[WARNING] Petri detection failed. Showing original image.")
                    self.petri_mask = None
                    self.processed_image = None
                    self.display_image(self.original_image)
                    self.image_label.repaint()
                    return
                else:
                    self.petri_mask = petri_mask # petri csészével maszkolt kép

            # Draw petri preview
            # preview = self.original_image.copy()
            # contours, _ = cv2.findContours(self.petri_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            # cv2.drawContours(preview, contours, -1, (255, 255, 0), 2)
            # self.display_image(preview)
            # self.image_label.repaint()

            self.update_bac_params()

    def update_bac_params(self):
        if self.original_image is not None:
            if self.petri_mask is None:
                self.display_image(self.original_image)
            else:
                min_size = self.min_size_slider.value()
                max_size = self.max_size_slider.value()
                split_thresh = self.split_thresh_slider.value()

                self.size_ranges = [(min_size, max_size)]
                self.bac_detector.set_params(self.hue_ranges, self.size_ranges, split_thresh)

                masked_image = cv2.bitwise_and(self.original_image, self.original_image, mask=self.petri_mask)
                # it will get the masked picture
                detected = self.bac_detector.detect(masked_image, self.petri_mask)
                # detected = self.bac_detector.detect(self.original_image, self.petri_mask)

                # Csak a Petri kontúr kirajzolása az észlelt képre
                preview = detected.copy()
                contours, _ = cv2.findContours(self.petri_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(preview, contours, -1, (255, 255, 0), 2)  # Csak kontúr, nem kitöltés

                # Most ezt jelenítsd meg
                self.display_image(preview)


    def load_and_process_image(self, path):
        self.image_path = path
        self.original_image = cv2.imread(path)
        if self.original_image is not None:
            self.petri_mask = None
            self.update_petri_params(force_detect=False)

    def display_image(self, image):
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image).scaled(640, 480, Qt.KeepAspectRatio)
        self.image_label.setPixmap(pixmap)
