from seamless.qt.QtWidgets import QLineEdit, QWidget, QVBoxLayout
from seamless.qt.QtCore import Qt

w = QWidget()
#w.setWindowFlags(Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_ShowWithoutActivating)
vbox = QVBoxLayout()
vbox.addStretch(1)
w.setLayout(vbox)
w.resize(300,100)
w.setWindowTitle(PINS.title.get())
w.show()
b = QLineEdit()
if PINS.value.defined:
    b.setText(PINS.value.get())
vbox.addWidget(b)
b.textChanged.connect(PINS.value.set)
