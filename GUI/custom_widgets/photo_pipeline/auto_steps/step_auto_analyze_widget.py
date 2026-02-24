from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, Qt, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QSizePolicy
from PyQt5.QtGui import QImage, QPixmap
import cv2


# Worker that runs analyze_whole off the GUI thread
class _AutoWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    @pyqtSlot(object)
    def run(self, context):
        try:
            img = getattr(context, "image", None)
            mask = getattr(context, "mask", None)
            if img is None:
                raise RuntimeError("No image in context")
            if not hasattr(context, "analyze_whole"):
                raise RuntimeError("context.analyze_whole is missing")

            res = context.analyze_whole(img, mask)  # heavy call
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class StepAutoAnalyzeWidget(QWidget):
    # to mirror your manual first step
    go_to_start = pyqtSignal()

    def __init__(self, context, image_path=None, log_widget=None, parent=None):
        super().__init__(parent)
        self.context = context
        self.log_widget = log_widget
        self.image_path = image_path
        self._analysis_done = False
        self._overlay_pixmap = None  # cache original for clean resizing

        root = QVBoxLayout(self)

        self.status_lbl = QLabel("Analyzing whole dish…")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status_lbl)

        # image preview
        self.image_lbl = QLabel()
        self.image_lbl.setAlignment(Qt.AlignCenter)
        self.image_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.image_lbl)

        # ---- NAV BUTTONS (same contract as manual steps) ----
        self.prev_btn = QPushButton("◀ Previous")
        self.next_btn = QPushButton("Next ▶")
        # first step → back to start screen
        self.prev_btn.clicked.connect(self.go_to_start.emit)

        nav = QHBoxLayout()
        nav.addWidget(self.prev_btn)
        nav.addStretch()
        nav.addWidget(self.next_btn)
        root.addLayout(nav)

        # thread setup
        self._thread = None
        self._worker = None
        self._start()

    # -------- manual-pipeline API --------
    def load_from_context(self):
        pass

    def save_to_context(self):
        pass

    def try_advance(self) -> bool:
        """Pipeline only advances when analysis is complete."""
        return self._analysis_done

    # -------- threading --------
    def _start(self):
        self._thread = QThread(self)
        self._worker = _AutoWorker()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(lambda: self._worker.run(self.context))
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    @staticmethod
    def cvimg_to_qpixmap(cv_img):
        """Convert OpenCV BGR image to QPixmap."""
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        # .copy() detaches from numpy buffer, safer if array goes out of scope
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        return QPixmap.fromImage(qimg)

    # -------- results --------
    def _on_done(self, res):
        try:
            # 1. Append detected points exactly like your analyze_whole ---
            auto_pts = res.get("centers", [])
            if hasattr(self, "_append_points_to_selection"):
                self._append_points_to_selection(auto_pts)
            else:
                # fallback if your helper isn't present
                self.context.roi_points = list(getattr(self.context, "roi_points", [])) + [
                    (int(x), int(y)) for (x, y) in auto_pts
                ]

            # 2. Collect detected contours from stats ---
            stats = res.get("stats", [])
            self.detected_contours = [s["contour"] for s in stats if "contour" in s]

            # 3. Stash overlay into context.analysis like your flow expects ---
            overlay = res.get("overlay", None)
            self.context.analysis = getattr(self.context, "analysis", {}) or {}
            if overlay is not None:
                self.context.analysis["whole_overlay"] = overlay

            # 4. Notify hook if present ---
            if hasattr(self.context, "on_analysis_done"):
                self.context.on_analysis_done(res)

            # 5. Choose what to show (overlay if available, else original image) ---
            overlay_from_ctx = getattr(self.context, "analysis", {}).get("whole_overlay", None)
            if overlay_from_ctx is not None:
                img_show = overlay_from_ctx.copy()
            else:
                img_show = self.context.image.copy()

            # 6. Apply mask outline exactly like your code ---
            if hasattr(self, "_apply_mask_outline"):
                self._apply_mask_outline(img_show)

            # 7. Set display_image + save + refresh UI (your way if available) ---
            self.display_image = img_show

            if hasattr(self, "save_to_context"):
                self.save_to_context()

            # Prefer your widget’s own updater if it exists
            if hasattr(self, "update_image_label"):
                self.update_image_label()
            else:
                # Fallback: render into the preview label we added
                if img_show is not None:
                    pixmap = self.cvimg_to_qpixmap(img_show)
                    self.image_lbl.setPixmap(pixmap.scaled(
                        self.image_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                    ))

            if self.log_widget:
                self.log_widget.append_log(f"[AUTO] analyze_whole: {len(auto_pts)} points")
        except Exception as e:
            if self.log_widget:
                self.log_widget.append_log(f"[AUTO][WARN] postprocess failed: {e}")

        # --- 8) Wrap up ---
        self._analysis_done = True
        self.status_lbl.setText("Analysis done.")
        QTimer.singleShot(700, self.next_btn.click)

    def _on_error(self, msg):
        if self.log_widget:
            self.log_widget.append_log(f"[AUTO][ERROR] {msg}")
        self.status_lbl.setText("Analysis failed — you can proceed.")
        self._analysis_done = True
        QTimer.singleShot(500, self.next_btn.click)

    # -------- helpers --------
    def _set_scaled_overlay_pixmap(self):
        if self._overlay_pixmap is None:
            return
        target = self._overlay_pixmap.scaled(
            self.image_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_lbl.setPixmap(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_scaled_overlay_pixmap()
