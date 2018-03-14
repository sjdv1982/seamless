if PINS.options.updated:
    options = PINS.options.get()
    str_options = [str(o) for o in options]
    on_change = True
    value = b.currentText()
    b.clear()
    b.addItems(str_options)
    try:
        ind = str_options.index(value)
        b.setCurrentIndex(ind)
    except ValueError:
        pass
    on_change = False
if PINS.value.updated:
    try:
        ind = str_options.index(str(PINS.value.get()))
        b.setCurrentIndex(ind)
    except IndexError:
        pass
if PINS.title.updated:
    l.setText(PINS.title.get())
    widget.setWindowTitle(PINS.title.get())
