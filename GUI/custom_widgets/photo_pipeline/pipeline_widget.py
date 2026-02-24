# manual_pipeline_widget.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget, QLabel
from .start_widget import StartWidget
from .manual_steps.manual_pipeline_widget import PipelineWidget as ManualPipelineWidget
from .auto_steps.auto_pipeline_widget import AutoPipelineWidget


class PipelineWidget(QWidget):
    def __init__(self, main_window, image_path=None, log_widget=None):
        super().__init__()
        self.setWindowTitle("Elemzési Mód Választása")
        self.image_path = image_path
        self.main_window = main_window
        self.log_widget = log_widget

        # Stack and layout setup
        self.stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)

        # 1. Blank screen as fallback
        self.blank_screen = QLabel("")
        self.stack.addWidget(self.blank_screen)

        # 2. Start screen with buttons
        self.start_screen = StartWidget()
        self.start_screen.manual_btn.clicked.connect(self.start_manual_pipeline)
        self.start_screen.auto_btn.clicked.connect(self.start_auto_pipeline)
        self.stack.addWidget(self.start_screen)

        # 3. Show the start screen by default
        self.stack.setCurrentWidget(self.start_screen)

        # Placeholders for dynamic widgets
        self.manual_pipeline = None
        self.auto_pipeline = None
        self.auto_step = None

    def start_manual_pipeline(self):
        self.manual_pipeline = ManualPipelineWidget(self.main_window,image_path=self.image_path,log_widget=self.log_widget)
        self.manual_pipeline.return_to_start_callback = self.return_to_start
        self.manual_pipeline.pipeline_finished.connect(self.close_manual_pipeline)  #  finish signal
        self.stack.addWidget(self.manual_pipeline)
        self.stack.setCurrentWidget(self.manual_pipeline)

    def start_auto_pipeline(self):
        self.auto_pipeline = AutoPipelineWidget(
            main_window=self.main_window,
            image_path=self.image_path,
            log_widget=getattr(self.main_window, "log", None)  # or pass your log widget
        )
        self.auto_pipeline.pipeline_finished.connect(self.close_auto_pipeline)
        self.stack.addWidget(self.auto_pipeline)
        self.stack.setCurrentWidget(self.auto_pipeline)

    def return_to_start(self):
        self.stack.setCurrentWidget(self.start_screen)

    def close_manual_pipeline(self):
        print("[DEBUG] Manual pipeline finished — closing top-level PipelineWidget.")

        # Optional: clean up the manual pipeline widget
        if self.manual_pipeline:
            self.stack.removeWidget(self.manual_pipeline)
            self.manual_pipeline.deleteLater()
            self.manual_pipeline = None

        self.close()

    def close_auto_pipeline(self):
        print("[DEBUG] Auto pipeline finished — closing top-level PipelineWidget.")

        # Optional: clean up the manual pipeline widget
        if self.manual_pipeline:
            self.stack.removeWidget(self.manual_pipeline)
            self.auto_pipeline.deleteLater()
            self.auto_pipeline = None

        self.close()