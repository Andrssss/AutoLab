import sys
import random
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QAction,
    QDockWidget, QWidget, QVBoxLayout, QLabel, QTabWidget
)
from PyQt5.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("MainWindow - interface")
        self.resize(1000, 600)

        # Menüsor létrehozása
        menubar = self.menuBar()

        # Menük létrehozása
        self.form_menu = menubar.addMenu("Form")
        self.view_menu = menubar.addMenu("View")
        self.settings_menu = menubar.addMenu("Settings")
        self.window_menu = menubar.addMenu("Window")
        self.typehere_menu = menubar.addMenu("Type Here")

        # Kapcsolódunk az aboutToShow jelzéshez (mindegyik menünél)
        self.form_menu.aboutToShow.connect(self.show_random_form_menu)
        self.view_menu.aboutToShow.connect(self.show_random_view_menu)
        self.settings_menu.aboutToShow.connect(self.show_random_settings_menu)
        self.window_menu.aboutToShow.connect(self.show_random_window_menu)
        self.typehere_menu.aboutToShow.connect(self.show_random_typehere_menu)

        # ToolBar
        toolbar = QToolBar("Fő eszköztár")
        self.addToolBar(toolbar)

        # Néhány példa QAction
        new_action = QAction("New", self)
        open_action = QAction("Open", self)
        save_action = QAction("Save", self)

        # Hozzáadjuk az akciókat a ToolBar-hoz
        toolbar.addAction(new_action)
        toolbar.addAction(open_action)
        toolbar.addAction(save_action)

        # Központi widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Bal oldali DockWidget
        left_dock = QDockWidget("Widget Box", self)
        left_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Layouts"))
        left_layout.addWidget(QLabel("Vertical Layout"))
        left_layout.addWidget(QLabel("Horizontal Layout"))
        left_layout.addWidget(QLabel("Spaces"))
        left_widget.setLayout(left_layout)
        left_dock.setWidget(left_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        # Jobb oldali DockWidget
        right_dock = QDockWidget("Properties", self)
        right_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        right_tabwidget = QTabWidget()
        right_tabwidget.addTab(QWidget(), "Object Inspector")
        right_tabwidget.addTab(QWidget(), "Property Editor")
        right_tabwidget.addTab(QWidget(), "Resource Browser")
        right_tabwidget.addTab(QWidget(), "Action Editor")

        right_dock.setWidget(right_tabwidget)
        self.addDockWidget(Qt.RightDockWidgetArea, right_dock)

    def show_random_form_menu(self):
        # Töröljük a menü jelenlegi elemeit
        self.form_menu.clear()
        # Generáljunk véletlenszerű számú menüpontot
        count = random.randint(1, 5)
        for i in range(count):
            action = QAction(f"Form Random {i + 1}", self)
            self.form_menu.addAction(action)

    def show_random_view_menu(self):
        self.view_menu.clear()
        count = random.randint(1, 4)
        for i in range(count):
            action = QAction(f"View Random {i + 1}", self)
            self.view_menu.addAction(action)

    def show_random_settings_menu(self):
        self.settings_menu.clear()
        count = random.randint(2, 6)
        for i in range(count):
            action = QAction(f"Settings Random {i + 1}", self)
            self.settings_menu.addAction(action)

    def show_random_window_menu(self):
        self.window_menu.clear()
        count = random.randint(1, 3)
        for i in range(count):
            action = QAction(f"Window Random {i + 1}", self)
            self.window_menu.addAction(action)

    def show_random_typehere_menu(self):
        self.typehere_menu.clear()
        count = random.randint(1, 5)
        for i in range(count):
            action = QAction(f"TypeHere Random {i + 1}", self)
            self.typehere_menu.addAction(action)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
