from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QListWidget, QListWidgetItem, QFrame, QSlider, QCheckBox, QFileDialog, QSpinBox, QDialog, QDialogButtonBox, QGroupBox, QSizePolicy, QScrollArea, QApplication
from PyQt5.QtGui import QPixmap, QImage, QKeySequence
from PyQt5.QtCore import Qt, QPoint, QTimer
import cv2
import numpy as np
import math
import os
import json
import yaml
from datetime import datetime
from Image_processing.BacteriaDetector import BacteriaDetector
from Image_processing.auto_k import compute_autok_centers, classify_contour_to_center

class StepROIWidget(QWidget):
    MODE_POINTS = "points"
    MODE_AREAS  = "areas"

    def __init__(self, context, image_path=None, log_widget=None, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(960, 620)
        self._normal_window_sized = False
        self.context = context
        self.log_widget = log_widget

        # model
        self.rois = list(getattr(context, "rois", []) or [])             # [(x,y,w,h), ...]
        self.roi_points = list(getattr(context, "roi_points", []) or []) # [(x,y), ...]
        self.mode = self.MODE_POINTS

        # selections (for highlight)
        self.selected_area_idx = -1
        self.selected_point_idx = -1

        # drawing/drag state
        self.dragging = False
        self.drag_start_img = None
        self.current_rect = None

        # analyzer drawings (we store contours, not boxes)
        self.detected_contours = []  # list of polygons (list[list[x,y]])
        self.detected_contour_labels = []  # parallel list: Auto-K class index per contour (or None)

        self.selected_point_radius = 12  # size of the selected point
        self.selected_point_halo = 4  # extra white halo thickness around it
        self.unselected_marker_size = 12  # size for the normal cross marker

        # --- UI ---
        # main layout: content row + bottom navigation row
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(10)

        content = QHBoxLayout()
        content.setSpacing(10)

        # left: image + controls
        left = QVBoxLayout()
        left.setSpacing(8)
        self.image_label = QLabel("Image not loaded")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(360, 260)
        self.image_label.setFrameShape(QFrame.StyledPanel)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.mousePressEvent = self.on_mouse_press
        self.image_label.mouseMoveEvent = self.on_mouse_move
        self.image_label.mouseReleaseEvent = self.on_mouse_release

        self.instructions = QLabel("Mode: POINTS - Left-click add / Right-click remove. Switch mode to AREAS to draw rectangles.")
        self.instructions.setAlignment(Qt.AlignCenter)
        self.instructions.setWordWrap(True)

        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)

        # nav / actions
        self.prev_btn = QPushButton("Previous")
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.on_next_save)
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.reset_all)
        self.clear_points_btn = QPushButton("Clear Points")
        self.clear_points_btn.clicked.connect(self.clear_points_only)

        self.btn_mode_points = QPushButton("Points")
        self.btn_mode_points.setCheckable(True)
        self.btn_mode_points.setChecked(True)
        self.btn_mode_points.clicked.connect(lambda: self.set_mode(self.MODE_POINTS))

        self.btn_mode_areas = QPushButton("Areas")
        self.btn_mode_areas.setCheckable(True)
        self.btn_mode_areas.clicked.connect(lambda: self.set_mode(self.MODE_AREAS))

        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(6)
        mode_layout.addWidget(self.btn_mode_points)
        mode_layout.addWidget(self.btn_mode_areas)
        mode_layout.addStretch()
        mode_layout.addWidget(self.clear_points_btn)
        mode_layout.addWidget(self.reset_btn)

        # (Analyze gombok maradnak itt, ha a kontextusban megvannak)
        self.btn_analyze_rois = QPushButton("X - Analyze Selected ROIs")
        self.btn_analyze_rois.clicked.connect(self.analyze_selected)
        self.btn_analyze_whole = QPushButton("O - Analyze Whole Dish")
        self.btn_analyze_whole.clicked.connect(self.analyze_whole)
        self.btn_analyze_rois.setMinimumWidth(0)
        self.btn_analyze_whole.setMinimumWidth(0)

        analyze_layout = QHBoxLayout()
        analyze_layout.setSpacing(6)
        analyze_layout.addStretch()
        analyze_layout.addWidget(self.btn_analyze_rois)
        analyze_layout.addWidget(self.btn_analyze_whole)
        analyze_layout.addStretch()

        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(6)
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_btn)

        left.addWidget(self.image_label, 1)
        left.addLayout(mode_layout)
        left.addSpacing(2)
        left.addWidget(self.instructions)
        left.addWidget(self.info_label)
        left.addLayout(analyze_layout)

        # right: side panel with lists
        right = QVBoxLayout()
        right.setSpacing(10)

        # --- Detector controls ---
        # sliders and checkboxes
        self.slider_num_colors = QSpinBox()
        self.slider_num_colors.setRange(2, 20)
        self.slider_num_colors.setValue(8)
        self.slider_split = QSlider(Qt.Horizontal)
        self.slider_split.setRange(1, 100)
        self.slider_split.setValue(40)
        self.slider_sat = QSlider(Qt.Horizontal)
        self.slider_sat.setRange(0, 255)
        self.slider_sat.setValue(50)
        self.slider_val = QSlider(Qt.Horizontal)
        self.slider_val.setRange(0, 255)
        self.slider_val.setValue(50)
        self.slider_close = QSlider(Qt.Horizontal)
        self.slider_close.setRange(0, 20)
        self.slider_close.setValue(2)
        self.slider_open = QSlider(Qt.Horizontal)
        self.slider_open.setRange(0, 20)
        self.slider_open.setValue(1)

        self.chk_texture = QCheckBox("Use Texture")
        self.chk_edge = QCheckBox("Edge-based Split")
        self.chk_calib = QCheckBox("Auto Color Calibrate")

        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_csv.clicked.connect(self._on_export_csv)

        # realtime debounce timer
        self._detector_timer = QTimer(self)
        self._detector_timer.setSingleShot(True)
        self._detector_timer.timeout.connect(self._on_detector_params_apply)

        # detector instance
        self.detector = BacteriaDetector()

        # connect sliders to debounce
        self.slider_num_colors.valueChanged.connect(self._on_num_colors_value_changed)
        self.slider_split.valueChanged.connect(lambda _: self._detector_timer.start(100))
        self.slider_sat.valueChanged.connect(lambda _: self._detector_timer.start(100))
        self.slider_val.valueChanged.connect(lambda _: self._detector_timer.start(100))
        self.slider_close.valueChanged.connect(lambda _: self._detector_timer.start(100))
        self.slider_open.valueChanged.connect(lambda _: self._detector_timer.start(100))
        self.chk_texture.stateChanged.connect(lambda _: self._detector_timer.start(100))
        self.chk_edge.stateChanged.connect(lambda _: self._detector_timer.start(100))
        self.chk_calib.stateChanged.connect(lambda _: self._detector_timer.start(100))
        # Auto-K button
        self.btn_auto_k = QPushButton("Auto-K")
        self.btn_auto_k.clicked.connect(self._on_autok)
        self.btn_auto_k.setToolTip("Run k-means on H+S to compute color centers from the image")


        # Areas list
        lbl_areas = QLabel("Areas")
        self.list_areas = QListWidget()
        self.list_areas.itemSelectionChanged.connect(self._on_area_selected)
        self.list_areas.itemDoubleClicked.connect(self._on_area_double_clicked)
        self.btn_area_delete = QPushButton("Delete (Area)")
        self.btn_area_delete.clicked.connect(self._delete_selected_area)

        # Points list
        lbl_points = QLabel("Points")
        self.list_points = QListWidget()
        self.list_points.itemSelectionChanged.connect(self._on_point_selected)
        self.list_points.itemDoubleClicked.connect(self._on_point_double_clicked)
        self.btn_point_delete = QPushButton("Delete (Point)")
        self.btn_point_delete.clicked.connect(self._delete_selected_point)

        # Quick help for deletion
        hint = QLabel("Tip: after selecting an item, the Delete key also works.")
        hint.setStyleSheet("color: gray; font-size: 11px;")

        roi_group = QGroupBox("ROI Lists")
        roi_layout = QVBoxLayout()
        roi_layout.setSpacing(6)
        roi_layout.addWidget(lbl_areas)
        roi_layout.addWidget(self.list_areas, 1)
        roi_layout.addWidget(self.btn_area_delete)
        roi_layout.addSpacing(4)
        roi_layout.addWidget(lbl_points)
        roi_layout.addWidget(self.list_points, 1)
        roi_layout.addWidget(self.btn_point_delete)
        roi_layout.addWidget(hint)
        roi_group.setLayout(roi_layout)

        detector_group = QGroupBox("Bacteria Detector")
        detector_layout = QVBoxLayout()
        detector_layout.setSpacing(6)
        detector_layout.addWidget(QLabel("Num Colors"))
        detector_layout.addWidget(self.slider_num_colors)
        detector_layout.addWidget(self.btn_auto_k)
        detector_layout.addWidget(QLabel("Split Threshold %"))
        detector_layout.addWidget(self.slider_split)
        detector_layout.addWidget(QLabel("Saturation Min"))
        detector_layout.addWidget(self.slider_sat)
        detector_layout.addWidget(QLabel("Value Min"))
        detector_layout.addWidget(self.slider_val)
        detector_layout.addWidget(QLabel("Close Radius"))
        detector_layout.addWidget(self.slider_close)
        detector_layout.addWidget(QLabel("Open Radius"))
        detector_layout.addWidget(self.slider_open)
        detector_layout.addWidget(self.chk_texture)
        detector_layout.addWidget(self.chk_edge)
        detector_layout.addWidget(self.chk_calib)
        detector_layout.addWidget(self.btn_export_csv)
        detector_group.setLayout(detector_layout)

        right.addWidget(roi_group, 2)
        right.addWidget(detector_group, 3)

        right_panel = QWidget()
        right_panel.setLayout(right)
        right_panel.setMinimumWidth(280)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setWidget(right_panel)
        right_scroll.setMinimumWidth(280)

        content.addLayout(left, 3)
        content.addWidget(right_scroll, 1)

        main.addLayout(content, 1)
        main.addLayout(nav_layout)

        self.display_image = None
        self.scaled_display_size = None

        self.load_from_context()
        self._refresh_roi_lists()
        # swatches area
        self._swatches_container = QWidget()
        self._swatches_layout = QHBoxLayout()
        self._swatches_container.setLayout(self._swatches_layout)
        right.addWidget(self._swatches_container)
        # enable key events
        self.setFocusPolicy(Qt.StrongFocus)

    # ---------- Slider state persistence ----------
    def _get_slider_config_path(self):
        """Get path to detector_params.yaml in config_profiles."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Navigate up to project root: GUI/custom_widgets/photo_pipeline/manual_steps -> AutoLab
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
        config_dir = os.path.join(project_root, "config_profiles")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "detector_params.yaml")

    def _save_slider_state(self):
        """Save all slider positions to YAML config file."""
        try:
            state = {
                "num_colors": self.slider_num_colors.value(),
                "split_threshold": self.slider_split.value(),
                "saturation_min": self.slider_sat.value(),
                "value_min": self.slider_val.value(),
                "morph_close_radius": self.slider_close.value(),
                "morph_open_radius": self.slider_open.value(),
                "use_texture": self.chk_texture.isChecked(),
                "use_edge_split": self.chk_edge.isChecked(),
                "auto_color_calib": self.chk_calib.isChecked(),
            }
            path = self._get_slider_config_path()
            with open(path, "w") as f:
                yaml.dump(state, f, default_flow_style=False)
        except Exception as e:
            if self.log_widget:
                self.log_widget.append_log(f"[WARN] Failed to save slider state: {e}")

    def _load_slider_state(self):
        """Load slider positions from YAML config file if available."""
        try:
            path = self._get_slider_config_path()
            if not os.path.exists(path):
                return
            with open(path, "r") as f:
                state = yaml.safe_load(f)
            if not state:
                return
            # Load values (with defaults if keys missing)
            self.slider_num_colors.setValue(state.get("num_colors", 8))
            self.slider_split.setValue(state.get("split_threshold", 40))
            self.slider_sat.setValue(state.get("saturation_min", 50))
            self.slider_val.setValue(state.get("value_min", 50))
            self.slider_close.setValue(state.get("morph_close_radius", 2))
            self.slider_open.setValue(state.get("morph_open_radius", 1))
            self.chk_texture.setChecked(state.get("use_texture", False))
            self.chk_edge.setChecked(state.get("use_edge_split", False))
            self.chk_calib.setChecked(state.get("auto_color_calib", False))
        except Exception as e:
            if self.log_widget:
                self.log_widget.append_log(f"[WARN] Failed to load slider state: {e}")

    # ---------- context ----------
    def load_from_context(self):
        if getattr(self.context, "image", None) is not None:
            self.display_roi_image()
        else:
            self.image_label.setText("No image")
        self.update_info()

        # Make the host window large but normal (not fullscreen/maximized)
        self._ensure_large_normal_window()

        # load slider positions from config if available
        self._load_slider_state()

        # apply initial detector params and run a quick preview
        self._apply_detector_params()
        self._detector_timer.start(10)
        # keep normal in-window sizing (do not force maximize/fullscreen from this step)

    def _ensure_large_normal_window(self):
        if self._normal_window_sized:
            return
        win = self.window()
        if win is None:
            return
        if win.isMaximized() or win.isFullScreen():
            self._normal_window_sized = True
            return

        app = QApplication.instance()
        if app is None:
            return
        screen = app.primaryScreen()
        if screen is None:
            return

        avail = screen.availableGeometry()
        target_w = min(avail.width() - 40, max(int(avail.width() * 0.92), 1200))
        target_h = min(avail.height() - 40, max(int(avail.height() * 0.90), 760))
        target_w = max(980, target_w)
        target_h = max(640, target_h)

        try:
            win.resize(target_w, target_h)
            x = avail.x() + (avail.width() - target_w) // 2
            y = avail.y() + (avail.height() - target_h) // 2
            win.move(max(avail.x(), x), max(avail.y(), y))
            self._normal_window_sized = True
        except Exception:
            pass

    def save_to_context(self):
        # keep original keys for backward compatibility
        self.context.rois = self.rois
        self.context.rois_areas = self.rois
        self.context.roi_points = self.roi_points
        # save slider state whenever context is saved
        self._save_slider_state()

    def _compose_visualized_image(self):
        if self.display_image is None:
            return None

        img = self.display_image.copy()

        # user ROIs (orange) + highlight selected (thicker, white overlay)
        for i, (x, y, w, h) in enumerate(self.rois):
            color = (0, 180, 255)
            thickness = 2
            if i == self.selected_area_idx:
                cv2.rectangle(img, (x-1, y-1), (x + w+1, y + h+1), (255, 255, 255), 3)
                thickness = 2
            cv2.rectangle(img, (x, y), (x + w, y + h), color, thickness)
            cv2.putText(img, f"A{i}", (x+3, y+16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 180, 255), 1, cv2.LINE_AA)

        # currently drawn rectangle (during drag)
        if self.current_rect is not None:
            x, y, w, h = self.current_rect
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 80, 0), 2)

        # analyzer contours (blue outlines)
        for idx, poly in enumerate(getattr(self, "detected_contours", [])):
            cnt = np.array(poly, dtype=np.int32)
            if cnt.ndim == 2 and len(cnt) >= 3:
                color = (255, 0, 0)
                labels = getattr(self, "detected_contour_labels", [])
                if idx < len(labels) and labels[idx] is not None:
                    color = self._legend_color(int(labels[idx]))
                cv2.polylines(img, [cnt], isClosed=True, color=color, thickness=2)

        # selected points (red crosses + labels) + highlight selected (filled circle)
        for j, (px, py) in enumerate(self.roi_points):
            if j == self.selected_point_idx:
                # white halo
                cv2.circle(img, (int(px), int(py)), self.selected_point_radius + self.selected_point_halo,
                           (255, 255, 255), -1)
                # big red dot
                cv2.circle(img, (int(px), int(py)), self.selected_point_radius, (0, 0, 255), -1)
            else:
                cv2.drawMarker(
                    img, (int(px), int(py)),
                    (0, 0, 255),
                    markerType=cv2.MARKER_TILTED_CROSS,
                    markerSize=self.unselected_marker_size,
                    thickness=2
                )
            cv2.putText(img, f"P{j}", (int(px) + 6, int(py) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

        # (optional) merged_points as green circles
        merged = getattr(self.context, "merged_points", None)
        if merged:
            for (mx, my) in merged:
                cv2.circle(img, (int(mx), int(my)), 5, (0, 200, 0), 2)

        return img

    def _normalize_for_json(self, value):
        if isinstance(value, (np.integer, )):
            return int(value)
        if isinstance(value, (np.floating, )):
            return float(value)
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, (list, tuple)):
            return [self._normalize_for_json(v) for v in value]
        if isinstance(value, dict):
            return {str(k): self._normalize_for_json(v) for k, v in value.items()}
        return value

    def _save_analysis_snapshot(self, mode, results_payload=None):
        """Persist current analyzed preview image + metadata for future comparison."""
        try:
            out_dir = getattr(self.context, "output_dir", None) or os.path.join(os.getcwd(), "debug")
            history_dir = os.path.join(out_dir, "analysis_history")
            os.makedirs(history_dir, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            img_path = getattr(self.context, "image_path", None)
            base = os.path.splitext(os.path.basename(img_path))[0] if isinstance(img_path, str) and img_path else "frame"

            # Save exactly the currently rendered analysis view (same overlays as widget preview)
            snap = self._compose_visualized_image()
            if snap is None and getattr(self.context, "image", None) is not None:
                snap = self.context.image.copy()
                self._apply_mask_outline(snap)

            snapshot_rel = None
            if snap is not None:
                snapshot_name = f"{base}_{mode}_{ts}.png"
                snapshot_path = os.path.join(history_dir, snapshot_name)
                cv2.imwrite(snapshot_path, snap)
                snapshot_rel = snapshot_name

            autok_centers = getattr(self, "_autok_centers", None)
            entry = {
                "timestamp": ts,
                "mode": mode,
                "source_image": img_path,
                "snapshot_file": snapshot_rel,
                "detector_params": {
                    "num_colors": int(self.slider_num_colors.value()),
                    "split_threshold": int(self.slider_split.value()),
                    "saturation_min": int(self.slider_sat.value()),
                    "value_min": int(self.slider_val.value()),
                    "morph_close_radius": int(self.slider_close.value()),
                    "morph_open_radius": int(self.slider_open.value()),
                    "use_texture": bool(self.chk_texture.isChecked()),
                    "use_edge_split": bool(self.chk_edge.isChecked()),
                    "color_calibration": bool(self.chk_calib.isChecked()),
                    "autok_centers": self._normalize_for_json(autok_centers) if autok_centers else [],
                },
                "roi_areas": self._normalize_for_json(list(self.rois)),
                "roi_points": self._normalize_for_json(list(self.roi_points)),
                "detected_contours_count": int(len(getattr(self, "detected_contours", []))),
                "results": self._normalize_for_json(results_payload or {}),
            }

            history_log = os.path.join(history_dir, "analysis_history.jsonl")
            with open(history_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            if self.log_widget:
                self.log_widget.append_log(f"[SAVE] Analysis snapshot -> {os.path.join(history_dir, snapshot_rel) if snapshot_rel else history_dir}")
                self.log_widget.append_log(f"[SAVE] Analysis metadata -> {history_log}")
        except Exception as e:
            if self.log_widget:
                self.log_widget.append_log(f"[WARNING] Analysis snapshot save failed: {e}")

    # ---------- rendering ----------
    def display_roi_image(self):
        image = self.context.image
        if image is None:
            self.image_label.setText("No image to show.")
            return
        preview = image.copy()
        self._apply_mask_outline(preview)
        self.display_image = preview
        self.update_image_label()

    def update_image_label(self):
        if self.display_image is None:
            return

        img = self._compose_visualized_image()
        if img is None:
            return

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        content_rect = self.image_label.contentsRect()
        target_w = max(1, content_rect.width())
        target_h = max(1, content_rect.height())
        pixmap = QPixmap.fromImage(qimg).scaled(
            target_w, target_h,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.scaled_display_size = pixmap.size()
        self.image_label.setPixmap(pixmap)

        self.update_info()

    def update_info(self):
        txt = f"Areas: {len(self.rois)} | Points: {len(self.roi_points)}"
        if getattr(self.context, "mask", None) is None:
            txt += " | No Petri mask"
        self.info_label.setText(txt)

        if self.mode == self.MODE_POINTS:
            self.instructions.setText("Mode: POINTS - Left click: add point | Right click: delete nearest point | Double click image: Analyze selected")
        else:
            self.instructions.setText("Mode: AREAS - Drag to draw rectangle | Right click: delete nearest area | Double click image: Analyze selected")

    # ---------- list helpers ----------
    def _refresh_roi_lists(self):
        # Areas
        self.list_areas.blockSignals(True)
        self.list_areas.clear()
        for i, (x, y, w, h) in enumerate(self.rois):
            item = QListWidgetItem(f"A{i}: x={x}, y={y}, w={w}, h={h}")
            self.list_areas.addItem(item)
        self.list_areas.blockSignals(False)
        if 0 <= self.selected_area_idx < len(self.rois):
            self.list_areas.setCurrentRow(self.selected_area_idx)
        else:
            self.selected_area_idx = -1

        # Points
        self.list_points.blockSignals(True)
        self.list_points.clear()
        for j, (px, py) in enumerate(self.roi_points):
            item = QListWidgetItem(f"P{j}: x={px}, y={py}")
            self.list_points.addItem(item)
        self.list_points.blockSignals(False)
        if 0 <= self.selected_point_idx < len(self.roi_points):
            self.list_points.setCurrentRow(self.selected_point_idx)
        else:
            self.selected_point_idx = -1

    def _on_area_selected(self):
        idx = self.list_areas.currentRow()
        self.selected_area_idx = idx
        self.update_image_label()

    def _on_point_selected(self):
        idx = self.list_points.currentRow()
        self.selected_point_idx = idx
        self.update_image_label()

    def _on_area_double_clicked(self, item):
        self._delete_selected_area()

    def _on_point_double_clicked(self, item):
        self._delete_selected_point()

    def _delete_selected_area(self):
        idx = self.list_areas.currentRow()
        if 0 <= idx < len(self.rois):
            self.rois.pop(idx)
            self.selected_area_idx = -1
            self._refresh_roi_lists()
            self.update_image_label()
            self.save_to_context()

    def _delete_selected_point(self):
        idx = self.list_points.currentRow()
        if 0 <= idx < len(self.roi_points):
            self.roi_points.pop(idx)

            # --- keep merged_points consistent ---
            if hasattr(self.context, "merged_points") and self.context.merged_points:
                if idx < len(self.context.merged_points):
                    self.context.merged_points.pop(idx)
            # -----------------------------------------

            self.selected_point_idx = -1
            self._refresh_roi_lists()
            self.update_image_label()
            self.save_to_context()

    # ---------- coord helpers ----------
    def _label_to_image_xy(self, pos: QPoint):
        if self.display_image is None or self.scaled_display_size is None:
            return None
        disp_w = self.scaled_display_size.width()
        disp_h = self.scaled_display_size.height()
        img_h, img_w = self.display_image.shape[:2]

        sx = img_w / disp_w
        sy = img_h / disp_h

        lw = self.image_label.width()
        lh = self.image_label.height()
        off_x = (lw - disp_w) // 2
        off_y = (lh - disp_h) // 2

        x = int((pos.x() - off_x) * sx)
        y = int((pos.y() - off_y) * sy)
        if x < 0 or y < 0 or x >= img_w or y >= img_h:
            return None
        return (x, y)

    def _rect_from_points(self, p0, p1):
        x0, y0 = p0; x1, y1 = p1
        x = min(x0, x1); y = min(y0, y1)
        w = abs(x1 - x0); h = abs(y1 - y0)
        return (x, y, w, h)

    def _apply_mask_outline(self, img):
        mask = getattr(self.context, "mask", None)
        if mask is None:
            return img
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img, cnts, -1, (0, 255, 255), 2)  # yellow outline
        return img

    # ---------- mouse ----------
    def on_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            pt = self._label_to_image_xy(event.pos())
            if pt is None:
                return

            if getattr(self.context, "mask", None) is not None:
                x, y = pt
                if self.context.mask[y, x] == 0:
                    if self.log_widget:
                        self.log_widget.append_log("[INFO] Click outside Petri dish ignored.")
                    return

            if self.mode == self.MODE_POINTS:
                for (px, py) in self.roi_points:
                    if abs(px - pt[0]) < 4 and abs(py - pt[1]) < 4:
                        if self.log_widget:
                            self.log_widget.append_log("[INFO] Point already exists nearby.")
                        return
                self.roi_points.append(pt)
                self.selected_point_idx = len(self.roi_points) - 1
                self.update_image_label()
                self._refresh_roi_lists()
                self.save_to_context()
            else:  # AREAS
                self.dragging = True
                self.drag_start_img = pt
                self.current_rect = (pt[0], pt[1], 1, 1)
                self.update_image_label()

        elif event.button() == Qt.RightButton:
            pt = self._label_to_image_xy(event.pos())
            if pt is None:
                return
            if self.mode == self.MODE_POINTS and self.roi_points:
                d = [math.hypot(px-pt[0], py-pt[1]) for (px, py) in self.roi_points]
                i = int(np.argmin(d))
                if d[i] < 25:
                    self.roi_points.pop(i)
                    self.selected_point_idx = -1
                    self.update_image_label()
                    self._refresh_roi_lists()
                    self.save_to_context()
            elif self.mode == self.MODE_AREAS and self.rois:
                centers = [((x+w/2), (y+h/2)) for (x, y, w, h) in self.rois]
                d = [math.hypot(cx-pt[0], cy-pt[1]) for (cx, cy) in centers]
                i = int(np.argmin(d))
                if d[i] < 35:
                    self.rois.pop(i)
                    self.selected_area_idx = -1
                    self.update_image_label()
                    self._refresh_roi_lists()
                    self.save_to_context()
                    self._detector_timer.start(50)

        if event.type() == event.MouseButtonDblClick:
            self.analyze_selected()

    def on_mouse_move(self, event):
        if self.mode != self.MODE_AREAS or not self.dragging or self.drag_start_img is None:
            return
        pt = self._label_to_image_xy(event.pos())
        if pt is None:
            return
        self.current_rect = self._rect_from_points(self.drag_start_img, pt)
        self.update_image_label()

    def on_mouse_release(self, event):
        if self.mode != self.MODE_AREAS:
            return
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            pt = self._label_to_image_xy(event.pos())
            if pt is None or self.drag_start_img is None:
                self.current_rect = None
                self.update_image_label()
                return

            rect = self._rect_from_points(self.drag_start_img, pt)
            x, y, w, h = rect
            if w < 5 or h < 5:
                self.current_rect = None
                self.update_image_label()
                return

            if getattr(self.context, "mask", None) is not None:
                cx = x + w // 2; cy = y + h // 2
                if (cy < 0 or cx < 0 or
                    cy >= self.context.mask.shape[0] or cx >= self.context.mask.shape[1] or
                    self.context.mask[cy, cx] == 0):
                    if self.log_widget:
                        self.log_widget.append_log("[INFO] ROI center outside dish -> ignored.")
                    self.current_rect = None
                    self.update_image_label()
                    return

            self.rois.append(rect)
            self.selected_area_idx = len(self.rois) - 1
            self.current_rect = None
            self.update_image_label()
            self._refresh_roi_lists()
            self.save_to_context()
            self._detector_timer.start(50)

    # ---------- actions ----------
    def set_mode(self, mode):
        self.mode = mode
        self.btn_mode_points.setChecked(mode == self.MODE_POINTS)
        self.btn_mode_areas.setChecked(mode == self.MODE_AREAS)
        self.update_info()

    def clear_points_only(self):
        """Clear only roi_points, keep rois and analysis."""
        self.roi_points.clear()
        self.selected_point_idx = -1
        if hasattr(self.context, "merged_points"):
            self.context.merged_points = []
        self.update_image_label()
        self._refresh_roi_lists()
        self.save_to_context()
        if self.log_widget:
            self.log_widget.append_log("[INFO] Points cleared.")

    def reset_all(self):
        self.rois.clear()
        self.roi_points.clear()
        self.current_rect = None
        self.detected_contours = []
        self.detected_contour_labels = []
        self.selected_area_idx = -1
        self.selected_point_idx = -1

        if hasattr(self.context, "merged_points"):
            self.context.merged_points = []
        if hasattr(self.context, "analysis") and isinstance(self.context.analysis, dict):
            self.context.analysis.pop("whole_overlay", None)
            self.context.analysis.pop("overlays", None)

        self.display_roi_image()
        self._refresh_roi_lists()
        self.save_to_context()
        self._detector_timer.start(50)

    def analyze_selected(self):
        img = getattr(self.context, "image", None)
        if img is None:
            if self.log_widget:
                self.log_widget.append_log("[INFO] No image to analyze.")
            return

        res_list = []
        auto_pts = []
        contours = []
        contour_labels = []

        if hasattr(self.context, "analyze_roi") and callable(self.context.analyze_roi):
            # Ensure context.detector uses current UI params
            try:
                self._sync_params_to_context_detector()
            except Exception:
                pass
            for rect in self.rois:
                r = self.context.analyze_roi(img, rect)
                res_list.append(r)
                auto_pts.extend(r.get("centers", []))
                for s in r.get("stats", []):
                    if "contour" in s:
                        contours.append(s["contour"])
                        contour_labels.append(self._classify_contour_autok_label(s["contour"]))
        else:
            if self.log_widget:
                self.log_widget.append_log("[INFO] context.analyze_roi not implemented. Falling back to local detector.")
            # fallback: run local detector on each ROI
            for rect in self.rois:
                ov, centers, objs, counts = self._run_detector_on_rect(rect)
                res_list.append({"overlay": ov, "centers": centers, "stats": objs})
                auto_pts.extend(centers)
                for s in objs:
                    if "contour" in s:
                        contours.append(s["contour"])
                        contour_labels.append(self._classify_contour_autok_label(s["contour"]))

        # add detected centers to selected list
        self._append_points_to_selection(auto_pts)
        # remember detected contours
        self.detected_contours = contours
        self.detected_contour_labels = contour_labels

        if hasattr(self.context, "on_analysis_done"):
            self.context.on_analysis_done(res_list)

        # Show PREVIEW: base image with detected contours (not full overlay)
        img_show = self.context.image.copy()
        self._apply_mask_outline(img_show)
        self.display_image = img_show

        self.save_to_context()
        self._refresh_roi_lists()
        self.update_image_label()
        self._save_analysis_snapshot(
            mode="selected_rois",
            results_payload={
                "roi_count": len(self.rois),
                "result_count": len(res_list),
                "detected_points_added": len(auto_pts),
                "objects_per_roi": [len(r.get("stats", [])) for r in res_list],
                "analysis_source": "context.analyze_roi" if (hasattr(self.context, "analyze_roi") and callable(self.context.analyze_roi)) else "local_detector"
            }
        )

    def analyze_whole(self):
        img = getattr(self.context, "image", None)
        if img is None:
            if self.log_widget:
                self.log_widget.append_log("[INFO] No image to analyze.")
            return
        mask = getattr(self.context, "mask", None)

        if hasattr(self.context, "analyze_whole") and callable(self.context.analyze_whole):
            # Sync current UI params to context detector so analysis uses the sliders
            try:
                self._sync_params_to_context_detector()
            except Exception:
                pass

            res = self.context.analyze_whole(img, mask)

            auto_pts = res.get("centers", [])
            self._append_points_to_selection(auto_pts)

            self.detected_contours = [s["contour"] for s in res.get("stats", []) if "contour" in s]
            self.detected_contour_labels = [self._classify_contour_autok_label(s["contour"]) for s in res.get("stats", []) if "contour" in s]

            if hasattr(self.context, "on_analysis_done"):
                self.context.on_analysis_done(res)

            # Show PREVIEW: base image with detected contours (not full overlay)
            img_show = self.context.image.copy()
            self._apply_mask_outline(img_show)
            self.display_image = img_show

            self.save_to_context()
            self._refresh_roi_lists()
            self.update_image_label()
            self._save_analysis_snapshot(
                mode="whole_dish",
                results_payload={
                    "detected_points_added": len(auto_pts),
                    "objects_detected": len(res.get("stats", [])),
                    "analysis_source": "context.analyze_whole"
                }
            )
        else:
            # fallback local detector on whole image
            if self.log_widget:
                self.log_widget.append_log("[INFO] context.analyze_whole not provided - using local detector.")
            ov, centers, objs, counts = self._run_detector_on_whole()
            self._append_points_to_selection(centers)
            self.detected_contours = [s["contour"] for s in objs if "contour" in s]
            self.detected_contour_labels = [self._classify_contour_autok_label(s["contour"]) for s in objs if "contour" in s]
            # Show PREVIEW: base image with detected contours (not full overlay)
            img_show = self.context.image.copy()
            self._apply_mask_outline(img_show)
            self.display_image = img_show
            self.save_to_context()
            self._refresh_roi_lists()
            self.update_image_label()
            self._save_analysis_snapshot(
                mode="whole_dish",
                results_payload={
                    "detected_points_added": len(centers),
                    "objects_detected": len(objs),
                    "analysis_source": "local_detector"
                }
            )

    def _append_points_to_selection(self, pts, min_dist_px=8):
        """Append points to roi_points, avoiding near-duplicates."""
        for (nx, ny) in pts:
            keep = True
            for (px, py) in self.roi_points:
                if math.hypot(nx - px, ny - py) < min_dist_px:
                    keep = False
                    break
            if keep:
                self.roi_points.append((int(nx), int(ny)))
        # after bulk add, keep list in sync
        self._refresh_roi_lists()

    # ---------- Detector helpers ----------
    def _on_num_colors_value_changed(self, _value):
        # If Auto-K centers are active, changing Num Colors should recompute centers.
        if hasattr(self, '_autok_centers') and getattr(self, '_autok_centers', None):
            self._on_autok()
            return
        self._detector_timer.start(100)

    def _autok_centers_to_hue_ranges(self, centers, tol=8):
        if not centers:
            return None
        ranges = []
        for c in centers:
            try:
                h = int(c[0]) if isinstance(c, (list, tuple)) else int(c)
            except Exception:
                continue
            h0 = max(0, h - int(tol))
            h1 = min(179, h + int(tol))
            ranges.append((h0, h1))
        return ranges if ranges else None

    def _apply_detector_params(self):
        # push UI params into detector
        # If Auto-K was used, convert centers to hue ranges so sat/value sliders still affect detection.
        hue_centers = None
        hue_ranges = None
        autok_centers = getattr(self, '_autok_centers', None)
        if autok_centers:
            hue_ranges = self._autok_centers_to_hue_ranges(autok_centers, tol=8)

        self.detector.set_params(
            hue_ranges=hue_ranges,
            hue_centers=hue_centers,
            use_hs_soft_assignment=False,
            split_threshold=self.slider_split.value(),
            saturation_min=self.slider_sat.value(),
            value_min=self.slider_val.value(),
            morph_close_radius=self.slider_close.value(),
            morph_open_radius=self.slider_open.value(),
            use_texture=self.chk_texture.isChecked(),
            use_edge_split=self.chk_edge.isChecked(),
            color_calibration=self.chk_calib.isChecked()
        )

    def _sync_params_to_context_detector(self):
        # Mirror current UI detection params into the pipeline context detector
        if not hasattr(self, 'context') or not hasattr(self.context, 'detector'):
            return
        hue_centers = None
        hue_ranges = None
        autok_centers = getattr(self, '_autok_centers', None)
        if autok_centers:
            hue_ranges = self._autok_centers_to_hue_ranges(autok_centers, tol=8)
        params = dict(
            hue_ranges=hue_ranges,
            hue_centers=hue_centers,
            use_hs_soft_assignment=False,
            split_threshold=self.slider_split.value(),
            saturation_min=self.slider_sat.value(),
            value_min=self.slider_val.value(),
            morph_close_radius=self.slider_close.value(),
            morph_open_radius=self.slider_open.value(),
            use_texture=self.chk_texture.isChecked(),
            use_edge_split=self.chk_edge.isChecked(),
            color_calibration=self.chk_calib.isChecked()
        )
        try:
            self.context.detector.set_params(**params)
        except Exception:
            # best-effort; ignore failures
            pass

    def _legend_color(self, idx):
        if hasattr(self, "detector") and self.detector is not None and hasattr(self.detector, "_legend_color"):
            return self.detector._legend_color(idx)
        fallback_palette = [
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 0),
            (255, 0, 255),
            (0, 255, 255),
        ]
        return fallback_palette[idx % len(fallback_palette)]

    def _on_detector_params_apply(self):
        # apply params and run a preview on currently visible region (ROIs if present else whole)
        self._apply_detector_params()
        fresh_contours = []
        fresh_labels = []
        # run on whole if no ROIs selected, else on ALL ROIs for preview
        if len(self.rois) > 0:
            # preview ALL ROIs - combine results into single display
            display_base = self.context.image.copy()
            
            for rect in self.rois:
                ov, centers, objs, counts = self._run_detector_on_rect(rect)
                for obj in objs:
                    if "contour" in obj:
                        fresh_contours.append(obj["contour"])
                        fresh_labels.append(self._classify_contour_autok_label(obj["contour"]))

            self.display_image = display_base
        else:
            ov, centers, objs, counts = self._run_detector_on_whole()
            for obj in objs:
                if "contour" in obj:
                    fresh_contours.append(obj["contour"])
                    fresh_labels.append(self._classify_contour_autok_label(obj["contour"]))

            display_base = self.context.image.copy()
            self.display_image = display_base

        self.detected_contours = fresh_contours
        self.detected_contour_labels = fresh_labels
        self._apply_mask_outline(self.display_image)
        self.update_image_label()

    def _classify_contour_autok_label(self, contour):
        centers = getattr(self, '_autok_centers', None)
        img = getattr(self.context, 'image', None)
        return classify_contour_to_center(img, contour, centers)

    def _run_detector_on_rect(self, rect):
        img = getattr(self.context, "image", None)
        if img is None:
            return None, [], [], []
        mask = getattr(self.context, "mask", None)
        # detector.detect accepts roi_rect
        ov, centers, objs, counts = self.detector.detect(img, mask, roi_rect=rect, save_debug=False)
        return ov, centers, objs, counts

    def _run_detector_on_whole(self):
        img = getattr(self.context, "image", None)
        if img is None:
            return None, [], [], []
        mask = getattr(self.context, "mask", None)
        ov, centers, objs, counts = self.detector.detect(img, mask, roi_rect=None, save_debug=False)
        return ov, centers, objs, counts

    def _centers_to_positions(self, image_bgr, centers, valid_mask=None):
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

        diff_h = np.abs(h_flat.reshape(-1, 1) - ch)
        diff_h = np.minimum(diff_h, 179.0 - diff_h) / 179.0
        diff_s = np.abs(s_flat.reshape(-1, 1) - cs) / 255.0
        dist = np.sqrt(diff_h ** 2 + diff_s ** 2)
        labels = np.argmin(dist, axis=1)

        labels_img = labels.reshape(h_img, w_img)
        centers_pos = []
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        for ci in range(centers_arr.shape[0]):
            mask = (labels_img == ci).astype('uint8') * 255
            if valid_mask is not None:
                vm = (valid_mask > 0).astype('uint8')
                mask = cv2.bitwise_and(mask, vm.astype('uint8') * 255)

            if np.count_nonzero(mask) == 0:
                centers_pos.append(None)
                continue

            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

            num_labels, labels_cc, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
            if num_labels <= 1:
                centers_pos.append(None)
                continue
            areas = stats[1:, cv2.CC_STAT_AREA]
            if areas.size == 0:
                centers_pos.append(None)
                continue
            max_idx = int(np.argmax(areas)) + 1
            cx, cy = centroids[max_idx]
            centers_pos.append((int(cx), int(cy)))

        return centers_pos

    def _on_export_csv(self):
        # run detection over whole image and export CSV
        img = getattr(self.context, "image", None)
        if img is None:
            if self.log_widget:
                self.log_widget.append_log("[INFO] No image to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save detection CSV", os.path.expanduser("~"), "CSV files (*.csv)")
        if not path:
            return
        ov, centers, objs, counts = self._run_detector_on_whole()
        try:
            self.detector.export_csv(objs, path)
            if self.log_widget:
                self.log_widget.append_log(f"[SAVE] CSV -> {path}")
        except Exception as e:
            if self.log_widget:
                self.log_widget.append_log(f"[ERROR] Export CSV failed: {e}")

    def _toggle_fullscreen(self, checked):
        win = self.window()
        try:
            if win is not None:
                win.showNormal()
        except Exception:
            pass

    # ---------- Swatches for interactive tuning ----------
    def _build_swatches_from_centers(self, centers):
        # centers: list of (h,s)
        self._clear_swatches()
        for i, (h, s) in enumerate(centers):
            rgb = cv2.cvtColor(np.uint8([[[h, s, 200]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); border: 1px solid #222;")
            btn.clicked.connect(lambda _, idx=i: self._on_swatch_clicked(idx))
            self._swatches_layout.addWidget(btn)
        self._swatches_layout.addStretch()

    def _build_swatches_from_ranges(self, ranges):
        self._clear_swatches()
        for i, (h0, h1) in enumerate(ranges):
            mid = (h0 + h1) // 2
            rgb = cv2.cvtColor(np.uint8([[[mid, 200, 200]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); border: 1px solid #222;")
            btn.clicked.connect(lambda _, idx=i: self._on_swatch_clicked(idx))
            self._swatches_layout.addWidget(btn)
        self._swatches_layout.addStretch()

    def _clear_swatches(self):
        while self._swatches_layout.count():
            w = self._swatches_layout.takeAt(0)
            if w.widget():
                w.widget().deleteLater()

    def _on_swatch_clicked(self, idx):
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
            if hasattr(self, '_autok_centers') and self._autok_centers:
                centers_h = [c[0] for c in self._autok_centers]
                centers_h_sorted = sorted(centers_h)
                ranges = []
                for i, c in enumerate(centers_h_sorted):
                    min_h = max(0, c - htol_v)
                    max_h = min(179, c + htol_v)
                    ranges.append((min_h, max_h))
                self.hue_ranges = ranges
                delattr(self, '_autok_centers')
            else:
                if 0 <= idx < len(self.hue_ranges):
                    c0, c1 = self.hue_ranges[idx]
                    mid = (c0 + c1) // 2
                    min_h = max(0, mid - htol_v)
                    max_h = min(179, mid + htol_v)
                    self.hue_ranges[idx] = (min_h, max_h)
            self._detector_timer.start(50)

    # ---------- Auto-K (kmeans on H+S) ----------
    def _on_autok(self):
        img = getattr(self.context, 'image', None)
        if img is None:
            if self.log_widget:
                self.log_widget.append_log('[INFO] No image for Auto-K')
            return

        mask = getattr(self.context, 'mask', None)
        valid = mask > 0 if mask is not None else None
        rois = list(self.rois) if self.rois else None
        centers = compute_autok_centers(
            image_bgr=img,
            k=self.slider_num_colors.value(),
            valid_mask=valid,
            rois=rois,
            saturation_min=self.slider_sat.value(),
            value_min=self.slider_val.value(),
            fallback_to_whole=True,
        )

        if centers:
            # store centers on widget for subsequent calls
            self._autok_centers = centers
            if self.log_widget:
                self.log_widget.append_log(f'[AUTO-K] Found {len(centers)} centers from all ROIs')
            # apply and preview
            # build swatches
            self._build_swatches_from_centers(centers)
            self._detector_timer.start(50)
        else:
            if self.log_widget:
                self.log_widget.append_log('[AUTO-K] No centers found')

    def _compute_hs_kmeans_centers_from_hs(self, hs, k=6):
        if hs is None or hs.shape[0] == 0:
            return []
        try:
            hs_f = hs.astype(np.float32)
            n = hs_f.shape[0]
            if n > 50000:
                idx = np.random.choice(n, 50000, replace=False)
                hs_f = hs_f[idx]

            dummy_hsv = np.zeros((hs_f.shape[0], 1, 3), dtype=np.uint8)
            dummy_hsv[:, 0, 0] = np.clip(hs_f[:, 0], 0, 179).astype(np.uint8)
            dummy_hsv[:, 0, 1] = np.clip(hs_f[:, 1], 0, 255).astype(np.uint8)
            dummy_hsv[:, 0, 2] = 200
            dummy_bgr = cv2.cvtColor(dummy_hsv, cv2.COLOR_HSV2BGR)
            return compute_autok_centers(dummy_bgr, k=k, valid_mask=None, rois=None, saturation_min=0, value_min=0, fallback_to_whole=False)
        except Exception:
            return []

    def _compute_hs_kmeans_centers(self, img_bgr, k=6, valid_mask=None):
        return compute_autok_centers(
            image_bgr=img_bgr,
            k=k,
            valid_mask=valid_mask,
            rois=None,
            saturation_min=self.slider_sat.value(),
            value_min=self.slider_val.value(),
            fallback_to_whole=False,
        )

    def on_next_save(self):
        """Save annotated picture (with outline/ROIs/points/contours) and the mask. Also save slider state."""
        # Save slider positions before moving to next step
        self._save_slider_state()
        
        # If new ROIs were drawn, run detector on them automatically
        if self.rois:
            try:
                self._on_detector_params_apply()
            except Exception as e:
                if self.log_widget:
                    self.log_widget.append_log(f"[INFO] Auto-detect on new ROIs: {e}")
        
        try:
            img = getattr(self.context, "image", None)
            if img is None:
                if self.log_widget:
                    self.log_widget.append_log("[INFO] No image to save.")
                return

            out_dir = getattr(self.context, "output_dir", None) or os.path.join(os.getcwd(), "debug")
            img_path = getattr(self.context, "image_path", None)
            base = os.path.splitext(os.path.basename(img_path))[0] if isinstance(img_path, str) and img_path else "frame"
            os.makedirs(out_dir, exist_ok=True)

            # build annotated image
            out = img.copy()
            self._apply_mask_outline(out)

            # user ROIs (orange)
            for (x, y, w, h) in self.rois:
                cv2.rectangle(out, (x, y), (x + w, y + h), (0, 180, 255), 2)

            # analyzer contours (blue)
            for poly in getattr(self, "detected_contours", []):
                cnt = np.array(poly, dtype=np.int32)
                if cnt.ndim == 2 and len(cnt) >= 3:
                    cv2.polylines(out, [cnt], isClosed=True, color=(255, 0, 0), thickness=2)

            # points (green filled)
            for (px, py) in self.roi_points:
                cv2.circle(out, (int(px), int(py)), 5, (0, 200, 0), -1)

            annot_path = os.path.join(out_dir, f"{base}_annotated.png")
            cv2.imwrite(annot_path, out)
            if self.log_widget:
                self.log_widget.append_log(f"[SAVE] Annotated image -> {annot_path}")

            # save mask (if present)
            mask = getattr(self.context, "mask", None)
            if mask is not None:
                mask_u8 = mask.astype(np.uint8) if mask.dtype != np.uint8 else mask
                mask_path = os.path.join(out_dir, f"{base}_mask.png")
                cv2.imwrite(mask_path, mask_u8)
                if self.log_widget:
                    self.log_widget.append_log(f"[SAVE] Mask -> {mask_path}")
            
            # Transfer the annotated display image to context for picking widget to use
            self.context.display_image = out

        except Exception as e:
            import traceback
            traceback.print_exc()
            if self.log_widget:
                self.log_widget.append_log(f"[ERROR] on_next_save failed: {e}")

    def _clear_analysis_overlays(self):
        """Drop cached overlay frames/legends so the next render uses the fresh base image."""
        if hasattr(self.context, "analysis") and isinstance(self.context.analysis, dict):
            self.context.analysis.pop("overlays", None)
            self.context.analysis.pop("whole_overlay", None)
            # optional: if you store derived stats that drive legends, clear them too
            self.context.analysis.pop("legend", None)
            self.context.analysis.pop("category_counts", None)

    # ---------- keyboard delete shortcuts ----------
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            # prefer deleting the focused list selection
            if self.list_points.hasFocus():
                self._delete_selected_point()
            elif self.list_areas.hasFocus():
                self._delete_selected_area()
            else:
                # fallback: delete currently selected (if any)
                if 0 <= self.selected_point_idx < len(self.roi_points):
                    self._delete_selected_point()
                elif 0 <= self.selected_area_idx < len(self.rois):
                    self._delete_selected_area()
        else:
            super().keyPressEvent(event)

