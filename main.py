import sys
from threading import Lock
from PyQt5.QtWidgets import QApplication
from GUI.main_window import MainWindow
from Pozitioner_and_Communicater.G_communicate import GCodeControl

if __name__ == "__main__":
    app = QApplication(sys.argv)

    lock = Lock()

    g_control = GCodeControl(lock)

    # Create and launch main window
    window = MainWindow(g_control)
    window.showMaximized()


    del g_control
    sys.exit(app.exec_())

