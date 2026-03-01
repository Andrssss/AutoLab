from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit, QHBoxLayout, QApplication, QSplitter, QGroupBox, QFrame, QSizePolicy
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
import cv2
from Pozitioner_and_Communicater.control_actions import ControlActions

class StepPickingWidget(QWidget):
    finished = pyqtSignal()
    ROI_MOVE_FEEDRATE = 6000

    def __init__(self, context, image_path=None, log_widget=None, main_window=None):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.context = context
        self.main_window = main_window
        self.log_widget = log_widget
        self.control_actions: ControlActions | None = None
        try:
            self.control_actions = main_window.get_control_actions()
        except Exception:
            self.control_actions = None

        # Main layout: vertical with split panel in middle and buttons at bottom
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Center: Split panel (image left, log right) ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Left: Image
        self.image_label = QLabel("No Image")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(480, 360)
        self.image_label.setFrameShape(QFrame.StyledPanel)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        splitter.addWidget(self.image_label)
        
        # Right: Log
        log_group = QGroupBox("Picking Log")
        log_layout = QVBoxLayout()
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        log_layout.addWidget(self.log_box)

        right_controls_layout = QHBoxLayout()
        right_controls_layout.setSpacing(8)

        self.start_btn = QPushButton("Start picking")
        self.pause_btn = QPushButton("Pause / Continue")
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setStyleSheet("color: red; font-weight: bold;")

        right_controls_layout.addWidget(self.start_btn)
        right_controls_layout.addWidget(self.pause_btn)
        right_controls_layout.addWidget(self.stop_btn)
        log_layout.addLayout(right_controls_layout)

        log_group.setLayout(log_layout)
        log_group.setMinimumWidth(300)
        splitter.addWidget(log_group)
        
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter, 1)

        # --- Bottom: Buttons in one row ---
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        self.prev_btn = QPushButton("Previous")
        self.finish_btn = QPushButton("Finish")
        
        button_layout.addWidget(self.prev_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.finish_btn)
        
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

        # state machine
        self._engine = QTimer(self)      # ticks every 100 ms
        self._engine.setInterval(100)
        self._engine.timeout.connect(self._tick)

        self._active = False
        self._paused = False
        self._idx = -1                   # current ROI index
        self._wait = 0                   # ticks remaining during dwell
        self._awaiting_motion = False    # True while waiting for queued move to fully complete
        self._points = []                # cached roi_points
        self._reconnect_required = False
        self._resume_after_stop_available = False

        # wire
        self.start_btn.clicked.connect(self.start_picking)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.stop_btn.clicked.connect(self.stop_picking)
        self.finish_btn.clicked.connect(self._on_finish_clicked)

        # show image
        self._show_base()

    def _refresh_view(self):
        if self._points:
            current = self._idx if self._idx >= 0 else None
            self._draw_progress(current=current)
        else:
            self._show_base()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_view()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_view()

    # ---------- lifecycle helpers ----------
    def prepare_to_close(self):
        """Called by the pipeline before removing the widget."""
        self._abort_pending_picking_motion("[INFO] Picking closed; pending motion commands cleared.")

    def _stop_engine(self):
        self._active = False
        self._paused = False
        self._awaiting_motion = False
        if self._engine.isActive():
            self._engine.stop()

    def _abort_pending_picking_motion(self, log_message: str = ""):
        self._stop_engine()
        removed = 0
        try:
            if self.control_actions:
                removed = int(self.control_actions.clear_pending_motion_commands())
        except Exception:
            removed = 0

        self._reconnect_required = False
        self._resume_after_stop_available = False

        if log_message:
            suffix = f" (removed: {removed})" if removed > 0 else ""
            self.log_box.append(f"{log_message}{suffix}")

    def _is_emergency_recovery_needed(self) -> bool:
        if self._reconnect_required:
            return True
        if not self.control_actions:
            return False
        g_control = getattr(self.control_actions, "g_control", None)
        if g_control is None:
            return False

        try:
            if hasattr(g_control, "is_emergency_latched") and g_control.is_emergency_latched():
                return True
        except Exception:
            return True

        connected = bool(getattr(g_control, "connected", False))
        return not connected

    # ---------- UI render ----------
    def _show(self, img):
        if img is None:
            return
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, 3*w, QImage.Format_RGB888)
        content_rect = self.image_label.contentsRect()
        target_w = max(1, content_rect.width())
        target_h = max(1, content_rect.height())
        pix = QPixmap.fromImage(qimg).scaled(target_w, target_h,
                                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pix)

    def _show_base(self):
        # Prefer the annotated display image from ROI widget if available
        display_img = getattr(self.context, "display_image", None)
        if display_img is not None:
            self._show(display_img)
        elif self.context.image is not None:
            self._show(self.context.image)
        else:
            self.image_label.setText("No Image")

    def _draw_progress(self, current=None):
        display_img_attr = getattr(self.context, "display_image", None)
        base = display_img_attr if display_img_attr is not None else self.context.image
        if base is None:
            return
        im = base.copy()

        total = len(self._points)
        if total == 0:
            self._show(im)
            return

        current_idx = current if current is not None and 0 <= current < total else None

        points_np = [(int(x), int(y)) for (x, y) in self._points]

        for i in range(1, len(points_np)):
            p0 = points_np[i - 1]
            p1 = points_np[i]
            if current_idx is not None and i <= current_idx:
                cv2.line(im, p0, p1, (40, 170, 40), 2, cv2.LINE_AA)
            else:
                cv2.line(im, p0, p1, (120, 120, 120), 1, cv2.LINE_AA)

        for i, (x, y) in enumerate(points_np):
            if current_idx is not None and i < current_idx:
                cv2.circle(im, (x, y), 7, (40, 170, 40), -1, cv2.LINE_AA)
                cv2.circle(im, (x, y), 10, (0, 70, 0), 2, cv2.LINE_AA)
            elif current_idx is not None and i == current_idx:
                cv2.circle(im, (x, y), 10, (0, 0, 255), -1, cv2.LINE_AA)
                cv2.circle(im, (x, y), 15, (255, 255, 255), 2, cv2.LINE_AA)
            else:
                cv2.circle(im, (x, y), 6, (0, 180, 255), -1, cv2.LINE_AA)
                cv2.circle(im, (x, y), 9, (0, 90, 130), 1, cv2.LINE_AA)

        self._show(im)

    # ---------- commands ----------
    def start_picking(self):
        self._points = list(self.context.roi_points) if self.context.roi_points is not None else []
        if not self._points:
            self.log_box.append("[ERROR] No ROI points.")
            return
        if not self.control_actions:
            self.log_box.append("[ERROR] Control actions service is not available.")
            return

        if self._is_emergency_recovery_needed() and self._reconnect_required:
            self.log_box.append("[INFO] Reconnecting to saved port before restart...")
            if not self.control_actions.action_reconnect_saved_connection():
                self.log_box.append("[ERROR] Reconnect failed (saved settings).")
                return
            self._reconnect_required = False

        if self._is_emergency_recovery_needed():
            if not self.control_actions.action_recover_from_emergency():
                self.log_box.append("[ERROR] Emergency recovery failed (M999/reconnect).")
                return
            self.log_box.append("[INFO] Emergency recovery OK. Starting picking...")

        # init FSM
        self._active = True
        self._paused = False
        self._idx = -1
        self._wait = 0
        self._awaiting_motion = False
        self._resume_after_stop_available = False
        self._draw_progress(current=None)
        self._engine.start()  # start ticking

    def _resume_after_emergency_stop(self):
        if not self._resume_after_stop_available or not self._points:
            self.log_box.append("[WARN] No paused picking state to continue.")
            return
        if not self.control_actions:
            self.log_box.append("[ERROR] Control actions service is not available.")
            return

        if self._is_emergency_recovery_needed() and self._reconnect_required:
            self.log_box.append("[INFO] Reconnecting to saved port before continue...")
            if not self.control_actions.action_reconnect_saved_connection():
                self.log_box.append("[ERROR] Reconnect failed (saved settings).")
                return
            self._reconnect_required = False

        if self._is_emergency_recovery_needed():
            if not self.control_actions.action_recover_from_emergency():
                self.log_box.append("[ERROR] Emergency recovery failed (M999/reconnect).")
                return

        self._active = True
        self._paused = False
        self._wait = 0
        self._awaiting_motion = False
        self._engine.start()
        self.log_box.append("[INFO] Continued from last ROI position.")

    def toggle_pause(self):
        if not self._active:
            if self._reconnect_required or self._resume_after_stop_available:
                self._resume_after_emergency_stop()
            return
        self._paused = not self._paused
        self.log_box.append("Pause" if self._paused else "Resume")

    def stop_picking(self):
        self._resume_after_stop_available = bool(self._active or self._idx >= 0)
        self._trigger_emergency_stop_like_manual_control()
        self._stop_engine()
        self._reconnect_required = True
        self.log_box.append("[INFO] Pipetting stopped (emergency stop sent).")

    def _trigger_emergency_stop_like_manual_control(self):
        """Use centralized emergency-stop action (manual control flow + fallback)."""
        try:
            control_widget = getattr(self.main_window, "control_widget", None) if self.main_window else None
            source = self.control_actions.action_emergency_stop(stop_context=control_widget, send_reset=False) if self.control_actions else "fallback"
            if source == "fallback":
                self.log_box.append("[EMERGENCY STOP] M112 sent (fallback).")
        except Exception as e:
            self.log_box.append(f"[ERROR] Emergency stop failed: {e}")

    def _on_finish_clicked(self):
        # Gracefully stop the engine and emit finished on the next event loop turn
        self._abort_pending_picking_motion("[INFO] Picking finished by user; pending motion commands cleared.")
        QTimer.singleShot(0, self.finished.emit)

    # ---------- FSM tick ----------
    def _tick(self):
        # stopped?
        if not self._active:
            self._engine.stop()
            return
        # paused?
        if self._paused:
            return

        # wait until last move is really completed (queue drained + worker idle)
        if self._awaiting_motion:
            if self.control_actions and self.control_actions.has_pending_motion_commands():
                return
            self._awaiting_motion = False

        # waiting phase?
        if self._wait > 0:
            self._wait -= 1
            return

        # move to next point
        self._idx += 1
        if self._idx >= len(self._points):
            if self.control_actions and self.control_actions.has_pending_motion_commands():
                self._idx = len(self._points) - 1
                return

            self._stop_engine()
            self.log_box.append("[DONE] All ROI positions visited.")
            return

        x, y = self._points[self._idx]
        self.log_box.append(f"[STEP] {self._idx + 1}. ROI -> X:{x}, Y:{y}")
        try:
            if not self.control_actions:
                raise RuntimeError("Control actions service is not available.")
            self.control_actions.action_move_xy(x, y, feedrate=self.ROI_MOVE_FEEDRATE)
        except Exception as e:
            self.log_box.append(f"[ERROR] Command send error: {e}")
            self._stop_engine()
            return

        # show progress with current highlighted
        self._draw_progress(current=self._idx)

        # wait for actual motion completion before moving to next ROI
        self._awaiting_motion = True
        self._wait = 0

    # ---------- Qt cleanup ----------
    def closeEvent(self, event):
        self._on_finish_clicked()
        event.accept()

