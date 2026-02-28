# manual_pipeline_widget.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QStackedWidget, QLabel, QApplication
from .start_widget import StartWidget
from .manual_steps.manual_pipeline_widget import PipelineWidget as ManualPipelineWidget
from .auto_steps.auto_pipeline_widget import AutoPipelineWidget


class PipelineWidget(QWidget):
    def __init__(self, main_window, image_path=None, log_widget=None):
        super().__init__()
        self.setWindowTitle("Select Analysis Mode")
        self.setMinimumSize(1200, 780)
        self.image_path = image_path
        self.main_window = main_window
        self.log_widget = log_widget

        self._apply_default_window_geometry()

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

    def _apply_default_window_geometry(self):
        app = QApplication.instance()
        if app is None:
            return
        screen = app.primaryScreen()
        if screen is None:
            return

        avail = screen.availableGeometry()
        target_w = min(avail.width() - 30, max(int(avail.width() * 0.95), 1280))
        target_h = min(avail.height() - 30, max(int(avail.height() * 0.93), 820))
        target_w = max(1200, target_w)
        target_h = max(780, target_h)

        self.resize(target_w, target_h)
        x = avail.x() + (avail.width() - target_w) // 2
        y = avail.y() + (avail.height() - target_h) // 2
        self.move(max(avail.x(), x), max(avail.y(), y))

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
        if self.log_widget:
            self.log_widget.append_log("[DEBUG] Manual pipeline finished - closing top-level PipelineWidget.")

        # Optional: clean up the manual pipeline widget
        if self.manual_pipeline:
            self.stack.removeWidget(self.manual_pipeline)
            self.manual_pipeline.deleteLater()
            self.manual_pipeline = None

        self.close()

    def close_auto_pipeline(self):
        if self.log_widget:
            self.log_widget.append_log("[DEBUG] Auto pipeline finished - closing top-level PipelineWidget.")

        # Optional: clean up the manual pipeline widget
        if self.manual_pipeline:
            self.stack.removeWidget(self.manual_pipeline)
            self.auto_pipeline.deleteLater()
            self.auto_pipeline = None

        self.close()