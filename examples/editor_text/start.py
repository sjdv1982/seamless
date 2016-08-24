from seamless.qt.QtWidgets import QTextEdit, QWidget, QVBoxLayout
from seamless.qt.QtCore import Qt

w = QWidget()
w.setWindowFlags(Qt.WindowStaysOnTopHint)
vbox = QVBoxLayout()
vbox.addStretch(1)
w.setLayout(vbox)
w.setWindowTitle('Editing text...')
w.resize(300,300)
w.show()
b = QTextEdit()
vbox.addWidget(b)
def func():
    output.set(b.toPlainText())
b.textChanged.connect(func)
_cache["func"] = func
_cache["b"] = b
_cache["w"] = w
