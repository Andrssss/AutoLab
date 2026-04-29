"""Pixel-to-millimeter calibration window.

Workflow:
1. User clicks 'Capture snapshot' -> freezes the current camera frame.
2. User clicks 3 points on the frozen image (P1, P2, P3).
3. For each point, the user manually moves the printer so the needle physically
   sits on the marked spot, then clicks 'Capture position' to query M114.
4. User enters the 3 real-world distances between the points (mm).
5. 'Calculate & Save' fits an affine transform (pixel -> gantry mm), computes
   the average px/mm scale, and the needle offset relative to the camera image
   center, then writes calibration.yaml.
"""
import os
import math
import time
import yaml
import cv2
import numpy as np
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QDoubleSpinBox, QMessageBox, QFrame
)

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "config_profiles")
CALIBRATION_FILE = os.path.join(CONFIG_DIR, "calibration.yaml")

POINT_COLORS = [QColor(255, 60, 60), QColor(60, 220, 60), QColor(60, 140, 255)]
POINT_LABELS = ["P1", "P2", "P3"]


class ClickableImageLabel(QLabel):
    """QLabel that reports clicks in image (not widget) coordinates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background-color: black;")
        self.setAlignment(Qt.AlignCenter)
        self._frame = None  # original BGR
        self._scaled_pixmap = None
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._offset_x = 0
        self._offset_y = 0
        self._points = [None, None, None]  # image-coords (px, py)
        self._active_idx = 0

    def set_frame(self, frame_bgr):
        self._frame = frame_bgr
        self._points = [None, None, None]
        self._active_idx = 0
        self._redraw()

    def set_active_index(self, idx):
        self._active_idx = idx

    def get_point(self, idx):
        return self._points[idx]

    def get_image_size(self):
        if self._frame is None:
            return None
        h, w = self._frame.shape[:2]
        return (w, h)

    def _redraw(self):
        if self._frame is None:
            return
        h, w = self._frame.shape[:2]
        rgb = cv2.cvtColor(self._frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        # draw markers on the scaled pixmap
        scaled_w, scaled_h = pix.width(), pix.height()
        self._scale_x = scaled_w / w
        self._scale_y = scaled_h / h
        self._offset_x = (self.width() - scaled_w) // 2
        self._offset_y = (self.height() - scaled_h) // 2

        painter = QPainter(pix)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        for i, pt in enumerate(self._points):
            if pt is None:
                continue
            px_disp = int(pt[0] * self._scale_x)
            py_disp = int(pt[1] * self._scale_y)
            pen = QPen(POINT_COLORS[i], 2)
            painter.setPen(pen)
            painter.drawLine(px_disp - 8, py_disp, px_disp + 8, py_disp)
            painter.drawLine(px_disp, py_disp - 8, px_disp, py_disp + 8)
            painter.drawEllipse(QPoint(px_disp, py_disp), 10, 10)
            painter.drawText(px_disp + 12, py_disp - 6, POINT_LABELS[i])
        painter.end()
        self._scaled_pixmap = pix
        self.setPixmap(pix)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._redraw()

    def mousePressEvent(self, event):
        if self._frame is None or event.button() != Qt.LeftButton:
            return
        x = event.x() - self._offset_x
        y = event.y() - self._offset_y
        if x < 0 or y < 0 or self._scale_x == 0 or self._scale_y == 0:
            return
        if x > self._scaled_pixmap.width() or y > self._scaled_pixmap.height():
            return
        img_x = int(x / self._scale_x)
        img_y = int(y / self._scale_y)
        self._points[self._active_idx] = (img_x, img_y)
        self._redraw()
        # notify parent
        parent = self.parent()
        while parent is not None and not hasattr(parent, "on_point_clicked"):
            parent = parent.parent()
        if parent is not None:
            parent.on_point_clicked(self._active_idx, img_x, img_y)


class PixelCalibrationWindow(QDialog):
    def __init__(self, g_control, camera_widget, log_widget, parent=None):
        super().__init__(parent)
        self.g_control = g_control
        self.camera_widget = camera_widget
        self.log_widget = log_widget
        self.setWindowTitle("Pixel / mm calibration")
        self.resize(1100, 800)

        # state
        self.pixel_points = [None, None, None]    # (px, py) in image coords
        self.gantry_points = [None, None, None]   # (gx, gy) mm

        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QHBoxLayout(self)

        # left: image
        left = QVBoxLayout()
        self.image_label = ClickableImageLabel(self)
        left.addWidget(self.image_label, 1)

        snap_row = QHBoxLayout()
        self.btn_snapshot = QPushButton("Capture snapshot from camera")
        self.btn_snapshot.clicked.connect(self.on_capture_snapshot)
        snap_row.addWidget(self.btn_snapshot)
        snap_row.addStretch()
        left.addLayout(snap_row)
        root.addLayout(left, 3)

        # right: controls
        right = QVBoxLayout()
        right.addWidget(self._build_points_group())
        right.addWidget(self._build_distances_group())
        right.addWidget(self._build_action_group())
        right.addStretch()
        self.lbl_result = QLabel("Calibration result will appear here.")
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setStyleSheet("font-family: Consolas; background:#222; color:#ddd; padding:6px;")
        right.addWidget(self.lbl_result)
        root.addLayout(right, 2)

    def _build_points_group(self):
        gb = QGroupBox("Points")
        grid = QGridLayout(gb)
        grid.addWidget(QLabel("<b>Point</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Pixel (x, y)</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Gantry (X, Y) mm</b>"), 0, 2)
        grid.addWidget(QLabel("<b>Action</b>"), 0, 3)

        self.lbl_px = []
        self.lbl_gantry = []
        self.btn_select = []
        self.btn_capture_pos = []
        for i in range(3):
            tag = QLabel(f"<b>{POINT_LABELS[i]}</b>")
            tag.setStyleSheet(f"color: rgb({POINT_COLORS[i].red()},{POINT_COLORS[i].green()},{POINT_COLORS[i].blue()});")
            grid.addWidget(tag, i + 1, 0)

            lp = QLabel("-")
            self.lbl_px.append(lp)
            grid.addWidget(lp, i + 1, 1)

            lg = QLabel("-")
            self.lbl_gantry.append(lg)
            grid.addWidget(lg, i + 1, 2)

            row = QHBoxLayout()
            sel = QPushButton(f"Pick {POINT_LABELS[i]} on image")
            sel.clicked.connect(lambda _, idx=i: self._activate_point(idx))
            row.addWidget(sel)
            self.btn_select.append(sel)

            cap = QPushButton("Capture pos (M114)")
            cap.clicked.connect(lambda _, idx=i: self.on_capture_position(idx))
            row.addWidget(cap)
            self.btn_capture_pos.append(cap)
            wrap = QFrame()
            wrap.setLayout(row)
            grid.addWidget(wrap, i + 1, 3)
        return gb

    def _build_distances_group(self):
        gb = QGroupBox("Real-world distances (mm)")
        grid = QGridLayout(gb)
        labels = ["P1 - P2", "P2 - P3", "P1 - P3"]
        self.spin_dist = []
        for i, lab in enumerate(labels):
            grid.addWidget(QLabel(lab), i, 0)
            sp = QDoubleSpinBox()
            sp.setRange(0.0, 10000.0)
            sp.setDecimals(3)
            sp.setSingleStep(1.0)
            sp.setSuffix(" mm")
            grid.addWidget(sp, i, 1)
            self.spin_dist.append(sp)
        return gb

    def _build_action_group(self):
        gb = QGroupBox("Calibration")
        v = QVBoxLayout(gb)
        self.btn_calc = QPushButton("Calculate && Save")
        self.btn_calc.clicked.connect(self.on_calculate_and_save)
        v.addWidget(self.btn_calc)
        return gb

    # ---------------- actions ----------------
    def on_capture_snapshot(self):
        frame = getattr(self.camera_widget, "current_frame", None)
        if frame is None:
            QMessageBox.warning(self, "No frame", "Camera has no frame yet. Start the camera first.")
            return
        self.image_label.set_frame(frame.copy())
        self.pixel_points = [None, None, None]
        self.gantry_points = [None, None, None]
        for i in range(3):
            self.lbl_px[i].setText("-")
            self.lbl_gantry[i].setText("-")
        self.log_widget.append_log("[CALIB] Snapshot frozen. Click point P1 on the image.")
        self._activate_point(0)

    def _activate_point(self, idx):
        self.image_label.set_active_index(idx)
        for i, btn in enumerate(self.btn_select):
            btn.setStyleSheet("font-weight: bold;" if i == idx else "")

    def on_point_clicked(self, idx, img_x, img_y):
        self.pixel_points[idx] = (img_x, img_y)
        self.lbl_px[idx].setText(f"({img_x}, {img_y})")
        self.log_widget.append_log(f"[CALIB] {POINT_LABELS[idx]} pixel set to ({img_x}, {img_y}).")
        if idx < 2:
            self._activate_point(idx + 1)

    def on_capture_position(self, idx):
        if not self.g_control or not self.g_control.connected:
            QMessageBox.warning(self, "Not connected", "Printer is not connected.")
            return
        # request position and read back after a short delay
        self.g_control.new_command("M114")
        # poll _current_pos for up to ~1s for a fresh value
        start = time.time()
        prev = dict(self.g_control._current_pos)
        x = y = None
        while time.time() - start < 1.0:
            time.sleep(0.05)
            cur = self.g_control._current_pos
            if cur != prev or (time.time() - start) > 0.4:
                x, y = cur.get("X"), cur.get("Y")
                break
        if x is None or y is None:
            cur = self.g_control._current_pos
            x, y = cur.get("X", 0.0), cur.get("Y", 0.0)
        self.gantry_points[idx] = (float(x), float(y))
        self.lbl_gantry[idx].setText(f"({x:.2f}, {y:.2f})")
        self.log_widget.append_log(f"[CALIB] {POINT_LABELS[idx]} gantry pos: X={x:.2f} Y={y:.2f}")

    def on_calculate_and_save(self):
        # validate
        for i in range(3):
            if self.pixel_points[i] is None:
                QMessageBox.warning(self, "Missing", f"Pixel point {POINT_LABELS[i]} not set.")
                return
            if self.gantry_points[i] is None:
                QMessageBox.warning(self, "Missing", f"Gantry position {POINT_LABELS[i]} not captured.")
                return
        for i, sp in enumerate(self.spin_dist):
            if sp.value() <= 0:
                QMessageBox.warning(self, "Missing", f"Distance #{i+1} must be > 0.")
                return

        img_size = self.image_label.get_image_size()
        if img_size is None:
            QMessageBox.warning(self, "Missing", "No snapshot.")
            return
        img_w, img_h = img_size

        px_pts = np.array(self.pixel_points, dtype=np.float64)
        ga_pts = np.array(self.gantry_points, dtype=np.float64)

        # px/mm scale: average of 3 pairs (pixel distance / user-entered mm)
        pairs = [(0, 1), (1, 2), (0, 2)]
        scales = []
        for k, (a, b) in enumerate(pairs):
            d_px = float(np.linalg.norm(px_pts[a] - px_pts[b]))
            d_mm = float(self.spin_dist[k].value())
            if d_mm > 0:
                scales.append(d_px / d_mm)
        px_per_mm = float(np.mean(scales)) if scales else 0.0

        # Affine pixel -> gantry mm. Solve A @ [px, py, 1].T = [gx, gy].T
        # Use 3 equations per axis: M * a = b
        M = np.hstack([px_pts, np.ones((3, 1))])  # 3x3
        try:
            ax = np.linalg.solve(M, ga_pts[:, 0])  # [a, b, c] for X
            ay = np.linalg.solve(M, ga_pts[:, 1])  # [d, e, f] for Y
        except np.linalg.LinAlgError:
            QMessageBox.warning(self, "Bad geometry", "The 3 pixel points are collinear; pick non-aligned points.")
            return

        affine = np.array([ax, ay], dtype=np.float64)  # 2x3

        # gantry coord at image center pixel = needle position when looking at image center
        center_px = np.array([img_w / 2.0, img_h / 2.0, 1.0])
        center_gantry = affine @ center_px  # (2,)

        # needle offset = vector from image center (in gantry mm) to gantry origin direction
        # i.e. when the needle is physically at the image-center pixel, gantry is at center_gantry.
        # If we want to know where the needle is relative to the image center (in mm),
        # we report the gantry coord at center, AND the per-point offset.
        # Per-point offset = gantry_point - gantry_at_pixel_of_that_point  -> always 0 (same thing).
        # The interesting value: gantry XY when the needle is at image center.
        # That IS the needle's position-in-gantry-coords for the camera's optical axis pixel.

        result = {
            "image_size": {"width": int(img_w), "height": int(img_h)},
            "px_per_mm": float(px_per_mm),
            "mm_per_px": float(1.0 / px_per_mm) if px_per_mm > 0 else 0.0,
            "affine_pixel_to_gantry_mm": {
                "row_x": [float(v) for v in ax.tolist()],
                "row_y": [float(v) for v in ay.tolist()],
            },
            "needle_gantry_at_image_center": {
                "X": float(center_gantry[0]),
                "Y": float(center_gantry[1]),
            },
            "points": [
                {
                    "label": POINT_LABELS[i],
                    "pixel": {"x": int(self.pixel_points[i][0]), "y": int(self.pixel_points[i][1])},
                    "gantry_mm": {"X": float(self.gantry_points[i][0]), "Y": float(self.gantry_points[i][1])},
                }
                for i in range(3)
            ],
            "distances_mm": {
                "P1_P2": float(self.spin_dist[0].value()),
                "P2_P3": float(self.spin_dist[1].value()),
                "P1_P3": float(self.spin_dist[2].value()),
            },
        }

        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
                yaml.safe_dump(result, f, sort_keys=False)
        except Exception as e:
            QMessageBox.critical(self, "Save error", f"Failed to write {CALIBRATION_FILE}:\n{e}")
            return

        msg = (
            f"px/mm     : {px_per_mm:.4f}\n"
            f"mm/px     : {result['mm_per_px']:.5f}\n"
            f"image     : {img_w} x {img_h}\n"
            f"needle gantry @ image center:\n"
            f"  X = {center_gantry[0]:.3f} mm\n"
            f"  Y = {center_gantry[1]:.3f} mm\n"
            f"saved to: {os.path.relpath(CALIBRATION_FILE)}"
        )
        self.lbl_result.setText(msg)
        self.log_widget.append_log("[CALIB] Calibration saved to calibration.yaml")
