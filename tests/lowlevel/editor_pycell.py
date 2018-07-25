from PyQt5.QtWidgets import QSpinBox, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
w = QWidget()
w.setWindowFlags(Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_ShowWithoutActivating)
vbox = QVBoxLayout()
vbox.addStretch(1)
w.setLayout(vbox)
w.setWindowTitle('Test editor')
w.resize(300,100)
w.show()
b = QSpinBox()
vbox.addWidget(b)
b.valueChanged.connect(PINS.value.set)
