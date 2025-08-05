# pipeline_widget.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget
from PyQt5.QtCore import pyqtSignal
from GUI.custom_widgets.photo_pipeline.manual_steps.step_capture_widget import StepCaptureWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.step_roi_widget import StepROIWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.step_analysis_widget import StepAnalysisWidget
from GUI.custom_widgets.photo_pipeline.manual_steps.step_summary_widget import StepSummaryWidget


class PipelineWidget(QWidget):
    pipeline_finished = pyqtSignal()

    def __init__(self, image_path=None):
        super().__init__()
        self.image_path = image_path

        self.stack = QStackedWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.stack)
        self.setLayout(layout)

        self.return_to_start_callback = None  # Set externally by parent

        # Step classes instead of instances
        self.step_classes = [
            StepCaptureWidget,
            StepROIWidget,
            StepAnalysisWidget,
            StepSummaryWidget
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
        self.current_step = step_class(image_path=self.image_path)
        self.current_step_index = index

        self.stack.addWidget(self.current_step)
        self.stack.setCurrentWidget(self.current_step)

        # Connect buttons if available
        if hasattr(self.current_step, "next_btn"):
            self.current_step.next_btn.clicked.connect(self.go_next)
        if hasattr(self.current_step, "prev_btn"):
            self.current_step.prev_btn.clicked.connect(self.go_prev)
        if hasattr(self.current_step, "go_to_start"):
            self.current_step.go_to_start.connect(self.go_back_to_start)
        # 🔥 NEW: Connect finished signal from summary step
        if hasattr(self.current_step, "finished"):
            self.current_step.finished.connect(self.handle_finished)

    def go_next(self):
        if self.current_step_index < len(self.step_classes) - 1:
            self.load_step(self.current_step_index + 1)

    def go_prev(self):
        if self.current_step_index > 0:
            self.load_step(self.current_step_index - 1)

    def go_back_to_start(self):
        print("[DEBUG] go_back_to_start() triggered")
        if self.return_to_start_callback:
            self.return_to_start_callback()
        else:
            print("[ERROR] return_to_start_callback is not set")

    from PyQt5.QtWidgets import QMessageBox, QStackedWidget

    def handle_finished(self):
        from PyQt5.QtWidgets import QMessageBox

        print("[DEBUG] Pipeline finished — showing message.")
        self.pipeline_finished.emit()  # Let the parent handle cleanup
