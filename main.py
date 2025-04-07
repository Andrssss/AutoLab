import sys
from PyQt5.QtWidgets import QApplication
from My_GUI_Docker_ver.main_window import MainWindow
from My_G_codes.G_communicate import GCodeControl
from THREADS.thread_control import LockRegistry

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Ezekből csak 1-1 példány lesz, ezért itt hozom létre, hogy bárkinek oda tudjam innen adni.
    locks = LockRegistry()
    g_control = GCodeControl(locks)


    # Főablak létrehozás és indítás
    window = MainWindow(g_control, locks)
    window.show()

    sys.exit(app.exec_())
