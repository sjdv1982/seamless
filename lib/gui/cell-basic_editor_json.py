from seamless.qt.QtWidgets import QTextEdit, QWidget, QVBoxLayout
from seamless.qt.QtCore import Qt
from PyQt5.QtGui import QColor
import json

w = QWidget()
#w.setWindowFlags(Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_ShowWithoutActivating)
vbox = QVBoxLayout()
vbox.addStretch(1)
w.setLayout(vbox)
w.setWindowTitle(title)
w.resize(300,300)
w.show()
b = QTextEdit()
b.setText(json.dumps(value))
vbox.addWidget(b)
def func():
    output.set(b.toPlainText())
b.textChanged.connect(func)
_cache["func"] = func
_cache["b"] = b
_cache["w"] = w
