if PINS.val.updated:
    widget.setHtml(PINS.val.get().data, fake_url)
if PINS.title.updated:
    widget.setWindowTitle(PINS.title.get().data)
