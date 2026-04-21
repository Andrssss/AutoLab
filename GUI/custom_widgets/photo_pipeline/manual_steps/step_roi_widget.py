from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QListWidget, QListWidgetItem, QFrame, QSlider, QCheckBox, QFileDialog, QSpinBox, QDialog, QDialogButtonBox, QGroupBox, QSizePolicy, QScrollArea, QApplication
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QPoint, QTimer
import cv2
import numpy as np
import math
import os
import yaml
from File_managers import config_manager
from Image_processing.BacteriaDetector import BacteriaDetector
from Image_processing.overlay_draw import draw_mask_outline, draw_rois, draw_drag_rect, draw_contours, draw_points, draw_points_simple

class StepROIWidget(QWidget):
    MODE_POINTS = 0
    MODE_AREAS  = 1

    DETECTOR_PARAMS_PATH = os.path.join(config_manager.CONFIG_DIR, "detector_params.yaml")

    def __init__(self, context, image_path=None, log_widget=None, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(900, 620)
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

        self.instructions = QLabel("Mode: POINTS - Left-click add. Switch mode to AREAS to draw rectangles.")
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
        self.slider_sat = QSlider(Qt.Horizontal)
        self.slider_sat.setRange(0, 255)
        self.slider_sat.setValue(50)
        self.slider_val = QSlider(Qt.Horizontal)
        self.slider_val.setRange(0, 255)
        self.slider_val.setValue(50)

        # realtime debounce timer
        self._detector_timer = QTimer(self)
        self._detector_timer.setSingleShot(True)
        self._detector_timer.timeout.connect(self._on_detector_params_apply)

        # detector instance
        self.detector = BacteriaDetector()

        # connect sliders to debounce
        self.slider_sat.valueChanged.connect(lambda _: self._detector_timer.start(100))
        self.slider_val.valueChanged.connect(lambda _: self._detector_timer.start(100))


        # Areas list
        lbl_areas = QLabel("Areas")
        self.list_areas = QListWidget()
        self.list_areas.itemSelectionChanged.connect(self._on_area_selected)
        self.btn_area_delete = QPushButton("Delete (Area)")
        self.btn_area_delete.clicked.connect(self._delete_selected_area)

        # Points list
        lbl_points = QLabel("Points")
        self.list_points = QListWidget()
        self.list_points.itemSelectionChanged.connect(self._on_point_selected)
        self.btn_point_delete = QPushButton("Delete (Point)")
        self.btn_point_delete.clicked.connect(self._delete_selected_point)

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
        roi_group.setLayout(roi_layout)

        detector_group = QGroupBox("Bacteria Detector")
        detector_layout = QVBoxLayout()
        detector_layout.setSpacing(6)
        detector_layout.addWidget(QLabel("Saturation Min"))
        detector_layout.addWidget(self.slider_sat)
        detector_layout.addWidget(QLabel("Value Min"))
        detector_layout.addWidget(self.slider_val)
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
        # enable key events
        self.setFocusPolicy(Qt.StrongFocus)

    # ---------- Slider state persistence ----------
    def _save_slider_state(self):
        """Save all slider positions to YAML config file."""
        try:
            state = {
                "saturation_min": self.slider_sat.value(),
                "value_min": self.slider_val.value(),
            }
            path = self.DETECTOR_PARAMS_PATH
            with open(path, "w") as f:
                yaml.dump(state, f, default_flow_style=False)
        except Exception as e:
            if self.log_widget:
                self.log_widget.append_log(f"[WARN] Failed to save slider state: {e}")

    def _load_slider_state(self):
        """Load slider positions from YAML config file if available."""
        try:
            path = self.DETECTOR_PARAMS_PATH
            if not os.path.exists(path):
                return
            with open(path, "r") as f:
                state = yaml.safe_load(f)
            if not state:
                return
            self.slider_sat.setValue(state.get("saturation_min", 50))
            self.slider_val.setValue(state.get("value_min", 50))
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

        # apply initial detector params and run preview after UI renders
        self._apply_detector_params()
        if getattr(self.context, "image", None) is not None:
            self._detector_timer.start(50)
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

    

    def _compose_visualized_image(self):
        if self.display_image is None:
            return None

        img = self.display_image.copy()
        draw_rois(img, self.rois, selected_idx=self.selected_area_idx)
        draw_drag_rect(img, self.current_rect)
        draw_contours(img, getattr(self, "detected_contours", []))
        draw_points(img, self.roi_points, selected_idx=self.selected_point_idx,
                    selected_radius=self.selected_point_radius,
                    halo=self.selected_point_halo,
                    marker_size=self.unselected_marker_size)
        merged = getattr(self.context, "merged_points", None)
        if merged:
            draw_points_simple(img, merged, color=(0, 200, 0), radius=5, thickness=2)
        return img

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
            self.instructions.setText("Mode: POINTS - Left click: add point")
        else:
            self.instructions.setText("Mode: AREAS - Drag to draw rectangle | Right click: delete nearest area")

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
        draw_mask_outline(img, mask, color=(255, 0, 0), thickness=3)
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
            if self.mode == self.MODE_AREAS and self.rois:
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

        # Ensure analysis uses the latest slider/checkbox values immediately
        self._prepare_detector_for_analysis()

        res_list = []
        auto_pts = []
        contours = []

        self._sync_params_to_context_detector()
        for rect in self.rois:
            try:
                overlay, centers, objs = self.context.detector.detect(
                    image_bgr=img,
                    full_mask=self.context.mask,
                    roi_rect=rect,
                )
                r = {"rect": rect, "centers": centers, "stats": objs}
                self.context.analysis.setdefault("overlays", []).append(overlay)
            except Exception:
                if self.log_widget:
                    self.log_widget.append_log(f"[WARN] analyze_roi failed for rect {rect}")
                continue
            res_list.append(r)
            auto_pts.extend(r.get("centers", []))
            for s in r.get("stats", []):
                if "contour" in s:
                    contours.append(s["contour"])

        # add detected centers to selected list
        self._append_points_to_selection(auto_pts)
        # remember detected contours
        self.detected_contours = contours

        if hasattr(self.context, "on_analysis_done"):
            self.context.on_analysis_done(res_list)

        # Show PREVIEW: base image with detected contours (not full overlay)
        img_show = self.context.image.copy()
        self._apply_mask_outline(img_show)
        self.display_image = img_show

        self.save_to_context()
        self._refresh_roi_lists()
        self.update_image_label()

    def analyze_whole(self):
        img = getattr(self.context, "image", None)
        if img is None:
            if self.log_widget:
                self.log_widget.append_log("[INFO] No image to analyze.")
            return

        # Ensure analysis uses the latest slider/checkbox values immediately
        self._prepare_detector_for_analysis()

        mask = getattr(self.context, "mask", None)

        self._sync_params_to_context_detector()
        overlay, centers, objs = self.context.detector.detect(
            image_bgr=img,
            full_mask=mask,
            roi_rect=None,
        )
        self.context.analysis["whole_overlay"] = overlay
        res = {"centers": centers, "stats": objs}

        auto_pts = res.get("centers", [])
        self._append_points_to_selection(auto_pts)

        self.detected_contours = [s["contour"] for s in objs if "contour" in s]

        if hasattr(self.context, "on_analysis_done"):
            self.context.on_analysis_done(res)

        img_show = self.context.image.copy()
        self._apply_mask_outline(img_show)
        self.display_image = img_show

        self.save_to_context()
        self._refresh_roi_lists()
        self.update_image_label()

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
        self._refresh_roi_lists()

    def _prepare_detector_for_analysis(self):
        """Flush pending UI detector changes so Analyze uses current values."""
        try:
            if hasattr(self, "_detector_timer") and self._detector_timer.isActive():
                self._detector_timer.stop()
        except Exception:
            pass

        # Apply to local preview detector immediately
        try:
            self._apply_detector_params()
        except Exception:
            pass

        # Best-effort direct sync to context detector too
        try:
            self._sync_params_to_context_detector()
        except Exception:
            pass

    # ---------- Detector helpers ----------
    def _apply_detector_params(self):
        self.detector.set_params(
            saturation_min=self.slider_sat.value(),
            value_min=self.slider_val.value()
        )

    def _sync_params_to_context_detector(self):
        if not hasattr(self, 'context') or not hasattr(self.context, 'detector'):
            return
        params = dict(
            saturation_min=self.slider_sat.value(),
            value_min=self.slider_val.value()
        )
        try:
            self.context.detector.set_params(**params)
        except Exception:
            pass

    def _on_detector_params_apply(self):
        # apply params and run a preview on currently visible region (ROIs if present else whole)
        self._apply_detector_params()
        fresh_contours = []
        rects = self.rois if self.rois else [None]
        for rect in rects:
            _, _, objs = self._run_detector(rect)
            for obj in objs:
                if "contour" in obj:
                    fresh_contours.append(obj["contour"])

        self.display_image = self.context.image.copy()

        self.detected_contours = fresh_contours
        self._apply_mask_outline(self.display_image)
        self.update_image_label()

    def _run_detector(self, rect=None):
        img = getattr(self.context, "image", None)
        if img is None:
            return None, [], []
        mask = getattr(self.context, "mask", None)
        ov, centers, objs = self.detector.detect(img, mask, roi_rect=rect)
        return ov, centers, objs

    def on_next_save(self):
        self._save_slider_state()

        img = getattr(self.context, "image", None)
        if img is None:
            if self.log_widget:
                self.log_widget.append_log("[INFO] No image to save.")
            return

        out = img.copy()
        self._apply_mask_outline(out)
        draw_rois(out, self.rois)
        draw_contours(out, getattr(self, "detected_contours", []))
        draw_points_simple(out, self.roi_points, color=(0, 200, 0), radius=5, thickness=-1)

        self.context.display_image = out

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

