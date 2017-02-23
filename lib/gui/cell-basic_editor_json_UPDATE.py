if PINS.value.updated:
    b.setText(json.dumps(PINS.value.get(), indent=2))
if PINS.title.updated:
    w.setWindowTitle(PINS.title.get())
