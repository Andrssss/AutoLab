import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QDockWidget, QTextEdit, QListWidget
from PyQt5.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Központi widget beállítása
        self.setCentralWidget(QTextEdit())

        # Dock widget létrehozása
        dock = QDockWidget("Dokkolható", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        # Tartalom hozzáadása a dock widgethez
        list_widget = QListWidget()
        list_widget.addItems(["Elem 1", "Elem 2", "Elem 3"])
        dock.setWidget(list_widget)

        # Dock widget hozzáadása a főablakhoz
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        self.setWindowTitle("QDockWidget példa")

app = QApplication(sys.argv)
app.setStyle("Fusion") # A Fusion stílus használata biztosítja, hogy az alkalmazás megjelenése konzisztens legyen különböző platformokon
window = MainWindow()
window.show()
sys.exit(app.exec_())
