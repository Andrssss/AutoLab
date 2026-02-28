from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QHBoxLayout, QLabel, QComboBox, QLineEdit

class LogWidget(QWidget):
    appendRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []  # list[(category, message)]
        self._current_filter = "All"
        self._search_text = ""

        self.appendRequested.connect(self._append_log_internal)

        layout = QVBoxLayout()

        # Button row (e.g. for clearing)
        button_layout = QHBoxLayout()
        button_layout.addWidget(QLabel("Category:"))

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Program", "Arduino Comms", "Errors", "Other"])
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        button_layout.addWidget(self.filter_combo)

        button_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter logs...")
        self.search_input.textChanged.connect(self._on_search_changed)
        button_layout.addWidget(self.search_input)

        button_layout.addStretch()

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear_log)
        button_layout.addWidget(btn_clear)

        # Log view
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        layout.addLayout(button_layout)  # Button row
        layout.addWidget(self.log_view)  # Text box
        self.setLayout(layout)
        self.setMinimumWidth(600)

    def append_log(self, message):
        self.appendRequested.emit(str(message))

    def _append_log_internal(self, message: str):
        message = self._normalize_message_label(message)
        category = self._categorize_message(message)
        self._entries.append((category, message))
        if self._matches_filters(category, message):
            self.log_view.appendPlainText(message)

    def _on_filter_changed(self, selected: str):
        self._current_filter = selected
        self._rebuild_view()

    def _on_search_changed(self, text: str):
        self._search_text = (text or "").strip().lower()
        self._rebuild_view()

    def _rebuild_view(self):
        self.log_view.clear()
        for category, message in self._entries:
            if self._matches_filters(category, message):
                self.log_view.appendPlainText(message)

    def _matches_filters(self, category: str, message: str) -> bool:
        category_ok = self._current_filter == "All" or category == self._current_filter
        if not category_ok:
            return False
        if not self._search_text:
            return True
        return self._search_text in str(message).lower()

    def _categorize_message(self, message: str) -> str:
        upper = message.upper()
        stripped = upper.strip()

        if (
            "[ERROR]" in upper
            or "[WARN]" in upper
            or "EXCEPTION" in upper
            or "TRACEBACK" in upper
            or "ERROR:" in upper
            or "HALTED" in upper
            or "KILL()" in upper
        ):
            return "Errors"

        program_tokens = (
            "[INFO]", "[DEBUG]", "[SAVE]", "[CAL]", "[LED]", "CAMERA:",
            "MANUAL CONTROL", "SETTINGS", "PIPELINE", "[CONTROL]", "[X_MOTOR]", "[Y_MOTOR]", "[AUX]"
        )
        if any(token in upper for token in program_tokens):
            return "Program"

        if "[RESPONSE]" in upper:
            return "Arduino Comms"

        # Common M114/position status lines, even if they arrive without prefix.
        if stripped.startswith("X:") and " Y:" in stripped and " Z:" in stripped:
            return "Arduino Comms"

        comm_tokens = (
            "[GCODE]", "[DISPATCH]", "[CONTROL_CMD]", "MARLIN", "SERIAL", "AUTOCONNECT",
            "M106", "M107", "M92", "M500", "M503", "M114", "M211", "COM"
        )
        if any(token in upper for token in comm_tokens):
            return "Arduino Comms"

        return "Other"

    def _normalize_message_label(self, message: str) -> str:
        msg = str(message).strip()
        if not msg:
            return msg

        # Already labeled (e.g. [INFO], [RESPONSE], [X_motor], etc.)
        if msg.startswith("[") and "]" in msg:
            return msg
        if "[" in msg and "]" in msg:
            return msg

        upper = msg.upper()
        if "TRACEBACK" in upper or "EXCEPTION" in upper or "ERROR" in upper or "FAILED" in upper:
            return f"[ERROR] {msg}"
        if "WARN" in upper:
            return f"[WARN] {msg}"

        # Common Marlin position/response line without explicit tag.
        if upper.startswith("X:") and " Y:" in upper and " Z:" in upper:
            return f"[RESPONSE] {msg}"

        return f"[INFO] {msg}"

    def clear_log(self):
        self._entries.clear()
        self.log_view.clear()
