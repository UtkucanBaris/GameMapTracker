from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt


class ConfirmDialog(QDialog):
    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(360, 150)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        label = QLabel(message)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)

        yes_btn = QPushButton("Yes")
        no_btn = QPushButton("No")

        yes_btn.setFixedWidth(100)
        no_btn.setFixedWidth(100)

        yes_btn.clicked.connect(self.accept)
        no_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(yes_btn)
        btn_layout.addWidget(no_btn)
        btn_layout.addStretch()

        layout.addWidget(label)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
            }
            QLabel {
                color: #dcdcdc;
                font-size: 13px;
            }
            QPushButton {
                background-color: #3c3c3c;
                color: #dcdcdc;
                border: 1px solid #555;
                padding: 6px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #666;
            }
        """)
