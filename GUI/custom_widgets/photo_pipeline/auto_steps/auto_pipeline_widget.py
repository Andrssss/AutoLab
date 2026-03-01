from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtGui import QCloseEvent
import cv2

from GUI.custom_widgets.photo_pipeline.pipeline_context import PipelineContext
from ..manual_steps.step_picking_widget import StepPickingWidget
from .step_auto_analyze_widget import StepAutoAnalyzeWidget


class AutoPipelineWidget(QWidget):
    pipeline_finished = pyqtSignal()

    def __init__(self, main_window, image_path=None, log_widget=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.image_path = image_path
        self.log_widget = log_widget

        self.context = PipelineContext()
        if self.image_path and getattr(self.context, "image", None) is None:
            try:
                img = cv2.imread(self.image_path)
                if img is not None:
                    self.context.image = img
            except Exception as e:
                if self.log_widget:
                    self.log_widget.append_log(f"[AUTO] Failed to load image: {e}")

        self.stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)

        self.return_to_start_callback = None  # set by parent if needed

        # steps (same idea as manual)
        self.step_classes = [
            StepAutoAnalyzeWidget,
            StepPickingWidget
        ]
        self.current_step_index = 0
        self.current_step = None

        self.load_step(0)

    # ------- same wiring as your manual PipelineWidget --------
    def load_step(self, index):
        if self.current_step is not None:
            self._shutdown_current_step()
            self.stack.removeWidget(self.current_step)
            self.current_step.deleteLater()
            self.current_step = None

        step_class = self.step_classes[index]

        if step_class == StepPickingWidget:
            self.current_step = step_class(
                context=self.context,
                image_path=self.image_path,
                log_widget=self.log_widget,
                main_window=self.main_window
            )
        else:
            self.current_step = step_class(
                context=self.context,
                image_path=self.image_path,
                log_widget=self.log_widget
            )

        self.current_step_index = index
        self.stack.addWidget(self.current_step)
        self.stack.setCurrentWidget(self.current_step)

        if hasattr(self.current_step, "load_from_context"):
            self.current_step.load_from_context()
        if hasattr(self.current_step, "next_btn"):
            self.current_step.next_btn.clicked.connect(self._handle_next_clicked)
        if hasattr(self.current_step, "prev_btn"):
            self.current_step.prev_btn.clicked.connect(self.go_prev)
        if hasattr(self.current_step, "go_to_start"):
            self.current_step.go_to_start.connect(self.go_back_to_start)
        if hasattr(self.current_step, "finished"):
            self.current_step.finished.connect(self.handle_finished)

        # auto-start picking after 3s when we land on picking
        if step_class == StepPickingWidget:
            QTimer.singleShot(500, self._start_picking_if_available)

    def _start_picking_if_available(self):
        if hasattr(self.current_step, "start_picking"):
            self.current_step.start_picking()

    def _handle_next_clicked(self):
        if hasattr(self.current_step, "try_advance"):
            proceed = self.current_step.try_advance()
            if not proceed:
                return
        self.go_next()

    def go_next(self):
        if hasattr(self.current_step, "save_to_context"):
            self.current_step.save_to_context()
        if self.current_step_index < len(self.step_classes) - 1:
            self.load_step(self.current_step_index + 1)

    def go_prev(self):
        if hasattr(self.current_step, "save_to_context"):
            self.current_step.save_to_context()
        if self.current_step_index > 0:
            self.load_step(self.current_step_index - 1)

    def go_back_to_start(self):
        if self.log_widget:
            self.log_widget.append_log("[DEBUG] go_back_to_start() triggered")
        if self.return_to_start_callback:
            self.return_to_start_callback()
        else:
            if self.log_widget:
                self.log_widget.append_log("[ERROR] return_to_start_callback is not set")

    def handle_finished(self):
        self.pipeline_finished.emit()

    def _shutdown_current_step(self):
        if self.current_step is not None and hasattr(self.current_step, "prepare_to_close"):
            try:
                self.current_step.prepare_to_close()
            except Exception:
                pass

    def closeEvent(self, event: QCloseEvent):
        self._shutdown_current_step()
        super().closeEvent(event)