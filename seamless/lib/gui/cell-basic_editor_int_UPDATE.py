if PINS.value.updated:
    b.setValue(PINS.value.get())
if PINS.title.updated:
    w.setWindowTitle(PINS.title.get())
if PINS.maximum.updated:
    b.setMaximum(PINS.maximum.get())
