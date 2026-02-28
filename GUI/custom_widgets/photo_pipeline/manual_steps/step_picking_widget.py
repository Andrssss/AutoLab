from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit, QHBoxLayout, QApplication, QSplitter, QGroupBox, QFrame, QSizePolicy
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
import cv2

class StepPickingWidget(QWidget):
    finished = pyqtSignal()

    def __init__(self, context, image_path=None, log_widget=None, main_window=None):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.context = context
        self.main_window = main_window
        self.log_widget = log_widget

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

        # external deps
        try:
            self.command_sender = main_window.get_command_sender()
        except Exception:
            self.command_sender = None
            self.log_box.append("[ERROR] command_sender is not available.")
        try:
            self.g_control = main_window.get_g_control()
        except Exception:
            self.g_control = None
            self.log_box.append("[ERROR] g_control is not available.")

        # state machine
        self._engine = QTimer(self)      # ticks every 100 ms
        self._engine.setInterval(100)
        self._engine.timeout.connect(self._tick)

        self._active = False
        self._paused = False
        self._idx = -1                   # current ROI index
        self._wait = 0                   # ticks remaining during dwell
        self._points = []                # cached roi_points

        # wire
        self.start_btn.clicked.connect(self.start_picking)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.stop_btn.clicked.connect(self.stop_picking)
        self.finish_btn.clicked.connect(self._on_finish_clicked)

        # show image
        self._show_base()

    def _refresh_view(self):
        if self._points and self._idx >= 0:
            self._draw_progress(current=self._idx)
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
        self._stop_engine()

    def _stop_engine(self):
        self._active = False
        self._paused = False
        if self._engine.isActive():
            self._engine.stop()

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
        """Draw visited points (black) and current (red)."""
        # Use display_image if available (annotated from ROI widget), otherwise fallback to context.image
        display_img_attr = getattr(self.context, "display_image", None)
        base = display_img_attr if display_img_attr is not None else self.context.image
        if base is None:
            return
        im = base.copy()
        for i, (x, y) in enumerate(self._points):
            if self._idx >= i:
                cv2.drawMarker(im, (x, y), (0, 0, 0), markerType=cv2.MARKER_TILTED_CROSS, markerSize=8, thickness=2)
        if current is not None and 0 <= current < len(self._points):
            x, y = self._points[current]
            cv2.drawMarker(im, (x, y), (0, 0, 255), markerType=cv2.MARKER_TILTED_CROSS, markerSize=8, thickness=2)
        self._show(im)

    # ---------- commands ----------
    def start_picking(self):
        self._points = list(self.context.roi_points) if self.context.roi_points is not None else []
        if not self._points:
            self.log_box.append("[ERROR] No ROI points.")
            return
        if not self.command_sender or not self.g_control:
            self.log_box.append("[ERROR] Controller is not configured.")
            return

        if not self.g_control.connected:
            self.log_box.append("[INFO] Automatic reconnection...")
            try:
                self.g_control.autoconnect()
            except Exception as e:
                self.log_box.append(f"[ERROR] Autoconnect error: {e}")
                return

        # init FSM
        self._active = True
        self._paused = False
        self._idx = -1
        self._wait = 0
        self._engine.start()  # start ticking

    def toggle_pause(self):
        if not self._active:
            return
        self._paused = not self._paused
        self.log_box.append("Pause" if self._paused else "Resume")

    def stop_picking(self):
        if not self._active:
            return
        self._stop_engine()
        self.log_box.append("[INFO] Pipetting stopped.")

    def _on_finish_clicked(self):
        # Gracefully stop the engine and emit finished on the next event loop turn
        self._stop_engine()
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

        # waiting phase?
        if self._wait > 0:
            self._wait -= 1
            return

        # move to next point
        self._idx += 1
        if self._idx >= len(self._points):
            # done
            self._stop_engine()
            self.log_box.append("[DONE] All ROI positions visited.")
            return

        x, y = self._points[self._idx]
        self.log_box.append(f"[STEP] {self._idx + 1}. ROI -> X:{x}, Y:{y}")
        try:
            self.command_sender.sendCommand.emit(f"G0 X{x} Y{y} F3000\n")
        except Exception as e:
            self.log_box.append(f"[ERROR] Command send error: {e}")
            self._stop_engine()
            return

        # show progress with current highlighted
        self._draw_progress(current=self._idx)

        # dwell ~3s => 30 ticks (100 ms each)
        self._wait = 30

    # ---------- Qt cleanup ----------
    def closeEvent(self, event):
        self._stop_engine()
        event.accept()

