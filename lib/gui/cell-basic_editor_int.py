from seamless.qt.QtWidgets import QSpinBox, QWidget, QVBoxLayout
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
b = QSpinBox()
b.setMaximum(1000000)
if PINS.value.defined:
    b.setValue(PINS.value.get())
vbox.addWidget(b)
b.valueChanged.connect(PINS.value.set)
