from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QSplitter, QGroupBox, QFrame, QSizePolicy
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer
import cv2
from Image_processing.overlay_draw import draw_mask_outline, draw_points_simple

class StepSummaryWidget(QWidget):
    def __init__(self, context, image_path=None, log_widget=None):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.context = context
        self.image_path = image_path
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
        
        # Right: Log (ROI points text)
        roi_group = QGroupBox("ROI Points")
        roi_group_layout = QVBoxLayout()
        self.roi_text = QTextEdit()
        self.roi_text.setReadOnly(True)
        roi_group_layout.addWidget(self.roi_text)
        roi_group.setLayout(roi_group_layout)
        roi_group.setMinimumWidth(300)
        splitter.addWidget(roi_group)
        
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter, 1)

        # --- Bottom: Buttons in one row ---
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        self.prev_btn = QPushButton("Previous")
        self.next_btn = QPushButton("Next")
        
        button_layout.addWidget(self.prev_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.next_btn)
        
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

        self.display_image_with_rois()
        self.display_roi_points()
        QTimer.singleShot(0, self._refresh_view)

    def _refresh_view(self):
        self.display_image_with_rois()
        self.display_roi_points()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_view()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.display_image_with_rois()

    def display_image_with_rois(self):
        # Prefer the annotated display image from ROI widget if available
        display_img_attr = getattr(self.context, "display_image", None)
        display_base = display_img_attr if display_img_attr is not None else self.context.image
        if display_base is None:
            self.image_label.setText("No image loaded.")
            return

        roi_points = list(self.context.roi_points) if self.context.roi_points is not None else []
        display_img = display_base.copy()

        # --- draw Petri dish outline only if not from ROI widget ---
        if getattr(self.context, "display_image", None) is None:
            mask = getattr(self.context, "mask", None)
            draw_mask_outline(display_img, mask, color=(255, 0, 0), thickness=3)

        # draw ROI points (if not already drawn by ROI widget)
        if getattr(self.context, "display_image", None) is None:
            draw_points_simple(display_img, roi_points, color=(0, 0, 255), radius=5, thickness=2)

        rgb_image = cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        # Scale to fit the larger image area in split panel
        content_rect = self.image_label.contentsRect()
        target_w = max(1, content_rect.width())
        target_h = max(1, content_rect.height())
        pixmap = QPixmap.fromImage(qt_img).scaled(target_w, target_h, 
                                                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pixmap)

    def display_roi_points(self):
        roi_points = list(self.context.roi_points) if self.context.roi_points is not None else []
        if not roi_points:
            self.roi_text.setText("No ROI points.")
            return

        text_lines = ["ROI points (x, y):"]
        for idx, (x, y) in enumerate(roi_points, start=1):
            text_lines.append(f"  {idx}. ({x}, {y})")

        self.roi_text.setText("\n".join(text_lines))





