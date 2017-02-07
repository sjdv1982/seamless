from seamless.qt.QtWidgets import QSpinBox, QWidget, QVBoxLayout
from seamless.qt.QtCore import Qt

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
b.valueChanged.connect(value.set)
