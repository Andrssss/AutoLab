# This class is needed to prevent GUI freezing.

from collections import deque
from threading import Lock
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot

class CommandSender(QThread):
    sendCommand = pyqtSignal(str)  # Callable from outside; accepts commands

    def __init__(self, g_control):
        super().__init__()
        self.g_control = g_control
        self.queue = deque()
        self._queue_lock = Lock()
        self.running = True
        self.sendCommand.connect(self.handle_command)

    @pyqtSlot(str)
    def handle_command(self, command):
        with self._queue_lock:
            self.queue.append(command)

    def clear_pending_commands(self, predicate=None):
        """Remove queued commands. If predicate is None, clear all pending commands."""
        with self._queue_lock:
            if predicate is None:
                removed = len(self.queue)
                self.queue.clear()
                return removed

            kept = deque()
            removed = 0
            while self.queue:
                cmd = self.queue.popleft()
                if predicate(cmd):
                    removed += 1
                else:
                    kept.append(cmd)
            self.queue = kept
            return removed

    def run(self):
        while self.running:
            command = None
            with self._queue_lock:
                if self.queue:
                    command = self.queue.popleft()
            if command is not None:
                self.g_control.new_command(command) # priority?
            self.msleep(50)  # short pause to avoid busy looping

        print("CommandSender close")

    def stop(self):
        self.running = False
        self.wait()