import sys
from PyQt5.QtWidgets import QApplication
from My_GUI_Docker_ver.main_window import MainWindow
from My_G_codes.G_communicate import GCodeControl
from THREADS.thread_control import LockRegistry

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Ezekből csak 1-1 példány lesz, ezért itt hozom létre, hogy bárkinek oda tudjam innen adni.
    # ( Singletonok, majd talánt átírom python sintax szerint, csak még nem volt rá időm )
    locks = LockRegistry()
    lock = LockRegistry.get("G-code_lock")

    g_control = GCodeControl(lock)
    g_control.start_threads()

    # Főablak létrehozás és indítás
    window = MainWindow(g_control, locks)
    window.show()

    del g_control
    sys.exit(app.exec_())

