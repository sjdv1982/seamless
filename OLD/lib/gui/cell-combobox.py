from seamless.qt.QtWidgets import QComboBox, QWidget, QVBoxLayout, QLabel
from seamless.qt.QtCore import Qt
from PyQt5.QtGui import QColor

on_change = False

widget = QWidget()
#w.setWindowFlags(Qt.WindowStaysOnTopHint)
widget.setAttribute(Qt.WA_ShowWithoutActivating)
vbox = QVBoxLayout()
#vbox.addStretch(1)
#widget.resize(600,600)
widget.setLayout(vbox)

widget.show()
l = QLabel()
vbox.addWidget(l)
b = QComboBox()
#b.addItems(PINS.options.get())
#b.setFontItalic(True)
#b.setTextColor(QColor(255,0,0))
vbox.addWidget(b)


def on_update(ind):
    if on_change:
        return
    PINS.value.set(options[ind])
b.currentIndexChanged.connect(on_update)
