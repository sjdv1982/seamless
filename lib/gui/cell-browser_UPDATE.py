if PINS.value.defined:
    widget.setHtml(PINS.value.get(), fake_url)
if PINS.title.updated:
    widget.setWindowTitle(PINS.title.get())
