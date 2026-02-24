from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QListWidget, QListWidgetItem, QFrame, QSlider, QCheckBox, QFileDialog, QSpinBox
from PyQt5.QtGui import QPixmap, QImage, QKeySequence
from PyQt5.QtCore import Qt, QPoint, QTimer
import cv2
import numpy as np
import math
import os
from Image_processing.BacteriaDetector import BacteriaDetector

class StepROIWidget(QWidget):
    MODE_POINTS = "points"
    MODE_AREAS  = "areas"

    def __init__(self, context, image_path=None, log_widget=None, parent=None):
        super().__init__(parent)
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
        # main layout: image left, side panel right
        main = QHBoxLayout(self)

        # left: image + controls
        left = QVBoxLayout()
        self.image_label = QLabel("Image not loaded")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(800, 600)
        self.image_label.setFrameShape(QFrame.StyledPanel)
        self.image_label.mousePressEvent = self.on_mouse_press
        self.image_label.mouseMoveEvent = self.on_mouse_move
        self.image_label.mouseReleaseEvent = self.on_mouse_release

        self.instructions = QLabel("Mode: POINTS — Left-click add / Right-click remove • Switch mode to AREAS to drag rectangles.")
        self.instructions.setAlignment(Qt.AlignCenter)

        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignTop)

        # nav / actions
        self.prev_btn = QPushButton("◀ Previous")
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.on_next_save)
        self.reset_btn = QPushButton("🧹 Reset")
        self.reset_btn.clicked.connect(self.reset_all)

        self.btn_mode_points = QPushButton("● Points")
        self.btn_mode_points.setCheckable(True)
        self.btn_mode_points.setChecked(True)
        self.btn_mode_points.clicked.connect(lambda: self.set_mode(self.MODE_POINTS))

        self.btn_mode_areas = QPushButton("▭ Areas")
        self.btn_mode_areas.setCheckable(True)
        self.btn_mode_areas.clicked.connect(lambda: self.set_mode(self.MODE_AREAS))

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.btn_mode_points)
        mode_layout.addWidget(self.btn_mode_areas)
        mode_layout.addStretch()
        mode_layout.addWidget(self.reset_btn)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addStretch()
        # (Analyze gombok maradnak itt, ha a kontextusban megvannak)
        self.btn_analyze_rois = QPushButton("X - Analyze Selected ROIs")
        self.btn_analyze_rois.clicked.connect(self.analyze_selected)
        self.btn_analyze_whole = QPushButton("O - Analyze Whole Dish")
        self.btn_analyze_whole.clicked.connect(self.analyze_whole)
        nav_layout.addWidget(self.btn_analyze_rois)
        nav_layout.addWidget(self.btn_analyze_whole)
        nav_layout.addWidget(self.next_btn)

        left.addWidget(self.image_label)
        left.addLayout(mode_layout)
        left.addWidget(self.instructions)
        left.addWidget(self.info_label)
        left.addLayout(nav_layout)

        # right: side panel with lists
        right = QVBoxLayout()

        # --- Detector controls ---
        det_label = QLabel("Bacteria Detector")
        det_label.setStyleSheet("font-weight: bold;")
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

        self.btn_fullscreen = QPushButton("□ Maximize")
        self.btn_fullscreen.setCheckable(True)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)

        # realtime debounce timer
        self._detector_timer = QTimer(self)
        self._detector_timer.setSingleShot(True)
        self._detector_timer.timeout.connect(self._on_detector_params_apply)

        # detector instance
        self.detector = BacteriaDetector()

        # connect sliders to debounce
        self.slider_num_colors.valueChanged.connect(lambda _: self._detector_timer.start(250))
        self.slider_split.valueChanged.connect(lambda _: self._detector_timer.start(250))
        self.slider_sat.valueChanged.connect(lambda _: self._detector_timer.start(250))
        self.slider_val.valueChanged.connect(lambda _: self._detector_timer.start(250))
        self.slider_close.valueChanged.connect(lambda _: self._detector_timer.start(250))
        self.slider_open.valueChanged.connect(lambda _: self._detector_timer.start(250))
        self.chk_texture.stateChanged.connect(lambda _: self._detector_timer.start(250))
        self.chk_edge.stateChanged.connect(lambda _: self._detector_timer.start(250))
        self.chk_calib.stateChanged.connect(lambda _: self._detector_timer.start(250))
        # Auto-K button
        self.btn_auto_k = QPushButton("Auto-K")
        self.btn_auto_k.clicked.connect(self._on_autok)
        self.btn_auto_k.setToolTip("Run k-means on H+S to compute color centers from the image")


        # Areas list
        lbl_areas = QLabel("Területek (Areas)")
        self.list_areas = QListWidget()
        self.list_areas.itemSelectionChanged.connect(self._on_area_selected)
        self.list_areas.itemDoubleClicked.connect(self._on_area_double_clicked)
        self.btn_area_delete = QPushButton("Törlés (Area)")
        self.btn_area_delete.clicked.connect(self._delete_selected_area)

        # Points list
        lbl_points = QLabel("✚ Pontok (Points)")
        self.list_points = QListWidget()
        self.list_points.itemSelectionChanged.connect(self._on_point_selected)
        self.list_points.itemDoubleClicked.connect(self._on_point_double_clicked)
        self.btn_point_delete = QPushButton("Törlés (Point)")
        self.btn_point_delete.clicked.connect(self._delete_selected_point)

        # Quick help for deletion
        hint = QLabel("Tipp: kijelölés után nyomd meg a Delete gombot is működik.")
        hint.setStyleSheet("color: gray; font-size: 11px;")

        right.addWidget(lbl_areas)
        right.addWidget(self.list_areas, 1)
        right.addWidget(self.btn_area_delete)
        right.addSpacing(8)
        right.addWidget(lbl_points)
        right.addWidget(self.list_points, 1)
        right.addWidget(self.btn_point_delete)
        right.addSpacing(8)
        right.addWidget(hint)

        # detector controls placement
        right.addSpacing(6)
        right.addWidget(det_label)
        right.addWidget(QLabel("Num Colors"))
        right.addWidget(self.slider_num_colors)
        right.addWidget(QLabel("Split Threshold %"))
        right.addWidget(self.slider_split)
        right.addWidget(QLabel("Saturation Min"))
        right.addWidget(self.slider_sat)
        right.addWidget(QLabel("Value Min"))
        right.addWidget(self.slider_val)
        right.addWidget(QLabel("Close Radius"))
        right.addWidget(self.slider_close)
        right.addWidget(QLabel("Open Radius"))
        right.addWidget(self.slider_open)
        right.addWidget(self.chk_texture)
        right.addWidget(self.chk_edge)
        right.addWidget(self.chk_calib)
        right.addWidget(self.btn_auto_k)
        right.addWidget(self.btn_export_csv)
        right.addWidget(self.btn_fullscreen)

        main.addLayout(left, 3)
        main.addLayout(right, 1)

        self.display_image = None
        self.scaled_display_size = None

        self.load_from_context()
        self._refresh_roi_lists()
        right.addWidget(self.btn_auto_k)
        # swatches area
        self._swatches_container = QWidget()
        self._swatches_layout = QHBoxLayout()
        self._swatches_container.setLayout(self._swatches_layout)
        right.addWidget(self._swatches_container)
        # enable key events
        self.setFocusPolicy(Qt.StrongFocus)

    # ---------- context ----------
    def load_from_context(self):
        if getattr(self.context, "image", None) is not None:
            self.display_roi_image()
        else:
            self.image_label.setText("❌ No image")
        self.update_info()

        # apply initial detector params and run a quick preview
        self._apply_detector_params()
        self._detector_timer.start(10)
        # respect pipeline fullscreen flag
        try:
            if getattr(self.context, "pipeline_fullscreen", False):
                win = self.window()
                if win is not None:
                    win.showMaximized()
        except Exception:
            pass

    def save_to_context(self):
        # keep original keys for backward compatibility
        self.context.rois = self.rois
        self.context.rois_areas = self.rois
        self.context.roi_points = self.roi_points

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
        for poly in getattr(self, "detected_contours", []):
            cnt = np.array(poly, dtype=np.int32)
            if cnt.ndim == 2 and len(cnt) >= 3:
                cv2.polylines(img, [cnt], isClosed=True, color=(255, 0, 0), thickness=2)

        # selected points (red crosses + labels) + highlight selected (filled circle)
        # selected points (highlight selected with big red dot + white halo)
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

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            self.image_label.width(), self.image_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.scaled_display_size = pixmap.size()
        self.image_label.setPixmap(pixmap)

        self.update_info()

    def update_info(self):
        txt = f"Areas: {len(self.rois)}   •   ✚ Points: {len(self.roi_points)}"
        if getattr(self.context, "mask", None) is None:
            txt += "   •   No Petri mask"
        self.info_label.setText(txt)

        if self.mode == self.MODE_POINTS:
            self.instructions.setText("Mode: POINTS — Bal klikk: pont felvétele • Jobb klikk: legközelebbi pont törlése • Dupla klikk a képen: Analyze selected")
        else:
            self.instructions.setText("Mode: AREAS — Húzással téglalap • Jobb klikk: legközelebbi area törlése • Dupla klikk a képen: Analyze selected")

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

    # ---------- actions ----------
    def set_mode(self, mode):
        self.mode = mode
        self.btn_mode_points.setChecked(mode == self.MODE_POINTS)
        self.btn_mode_areas.setChecked(mode == self.MODE_AREAS)
        self.update_info()

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

    def analyze_selected(self):
        img = getattr(self.context, "image", None)
        if img is None:
            if self.log_widget:
                self.log_widget.append_log("[INFO] No image to analyze.")
            return

        res_list = []
        auto_pts = []
        contours = []

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
                contours.extend([s["contour"] for s in r.get("stats", []) if "contour" in s])
        else:
            if self.log_widget:
                self.log_widget.append_log("[INFO] context.analyze_roi not implemented. Falling back to local detector.")
            # fallback: run local detector on each ROI
            for rect in self.rois:
                ov, centers, objs, counts = self._run_detector_on_rect(rect)
                res_list.append({"overlay": ov, "centers": centers, "stats": objs})
                auto_pts.extend(centers)
                contours.extend([s["contour"] for s in objs if "contour" in s])

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

            if hasattr(self.context, "on_analysis_done"):
                self.context.on_analysis_done(res)

            # Show PREVIEW: base image with detected contours (not full overlay)
            img_show = self.context.image.copy()
            self._apply_mask_outline(img_show)
            self.display_image = img_show

            self.save_to_context()
            self._refresh_roi_lists()
            self.update_image_label()
        else:
            # fallback local detector on whole image
            if self.log_widget:
                self.log_widget.append_log("[INFO] context.analyze_whole not provided — using local detector.")
            ov, centers, objs, counts = self._run_detector_on_whole()
            self._append_points_to_selection(centers)
            self.detected_contours = [s["contour"] for s in objs if "contour" in s]
            # Show PREVIEW: base image with detected contours (not full overlay)
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
        # after bulk add, keep list in sync
        self._refresh_roi_lists()

    # ---------- Detector helpers ----------
    def _apply_detector_params(self):
        # push UI params into detector
        # For now hue_centers left to auto-detection inside detector; we map num colors to that internal use later
        # ensure centers are passed when present
        hue_centers = getattr(self, '_autok_centers', None)
        self.detector.set_params(
            hue_centers=hue_centers,
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
        hue_centers = getattr(self, '_autok_centers', None)
        params = dict(
            hue_centers=hue_centers,
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

    def _on_detector_params_apply(self):
        # apply params and run a preview on currently visible region (ROIs if present else whole)
        self._apply_detector_params()
        # run on whole if no ROIs selected, else on ALL ROIs for preview
        if len(self.rois) > 0:
            # preview ALL ROIs - combine results into single display
            display_base = self.context.image.copy()
            all_centers = []
            
            for roi_idx, rect in enumerate(self.rois):
                ov, centers, objs, counts = self._run_detector_on_rect(rect)
                all_centers.extend(centers)
                # Draw detected contours from this ROI directly onto the base image
                for obj in objs:
                    if "contour" in obj:
                        cnt = np.array(obj["contour"], dtype=np.int32)
                        if cnt.ndim == 2 and len(cnt) >= 3:
                            cv2.polylines(display_base, [cnt], isClosed=True, color=(255, 0, 0), thickness=2)
            
            # overlay autok centers if available
            centers_pos = None
            centers_hs = getattr(self, '_autok_centers', None)
            if centers_hs:
                centers_pos = self._centers_to_positions(self.context.image, centers_hs, valid_mask=None)
            
            if centers_pos:
                display_img = display_base.copy()
                for i, p in enumerate(centers_pos):
                    if p is None:
                        continue
                    cv2.circle(display_img, (int(p[0]), int(p[1])), 6, (0,0,0), -1)
                    cv2.circle(display_img, (int(p[0]), int(p[1])), 4, self._legend_color(i), -1)
                    cv2.putText(display_img, f"C{i+1}", (int(p[0]) + 6, int(p[1]) + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
                self.display_image = display_img
            else:
                self.display_image = display_base
        else:
            ov, centers, objs, counts = self._run_detector_on_whole()
            centers_pos = None
            centers_hs = getattr(self, '_autok_centers', None)
            if centers_hs:
                centers_pos = self._centers_to_positions(self.context.image, centers_hs, valid_mask=None)
            if centers_pos:
                ov2 = ov.copy()
                for i, p in enumerate(centers_pos):
                    if p is None:
                        continue
                    cv2.circle(ov2, (int(p[0]), int(p[1])), 6, (0,0,0), -1)
                    cv2.circle(ov2, (int(p[0]), int(p[1])), 4, self._legend_color(i), -1)
                    cv2.putText(ov2, f"C{i+1}", (int(p[0]) + 6, int(p[1]) + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
                self.display_image = ov2
            else:
                self.display_image = ov
        self._apply_mask_outline(self.display_image)
        self.update_image_label()

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
            if checked:
                win.showMaximized()
            else:
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

        # Process ALL ROI areas if present (not just the first one)
        if len(self.rois) > 0:
            # Combine all ROI areas into a single image for color analysis
            rois_combined = []
            mask_combined = []
            for rect in self.rois:
                x, y, w, h = rect
                rois_combined.append(img[y:y+h, x:x+w])
                mask = getattr(self.context, 'mask', None)
                if mask is not None:
                    mask_combined.append(mask[y:y+h, x:x+w])
            
            # Concatenate all ROI images vertically for analysis
            if rois_combined:
                img_proc = np.vstack(rois_combined)
                if mask_combined:
                    mask_proc = np.vstack(mask_combined)
                    valid = mask_proc > 0
                else:
                    valid = None
            else:
                img_proc = img
                valid = None
        else:
            img_proc = img
            mask = getattr(self.context, 'mask', None)
            valid = mask > 0 if mask is not None else None

        centers = self._compute_hs_kmeans_centers(img_proc, k=self.slider_num_colors.value(), valid_mask=valid)
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

    def _compute_hs_kmeans_centers(self, img_bgr, k=6, valid_mask=None):
        # convert to HSV and sample H+S, optionally masked
        try:
            hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        except Exception:
            return []
        H = hsv[:, :, 0].reshape(-1, 1).astype(np.float32)
        S = hsv[:, :, 1].reshape(-1, 1).astype(np.float32)
        hs = np.hstack([H, S])
        if valid_mask is not None:
            vm = valid_mask.reshape(-1)
            hs = hs[vm]
            if hs.shape[0] == 0:
                return []

        # downsample for speed if very large
        n_samples = hs.shape[0]
        if n_samples > 50000:
            idx = np.random.choice(n_samples, 50000, replace=False)
            hs_sample = hs[idx]
        else:
            hs_sample = hs

        # normalize H to [0..179], S to [0..255] as floats already
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        try:
            _, labels, centers = cv2.kmeans(hs_sample, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
        except Exception:
            return []
        centers = centers.astype(int).tolist()
        # convert to tuples (h,s)
        centers_t = [(int(c[0]), int(c[1])) for c in centers]
        return centers_t

    def on_next_save(self):
        """Save annotated picture (with outline/ROIs/points/contours) and the mask."""
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
