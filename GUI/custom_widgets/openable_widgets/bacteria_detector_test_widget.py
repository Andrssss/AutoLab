import cv2
import numpy as np
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
    QFileDialog, QScrollArea, QGroupBox, QSpinBox, QTabWidget,
    QListWidget, QListWidgetItem, QSplitter, QDialog, QDialogButtonBox
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt
from Image_processing.BacteriaDetector import BacteriaDetector


class BacteriaDetectorTestWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bacteria Detector Test - Auto Color Detection")
        self.setGeometry(100, 100, 1600, 900)
        
        self.detector = BacteriaDetector()
        self.current_image = None
        self.current_image_path = None
        self.overlay_image = None
        
        # Default parameters
        self.hue_ranges = []
        self.size_ranges = [(100, 500), (500, 1500), (1500, 99999)]
        self.split_threshold = 40.0
        self.saturation_min = 50
        self.value_min = 50
        self.morph_close_radius = 2
        self.morph_open_radius = 1
        self.num_colors = 8  # Auto-detect N dominant colors
        
        # Image list for MyCaptures folder
        self.image_list = []
        self.pictures_folder = r"C:\Users\Public\Pictures\MyCaptures"
        
        self.initUI()
        self.load_images_from_folder()
    
    def initUI(self):
        """Create main UI layout"""
        main_layout = QHBoxLayout()
        
        # ============== LEFT PANEL - CONTROLS ==============
        left_layout = QVBoxLayout()
        
        # --- Image Selection Group ---
        img_group = QGroupBox("📷 Image Selection")
        img_layout = QVBoxLayout()
        
        self.image_list_widget = QListWidget()
        self.image_list_widget.itemClicked.connect(self.on_image_selected)
        img_layout.addWidget(QLabel("MyCaptures folder:"))
        img_layout.addWidget(self.image_list_widget, 1)
        
        btn_load_custom = QPushButton("Or Load Custom")
        btn_load_custom.clicked.connect(self.load_image)
        img_layout.addWidget(btn_load_custom)
        
        self.label_image_path = QLabel("No image loaded")
        self.label_image_path.setWordWrap(True)
        img_layout.addWidget(self.label_image_path)
        img_group.setLayout(img_layout)
        left_layout.addWidget(img_group)
        
        # --- Tabs for Parameters ---
        self.tabs = QTabWidget()
        
        # TAB 1: Filtering Parameters
        filter_widget = QWidget()
        filter_layout = QVBoxLayout()
        
        # Number of colors to detect
        num_colors_group = self._create_slider_group(
            "🌈 Number of Colors to Detect (2-20)", 2, 20, self.num_colors, 
            "label_num_colors", self.on_num_colors_changed
        )
        filter_layout.addWidget(num_colors_group)
        
        # Split Threshold
        thresh_group = self._create_slider_group(
            "🔧 Split Threshold (%)", 0, 100, self.split_threshold, 
            "label_threshold", self.on_threshold_changed
        )
        filter_layout.addWidget(thresh_group)
        
        # Saturation Min
        sat_group = self._create_slider_group(
            "🎨 Saturation Min (0-255)", 0, 255, self.saturation_min,
            "label_sat", self.on_saturation_changed
        )
        filter_layout.addWidget(sat_group)
        
        # Value Min
        val_group = self._create_slider_group(
            "💡 Value Min (0-255)", 0, 255, self.value_min,
            "label_val", self.on_value_changed
        )
        filter_layout.addWidget(val_group)
        
        filter_layout.addStretch()
        filter_widget.setLayout(filter_layout)
        self.tabs.addTab(filter_widget, "Filtering")
        
        # TAB 2: Morphological Operations
        morph_widget = QWidget()
        morph_layout = QVBoxLayout()
        
        close_group = self._create_slider_group(
            "▓ Close Radius", 0, 10, self.morph_close_radius,
            "label_close", self.on_morph_changed
        )
        morph_layout.addWidget(close_group)
        
        open_group = self._create_slider_group(
            "░ Open Radius", 0, 10, self.morph_open_radius,
            "label_open", self.on_morph_changed
        )
        morph_layout.addWidget(open_group)
        
        morph_layout.addStretch()
        morph_widget.setLayout(morph_layout)
        self.tabs.addTab(morph_widget, "Morphology")
        
        # TAB 3: Size Ranges
        size_widget = QWidget()
        size_layout = QVBoxLayout()
        
        size_group = QGroupBox("📏 Size Ranges (Area)")
        size_inner = QVBoxLayout()
        self.size_range_spinboxes = []
        for i, (min_val, max_val) in enumerate(self.size_ranges):
            h_layout = QHBoxLayout()
            h_layout.addWidget(QLabel(f"Range {i+1}:"))
            
            min_spin = QSpinBox()
            min_spin.setMinimum(0)
            min_spin.setMaximum(99999)
            min_spin.setValue(min_val)
            min_spin.valueChanged.connect(self.on_size_range_changed)
            h_layout.addWidget(QLabel("Min:"))
            h_layout.addWidget(min_spin)
            
            max_spin = QSpinBox()
            max_spin.setMinimum(0)
            max_spin.setMaximum(99999)
            max_spin.setValue(max_val)
            max_spin.valueChanged.connect(self.on_size_range_changed)
            h_layout.addWidget(QLabel("Max:"))
            h_layout.addWidget(max_spin)
            
            self.size_range_spinboxes.append((min_spin, max_spin))
            size_inner.addLayout(h_layout)
        
        size_group.setLayout(size_inner)
        size_layout.addWidget(size_group)
        size_layout.addStretch()
        size_widget.setLayout(size_layout)
        self.tabs.addTab(size_widget, "Size Ranges")
        
        left_layout.addWidget(self.tabs)
        
        # --- Results Panel ---
        results_group = QGroupBox("📊 Detection Results")
        results_layout = QVBoxLayout()
        self.label_results = QLabel("Load an image - colors auto-detect on load")
        self.label_results.setWordWrap(True)
        results_layout.addWidget(self.label_results)
        results_group.setLayout(results_layout)
        left_layout.addWidget(results_group)
        
        # ============== RIGHT PANEL - PREVIEW ==============
        right_layout = QVBoxLayout()
        
        # Detection result
        right_layout.addWidget(QLabel("🔬 Detection Result:"))
        self.image_label = QLabel()
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setStyleSheet("border: 2px solid #333; background: #111;")
        self.image_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.image_label)
        
        # Color separation button
        btn_sep = QPushButton("🌈 Show Color Separation")
        btn_sep.clicked.connect(self.show_color_separation)
        right_layout.addWidget(btn_sep)

        # Auto-K button (H+S k-means)
        btn_auto_k = QPushButton("Auto-K (H+S)")
        btn_auto_k.setToolTip("Run k-means on H+S to compute color centers")
        btn_auto_k.clicked.connect(self._on_autok)
        right_layout.addWidget(btn_auto_k)
        
        # Color separation preview
        self.color_sep_label = QLabel()
        self.color_sep_label.setMinimumSize(640, 300)
        self.color_sep_label.setStyleSheet("border: 1px solid #666; background: #222;")
        self.color_sep_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.color_sep_label)

        # Swatches container (click a swatch to tune tolerance)
        self.swatch_widget = QWidget()
        self.swatch_layout = QHBoxLayout()
        self.swatch_widget.setLayout(self.swatch_layout)
        right_layout.addWidget(self.swatch_widget)
        
        # ============== COMBINE PANELS ==============
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        left_scroll = QScrollArea()
        left_scroll.setWidget(left_widget)
        left_scroll.setWidgetResizable(True)
        
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_scroll)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)
    
    def _create_slider_group(self, title, min_val, max_val, init_val, label_attr, callback):
        """Helper to create slider groups"""
        group = QGroupBox(title)
        layout = QVBoxLayout()
        
        slider_layout = QHBoxLayout()
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        slider.setValue(int(init_val))
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(max(1, (max_val - min_val) // 10))
        slider.valueChanged.connect(callback)
        
        label = QLabel(f"Value: {int(init_val)}")
        label.setMinimumWidth(100)
        setattr(self, label_attr, label)
        
        slider_layout.addWidget(slider)
        slider_layout.addWidget(label)
        layout.addLayout(slider_layout)
        group.setLayout(layout)
        
        # Store slider for callback
        setattr(self, f"slider_{label_attr}", slider)
        return group
    
    def load_images_from_folder(self):
        """Auto-load images from MyCaptures folder"""
        if os.path.exists(self.pictures_folder):
            supported = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif')
            self.image_list = sorted([f for f in os.listdir(self.pictures_folder) 
                                     if f.lower().endswith(supported)])
            
            for image_name in self.image_list:
                self.image_list_widget.addItem(image_name)
    
    def auto_detect_colors(self, image, k=4):
        """Auto-detect dominant colors using K-means in HSV space"""
        if image is None:
            return []
        
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h_channel = hsv[:,:,0]  # Only use hue
        
        # Reshape for k-means
        pixels = h_channel.reshape((-1, 1)).astype(np.float32)
        
        # K-means clustering
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, _, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        # Sort centers
        centers = sorted(centers.flatten().astype(int))
        
        # Create ranges around each center (tolerance = ~15)
        hue_ranges = []
        for i, center in enumerate(centers):
            # Avoid overlap - split the space between centers
            if i == 0:
                min_h = max(0, center - 8)
            else:
                min_h = (centers[i-1] + center) // 2
            
            if i == len(centers) - 1:
                max_h = min(179, center + 8)
            else:
                max_h = (center + centers[i+1]) // 2
            
            hue_ranges.append((min(min_h, 179), min(max_h, 179)))
        
        return hue_ranges
    
    def on_image_selected(self, item):
        """Load and auto-detect colors when selecting image"""
        image_name = item.text()
        image_path = os.path.join(self.pictures_folder, image_name)
        
        self.current_image_path = image_path
        self.current_image = cv2.imread(image_path)
        
        if self.current_image is None:
            self.label_image_path.setText(f"❌ Failed to load: {image_path}")
            return
        
        self.label_image_path.setText(f"✓ Loaded: {image_name}")
        
        # AUTO-DETECT COLORS
        self.hue_ranges = self.auto_detect_colors(self.current_image, k=self.num_colors)
        
        self.label_results.setText(f"🎨 Auto-detected {len(self.hue_ranges)} colors:\n" + 
                                   "\n".join([f"Color {i+1}: {h[0]}-{h[1]}" 
                                             for i, h in enumerate(self.hue_ranges)]))
        
        self.run_detection()
    
    def load_image(self):
        """Load custom image"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", self.pictures_folder,
            "Image Files (*.png *.jpg *.jpeg *.bmp *.tiff)"
        )
        
        if not file_path:
            return
        
        self.current_image_path = file_path
        self.current_image = cv2.imread(file_path)
        
        if self.current_image is None:
            self.label_image_path.setText(f"❌ Failed to load")
            return
        
        self.label_image_path.setText(f"✓ Loaded: {os.path.basename(file_path)}")
        
        # AUTO-DETECT COLORS
        self.hue_ranges = self.auto_detect_colors(self.current_image, k=self.num_colors)
        
        self.label_results.setText(f"🎨 Auto-detected {len(self.hue_ranges)} colors:\n" + 
                                   "\n".join([f"Color {i+1}: {h[0]}-{h[1]}" 
                                             for i, h in enumerate(self.hue_ranges)]))
        
        self.run_detection()
    
    def on_threshold_changed(self, value):
        self.split_threshold = float(value)
        self.label_threshold.setText(f"Value: {value}%")
        if self.current_image is not None:
            self.run_detection()
    
    def on_saturation_changed(self, value):
        self.saturation_min = int(value)
        self.label_sat.setText(f"Value: {value}")
        if self.current_image is not None:
            self.run_detection()
    
    def on_num_colors_changed(self, value):
        """Update number of colors to detect and re-run auto-detection"""
        self.num_colors = int(value)
        self.label_num_colors.setText(f"Value: {value}")
        if self.current_image is not None:
            # Re-detect colors with new number
            self.hue_ranges = self.auto_detect_colors(self.current_image, k=self.num_colors)
            self.label_results.setText(f"🎨 Auto-detected {len(self.hue_ranges)} colors:\n" + 
                                       "\n".join([f"Color {i+1}: {h[0]}-{h[1]}" 
                                                 for i, h in enumerate(self.hue_ranges)]))
            self.run_detection()
    
    def on_value_changed(self, value):
        self.value_min = int(value)
        self.label_val.setText(f"Value: {value}")
        if self.current_image is not None:
            self.run_detection()
    
    def on_morph_changed(self, value):
        self.morph_close_radius = self.slider_label_close.value()
        self.morph_open_radius = self.slider_label_open.value()
        self.label_close.setText(f"Value: {self.morph_close_radius}")
        self.label_open.setText(f"Value: {self.morph_open_radius}")
        if self.current_image is not None:
            self.run_detection()
    
    def on_size_range_changed(self):
        self.size_ranges = [
            (min_spin.value(), max_spin.value())
            for min_spin, max_spin in self.size_range_spinboxes
        ]
        if self.current_image is not None:
            self.run_detection()
    
    def run_detection(self):
        """Run the detection algorithm"""
        if self.current_image is None or not self.hue_ranges:
            return
        # If Auto-K produced HS centers, prefer passing them to the detector
        params = dict(
            size_ranges=self.size_ranges,
            split_threshold=self.split_threshold,
            saturation_min=self.saturation_min,
            value_min=self.value_min,
            morph_close_radius=self.morph_close_radius,
            morph_open_radius=self.morph_open_radius
        )
        if hasattr(self, '_autok_centers') and self._autok_centers:
            params['hue_centers'] = self._autok_centers
        else:
            params['hue_ranges'] = self.hue_ranges
        self.detector.set_params(**params)
        
        try:
            overlay, centers, objects, category_counts = self.detector.detect(
                self.current_image, full_mask=None, roi_rect=None, save_debug=False
            )
            
            # Update results
            color_names = ["Red", "Yellow", "Green", "Cyan", "Magenta", "Blue", 
                          "Purple", "Orange", "Pink", "Lime", "Navy", "Teal", 
                          "Olive", "Coral", "Gold", "Indigo", "Turquoise", "Rose",
                          "Brown", "Khaki"]
            results_text = f"🎯 Detected: {len(objects)} objects\n"
            for i, count in enumerate(category_counts):
                if i < len(self.hue_ranges):
                    color = color_names[i % len(color_names)]
                    results_text += f"{color}: {count}\n"
            
            self.label_results.setText(results_text)
            # If Auto-K centers exist, overlay their approximate positions
            try:
                centers_pos = None
                centers = getattr(self, '_autok_centers', None)
                if centers:
                    centers_pos = self._centers_to_positions(self.current_image, centers)
                if centers_pos:
                    ov2 = overlay.copy()
                    for i, p in enumerate(centers_pos):
                        if p is None:
                            continue
                        cv2.circle(ov2, (int(p[0]), int(p[1])), 8, (0, 0, 0), -1)
                        cv2.circle(ov2, (int(p[0]), int(p[1])), 6, self._legend_color(i), -1)
                        cv2.putText(ov2, f"C{i+1}", (int(p[0]) + 8, int(p[1]) + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
                    self.display_image(ov2)
                else:
                    self.display_image(overlay)
            except Exception:
                self.display_image(overlay)
            # Build/update swatches for interactive tuning
            try:
                centers = getattr(self, '_autok_centers', None)
                if centers:
                    self._build_swatches_from_centers(centers)
                else:
                    # build from hue_ranges
                    self._build_swatches_from_ranges(self.hue_ranges)
            except Exception:
                pass
            
        except Exception as e:
            self.label_results.setText(f"❌ Error: {str(e)}")
    
    def show_color_separation(self):
        """Show color separation preview - side by side"""
        if self.current_image is None or not self.hue_ranges:
            self.label_results.setText("❌ Load image first")
            return
        
        image = self.current_image.copy()
        h, w = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Create composite - arrange colors SIDE BY SIDE horizontally
        num_ranges = len(self.hue_ranges)
        display_h = h // 2  # Reduce height for side-by-side view
        display_w = w  # Full width
        
        # Each color gets a slice of the width
        color_width = display_w // num_ranges if num_ranges > 0 else display_w
        composite = np.zeros((display_h, display_w, 3), dtype=np.uint8)
        
        color_names = ["Red", "Yellow", "Green", "Cyan", "Magenta", "Blue", 
                      "Purple", "Orange", "Pink", "Lime", "Navy", "Teal", 
                      "Olive", "Coral", "Gold", "Indigo", "Turquoise", "Rose",
                      "Brown", "Khaki"]
        
        for idx, (h_min, h_max) in enumerate(self.hue_ranges):
            lower = np.array([h_min, self.saturation_min, self.value_min], dtype=np.uint8)
            upper = np.array([h_max, 255, 255], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)
            masked_img = cv2.bitwise_and(image, image, mask=mask)
            
            # Resize to fit in the side-by-side layout
            resized = cv2.resize(masked_img, (color_width, display_h))
            composite[:, idx * color_width:(idx + 1) * color_width] = resized
            
            # Add label at the top-left of each color section
            color = color_names[idx % len(color_names)]
            label_text = f"{color} ({h_min}-{h_max})"
            cv2.putText(composite, label_text, (idx * color_width + 5, 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        self.display_color_separation(composite)
    
    def display_image(self, image_bgr):
        """Display image in label"""
        h, w = image_bgr.shape[:2]
        if w > 600 or h > 480:
            scale = min(600 / w, 480 / h)
            image_bgr = cv2.resize(image_bgr, (int(w * scale), int(h * scale)))
        
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = image_rgb.shape
        # Make a contiguous copy to prevent garbage collection issues
        image_rgb = np.ascontiguousarray(image_rgb)
        bytes_per_line = 3 * w
        qt_image = QImage(image_rgb.tobytes(), w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        self.image_label.setPixmap(pixmap)
    
    def display_color_separation(self, image_bgr):
        """Display color separation"""
        h, w = image_bgr.shape[:2]
        if w > 600 or h > 800:
            scale = min(600 / w, 800 / h)
            image_bgr = cv2.resize(image_bgr, (int(w * scale), int(h * scale)))
        
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = image_rgb.shape
        # Make a contiguous copy to prevent garbage collection issues
        image_rgb = np.ascontiguousarray(image_rgb)
        bytes_per_line = 3 * w
        qt_image = QImage(image_rgb.tobytes(), w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        self.color_sep_label.setPixmap(pixmap)

    # ---------- Auto-K (H+S KMeans) ----------
    def _on_autok(self):
        if self.current_image is None:
            self.label_results.setText("❌ Load an image first")
            return

        centers = self._compute_hs_kmeans_centers(self.current_image, k=self.num_colors)
        if not centers:
            self.label_results.setText("❌ Auto-K failed to find centers")
            return

        # store centers (list of (h,s)) and also update hue_ranges for compatibility
        self._autok_centers = centers
        # create hue ranges (simple +/- 8 around hue center, will be handled by detector as centers if provided)
        hue_ranges = []
        centers_h = [c[0] for c in centers]
        centers_h_sorted = sorted(centers_h)
        for i, center in enumerate(centers_h_sorted):
            if i == 0:
                min_h = max(0, center - 8)
            else:
                min_h = (centers_h_sorted[i-1] + center) // 2
            if i == len(centers_h_sorted) - 1:
                max_h = min(179, center + 8)
            else:
                max_h = (center + centers_h_sorted[i+1]) // 2
            hue_ranges.append((min_h, max_h))
        self.hue_ranges = hue_ranges

        self.label_results.setText(f"🎨 Auto-K detected {len(centers)} centers")
        self.run_detection()

    def _compute_hs_kmeans_centers(self, image, k=8, valid_mask=None):
        if image is None:
            return []
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        H = hsv[:, :, 0].reshape(-1, 1).astype(np.float32)
        S = hsv[:, :, 1].reshape(-1, 1).astype(np.float32)
        hs = np.hstack([H, S])

        if valid_mask is not None:
            vm = valid_mask.reshape(-1)
            hs = hs[vm]
            if hs.shape[0] == 0:
                return []

        # downsample for speed
        n = hs.shape[0]
        if n > 50000:
            idx = np.random.choice(n, 50000, replace=False)
            sample = hs[idx]
        else:
            sample = hs

        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        try:
            _, _, centers = cv2.kmeans(sample.astype(np.float32), k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
        except Exception:
            return []

        centers = centers.astype(int).tolist()
        centers_t = [(int(c[0]), int(c[1])) for c in centers]
        return centers_t

    def _centers_to_positions(self, image_bgr, centers, valid_mask=None):
        """Approximate image coordinates for HS centers by assigning each pixel to nearest center and
        computing centroid of assigned pixels for each center. Returns list of (x,y) or None."""
        if image_bgr is None or not centers:
            return []
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        H = hsv[:, :, 0].astype(np.float32)
        S = hsv[:, :, 1].astype(np.float32)
        h_flat = H.reshape(-1)
        s_flat = S.reshape(-1)
        h_img, w_img = H.shape

        centers_arr = np.array(centers, dtype=np.float32)
        ch = centers_arr[:, 0].reshape(1, -1)
        cs = centers_arr[:, 1].reshape(1, -1)

        # compute circular hue distance and label pixels
        diff_h = np.abs(h_flat.reshape(-1, 1) - ch)
        diff_h = np.minimum(diff_h, 179.0 - diff_h) / 179.0
        diff_s = np.abs(s_flat.reshape(-1, 1) - cs) / 255.0
        dist = np.sqrt(diff_h ** 2 + diff_s ** 2)
        labels = np.argmin(dist, axis=1)

        labels_img = labels.reshape(h_img, w_img)
        centers_pos = []
        # morphological kernel for cleaning assigned masks
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        for ci in range(centers_arr.shape[0]):
            mask = (labels_img == ci).astype('uint8') * 255
            if valid_mask is not None:
                vm = (valid_mask > 0).astype('uint8')
                mask = cv2.bitwise_and(mask, vm.astype('uint8') * 255)

            # clean small speckles and close holes
            if np.count_nonzero(mask) == 0:
                centers_pos.append(None)
                continue
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

            # connected components -> pick largest component
            num_labels, labels_cc, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
            if num_labels <= 1:
                centers_pos.append(None)
                continue
            # find largest non-background component
            areas = stats[1:, cv2.CC_STAT_AREA]
            if areas.size == 0:
                centers_pos.append(None)
                continue
            max_idx = int(np.argmax(areas)) + 1
            cx, cy = centroids[max_idx]
            centers_pos.append((int(cx), int(cy)))

        return centers_pos

    # ---------- Interactive swatches ----------
    def _build_swatches_from_centers(self, centers):
        # centers: list of (h,s)
        self._clear_swatches()
        for i, (h, s) in enumerate(centers):
            rgb = cv2.cvtColor(np.uint8([[[h, s, 200]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
            btn = QPushButton()
            btn.setFixedSize(36, 36)
            btn.setStyleSheet(f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); border: 1px solid #222;")
            btn.clicked.connect(lambda _, idx=i: self._on_swatch_clicked(idx))
            self.swatch_layout.addWidget(btn)
        self.swatch_layout.addStretch()

    def _build_swatches_from_ranges(self, ranges):
        self._clear_swatches()
        for i, (h0, h1) in enumerate(ranges):
            mid = (h0 + h1) // 2
            rgb = cv2.cvtColor(np.uint8([[[mid, 200, 200]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
            btn = QPushButton()
            btn.setFixedSize(36, 36)
            btn.setStyleSheet(f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); border: 1px solid #222;")
            btn.clicked.connect(lambda _, idx=i: self._on_swatch_clicked(idx))
            self.swatch_layout.addWidget(btn)
        self.swatch_layout.addStretch()

    def _clear_swatches(self):
        while self.swatch_layout.count():
            w = self.swatch_layout.takeAt(0)
            if w.widget():
                w.widget().deleteLater()

    def _on_swatch_clicked(self, idx):
        # open dialog to tune tolerance for swatch idx
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Tune Color {idx+1}")
        v = QVBoxLayout(dlg)
        htol_label = QLabel("Hue tolerance (+/- deg)")
        htol = QSpinBox()
        htol.setRange(0, 60)
        htol.setValue(8)
        stol_label = QLabel("Sat tolerance (0-255)")
        stol = QSpinBox()
        stol.setRange(0, 255)
        stol.setValue(60)
        v.addWidget(htol_label)
        v.addWidget(htol)
        v.addWidget(stol_label)
        v.addWidget(stol)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        v.addWidget(box)
        if dlg.exec_() == QDialog.Accepted:
            htol_v = htol.value()
            s_tol_v = stol.value()
            # apply by converting centers -> hue_ranges using tolerance
            if hasattr(self, '_autok_centers') and self._autok_centers:
                centers_h = [c[0] for c in self._autok_centers]
                centers_h_sorted = sorted(centers_h)
                ranges = []
                for i, c in enumerate(centers_h_sorted):
                    min_h = max(0, c - htol_v)
                    max_h = min(179, c + htol_v)
                    ranges.append((min_h, max_h))
                self.hue_ranges = ranges
                # clear autok centers to prefer ranges
                delattr(self, '_autok_centers')
            else:
                # tune existing hue_ranges
                if 0 <= idx < len(self.hue_ranges):
                    c0, c1 = self.hue_ranges[idx]
                    mid = (c0 + c1) // 2
                    min_h = max(0, mid - htol_v)
                    max_h = min(179, mid + htol_v)
                    self.hue_ranges[idx] = (min_h, max_h)
            # re-run detection
            self.run_detection()
