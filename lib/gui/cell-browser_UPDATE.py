if PINS.value.defined:
    widget.setHtml(PINS.value.get())
if PINS.title.updated:
    widget.setWindowTitle(PINS.title.get())
