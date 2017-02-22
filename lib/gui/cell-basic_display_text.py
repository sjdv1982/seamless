from seamless.qt.QtWidgets import QTextEdit, QWidget, QVBoxLayout
from seamless.qt.QtCore import Qt
from PyQt5.QtGui import QColor

w = QWidget()
#w.setWindowFlags(Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_ShowWithoutActivating)
vbox = QVBoxLayout()
#vbox.addStretch(1)
w.resize(600,600)
w.setLayout(vbox)
w.setWindowTitle(PINS.title.get())

w.show()
b = QTextEdit()
b.setReadOnly(True)
b.setFontPointSize(15)
b.setText(PINS.value.get())
#b.setFontItalic(True)
#b.setTextColor(QColor(255,0,0))
vbox.addWidget(b)
