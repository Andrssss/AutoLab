import sys
from PyQt5.QtWidgets import QApplication
from My_GUI_Docker_ver.main_window import MainWindow
from My_G_codes.G_communicate import GCodeControl
from THREADS.thread_control import ThreadControl

if __name__ == "__main__":
    app = QApplication(sys.argv)
    g_control = GCodeControl()
    thread_contol = ThreadControl()
    window = MainWindow(g_control, thread_contol)
    window.show()

    sys.exit(app.exec_())
