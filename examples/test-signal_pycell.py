import random
from seamless.qt.QtWidgets import QPushButton
from seamless.qt.QtCore import Qt
widget = QPushButton()
widget.setGeometry(0,0,200,100)
widget.setWindowTitle("Button")
widget.setText("Press me")
widget.setWindowFlags(Qt.WindowStaysOnTopHint)
PINS.outp2.set(0)
def pressed():
    print("Sender: Button pressed, sending signal")
    PINS.outp.set()
    print("Sender: Signal sending completed")
    print("Sender: Setting secondary output")
    PINS.outp2.set(random.randint(1,1000000))
    print("Sender: Setting secondary output completed")
widget.pressed.connect(pressed)
widget.show()
