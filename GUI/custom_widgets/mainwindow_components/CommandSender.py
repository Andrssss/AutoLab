# This class is needed to prevent GUI freezing.

from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot

class CommandSender(QThread):
    sendCommand = pyqtSignal(str)  # Callable from outside; accepts commands

    def __init__(self, g_control):
        super().__init__()
        self.g_control = g_control
        self.queue = []
        self.running = True
        self.sendCommand.connect(self.handle_command)

    @pyqtSlot(str)
    def handle_command(self, command):
        self.queue.append(command)

    def run(self):
        while self.running:
            if self.queue:
                command = self.queue.pop(0)
                self.g_control.new_command(command) # priority?
            self.msleep(50)  # short pause to avoid busy looping

        print("CommandSender close")

    def stop(self):
        self.running = False
        self.wait()