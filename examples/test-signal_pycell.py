from seamless.qt.QtWidgets import QPushButton
from seamless.qt.QtCore import Qt
widget = QPushButton()
widget.setGeometry(0,0,200,100)
widget.setWindowTitle("Button")
widget.setText("Press me")
widget.setWindowFlags(Qt.WindowStaysOnTopHint)
def pressed():
    print("Button pressed")
    PINS.outp.set()
widget.pressed.connect(pressed)
widget.show()
