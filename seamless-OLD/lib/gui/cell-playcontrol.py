from PyQt5.QtWidgets import QToolButton, QSpinBox, QWidget, QHBoxLayout, \
  QCheckBox, QLabel
from PyQt5.QtGui import  QIcon
from PyQt5.QtCore import QTimer
import time
widget = QWidget()
widget.setWindowTitle(PINS.title.get())
layout = QHBoxLayout(widget)
buttons = []

timer = QTimer()

negative = False
pace = 0

b = QToolButton(widget)
b.setIcon(QIcon.fromTheme("media-skip-backward"))
layout.addWidget(b)
buttons.append(b)

b = QToolButton(widget)
b.setIcon(QIcon.fromTheme("media-seek-backward"))
layout.addWidget(b)
buttons.append(b)

b = QToolButton(widget)
b.setIcon(QIcon.fromTheme("media-playback-start"))
layout.addWidget(b)
buttons.append(b)

b = QToolButton(widget)
b.setIcon(QIcon.fromTheme("media-playback-stop"))
layout.addWidget(b)
buttons.append(b)

sb = QSpinBox(widget)
sb.setMinimum(PINS.min.get())
sb.setValue(PINS.value.get())
layout.addWidget(sb)

b = QToolButton(widget)
b.setIcon(QIcon.fromTheme("media-seek-forward"))
layout.addWidget(b)
buttons.append(b)

b = QToolButton(widget)
b.setIcon(QIcon.fromTheme("media-skip-forward"))
layout.addWidget(b)
buttons.append(b)

label = QLabel(widget)
label.setText("Loop")
layout.addWidget(label)

lb = QCheckBox(widget)
lb.setChecked(PINS.loop.get())
layout.addWidget(lb)

widget.show()


def skip_back():
    sb.setValue(sb.minimum())
buttons[0].pressed.connect(skip_back)
def skip_fwd():
    sb.setValue(sb.maximum())
buttons[-1].pressed.connect(skip_fwd)


def play():
    global pace, negative
    negative = False
    pace = 1
    update_timer()
buttons[2].pressed.connect(play)

def stop():
    global pace
    pace = 0
    update_timer()
buttons[3].pressed.connect(stop)

def fast_bwd():
    global pace, negative
    negative = True
    pace = 5
    update_timer()
buttons[1].pressed.connect(fast_bwd)

def fast_fwd():
    global pace, negative
    negative = False
    pace = 5
    update_timer()
buttons[-2].pressed.connect(fast_fwd)

last_value = None

def update_spinbox():
    global last_value
    _updating = True
    v = sb.value() + (1-2*negative)
    if loop and v > sb.maximum():
        v = sb.minimum()
    last_value = v
    sb.setValue(v)

def timer_shot():
    try:
        update_spinbox()
    finally:
        if pace != 0:
            timer.singleShot(timer.interval(), timer_shot)

def update_value(value):
    global last_value
    if value_updated:
        return
    last_value = value
    PINS.value.set(value)

sb.valueChanged.connect(update_value)

def update_timer():
    if pace != 0:
        timer.setInterval(1000/(rate*pace))
        timer.singleShot(timer.interval(), timer_shot)
    else:
        timer.stop()

lb.toggled.connect(PINS.loop.set)

def do_update():
    global rate, last_value, loop, value_updated
    sb.setMaximum(PINS.max.get())
    if PINS.value.updated:
        try:
            value_updated = True
            value = PINS.value.get()
            if value != last_value:
                last_value = value
                sb.setValue(value)
        finally:
            value_updated = False
    if PINS.rate.updated:
        rate = PINS.rate.get()
        update_timer()
    if PINS.loop.updated:
        loop = PINS.loop.get()
        lb.setChecked(loop)
