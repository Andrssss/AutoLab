# Erre az osztályra azért van szükség, mert különben GUI kifagy

from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot

class CommandSender(QThread):
    sendCommand = pyqtSignal(str)  # Külsőből hívható, parancsokat vesz át

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
                self.g_control.new_command(command) # prioritás ?
            self.msleep(50)  # kis szünet, hogy ne pörögjön folyamatosan

        print("CommandSender close")
