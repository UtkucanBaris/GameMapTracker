import sys
from PySide6.QtWidgets import QApplication
from views.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GameMapTracker")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
