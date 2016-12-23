from seamless.qt.QtWidgets import QDoubleSpinBox, QWidget, QVBoxLayout
from seamless.qt.QtCore import Qt

w = QWidget()
w.setWindowFlags(Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_ShowWithoutActivating)
vbox = QVBoxLayout()
vbox.addStretch(1)
w.setLayout(vbox)
w.resize(300,100)
w.setWindowTitle(title)
w.show()
b = QDoubleSpinBox()
b.setSingleStep(0.1)
b.setMaximum(10)
vbox.addWidget(b)
b.valueChanged.connect(output.set)
_cache["b"] = b
_cache["w"] = w
