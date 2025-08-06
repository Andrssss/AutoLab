# pipeline_widget.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget
from PyQt5.QtCore import pyqtSignal
from GUI.custom_widgets.photo_pipeline.manual_steps.step_capture_widget import StepCaptureWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.step_roi_widget import StepROIWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.step_picking_widget import StepPickingWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.step_summary_widget import StepSummaryWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.pipeline_context import PipelineContext


class PipelineWidget(QWidget):
    pipeline_finished = pyqtSignal()

    def __init__(self, image_path=None):
        super().__init__()
        self.image_path = image_path

        self.context = PipelineContext()
        self.stack = QStackedWidget()
        layout = QVBoxLayout()
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
        # Clear previous step from stack
        if self.current_step is not None:
            self.stack.removeWidget(self.current_step)
            self.current_step.deleteLater()
            self.current_step = None

        # Instantiate new step widget
        step_class = self.step_classes[index]
        self.current_step = step_class(context=self.context, image_path=self.image_path)
        self.current_step_index = index

        self.stack.addWidget(self.current_step)
        self.stack.setCurrentWidget(self.current_step)

        # Connect buttons if available
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
        print("[DEBUG] go_back_to_start() triggered")
        if self.return_to_start_callback:
            self.return_to_start_callback()
        else:
            print("[ERROR] return_to_start_callback is not set")


    def handle_finished(self):
        print("[DEBUG] Pipeline finished — váltás a következő lépésre.")
        self.pipeline_finished.emit()

    def _handle_next_clicked(self):
        # Ha az aktuális step tartalmaz try_advance metódust, akkor azt hívjuk meg
        if hasattr(self.current_step, "try_advance"):
            proceed = self.current_step.try_advance()
            if not proceed:
                return  # Ne lépj tovább
        self.go_next()

