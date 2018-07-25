from PyQt5.QtWidgets import QTextEdit, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

w = QWidget()
w.setWindowFlags(Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_ShowWithoutActivating)
vbox = QVBoxLayout()
vbox.addStretch(1)
w.setLayout(vbox)
w.setWindowTitle('Editing text...')
w.resize(300,300)
w.show()
b = QTextEdit()
#b.setFontItalic(True)
#b.setTextColor(QColor(255,0,0))
vbox.addWidget(b)
def func():
    PINS.value.set(b.toPlainText())
b.textChanged.connect(func)
