from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget, QSizePolicy
from PyQt5.QtCore import pyqtSignal, QTimer
from GUI.custom_widgets.photo_pipeline.manual_steps.step_capture_widget import StepCaptureWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.step_roi_widget import StepROIWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.step_picking_widget import StepPickingWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.step_summary_widget import StepSummaryWidget
from GUI.custom_widgets.photo_pipeline.pipeline_context import PipelineContext


class PipelineWidget(QWidget):
    pipeline_finished = pyqtSignal()

    def __init__(self,main_window, image_path,log_widget):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_path = image_path
        self.main_window = main_window
        self.log_widget = log_widget

        self.context = PipelineContext()
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack)
        self.setLayout(layout)

        self.return_to_start_callback = None  # Set externally by parent

        # Step classes instead of instances
        self.step_classes = [
            StepCaptureWidget,
            StepROIWidget,
            StepSummaryWidget,
            StepPickingWidget
        ]

        self.current_step_index = 0
        self.current_step = None

        self.load_step(0)  # Load first step

    def load_step(self, index):
        # safely remove previous
        if self.current_step is not None:
            # give the step a chance to stop timers/threads
            if hasattr(self.current_step, "prepare_to_close"):
                try:
                    self.current_step.prepare_to_close()
                except Exception:
                    pass
            self.stack.removeWidget(self.current_step)
            self.current_step.deleteLater()
            self.current_step = None

        # construct new step (unchanged)
        step_class = self.step_classes[index]
        if step_class == StepPickingWidget:
            self.current_step = step_class(context=self.context, image_path=self.image_path,
                                           log_widget=self.log_widget, main_window=self.main_window)
        else:
            self.current_step = step_class(context=self.context, image_path=self.image_path,
                                           log_widget=self.log_widget)

        self.current_step_index = index
        self.stack.addWidget(self.current_step)
        self.stack.setCurrentWidget(self.current_step)

        if hasattr(self.current_step, "load_from_context"):
            self.current_step.load_from_context()
        # Keep normal window sizing during step switches (no forced maximize here)
        if hasattr(self.current_step, "next_btn"):
            self.current_step.next_btn.clicked.connect(self._handle_next_clicked)
        if hasattr(self.current_step, "prev_btn"):
            self.current_step.prev_btn.clicked.connect(self.go_prev)
        if hasattr(self.current_step, "go_to_start"):
            self.current_step.go_to_start.connect(self.go_back_to_start)
        if hasattr(self.current_step, "finished"):
            self.current_step.finished.connect(self.handle_finished)


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
        if self.log_widget:
            self.log_widget.append_log("[DEBUG] Pipeline finished - switching to the next step.")
        QTimer.singleShot(0, self.pipeline_finished.emit)

    def _handle_next_clicked(self):
        # If the current step has a try_advance method, call it.
        if hasattr(self.current_step, "try_advance"):
            proceed = self.current_step.try_advance()
            if not proceed:
                return  # Do not continue
        self.go_next()
