if PINS.value.updated:
    b.setText(json.dumps(PINS.value.get(), indent=2))
if PINS.title.updated:
    b.setWindowTitle(PINS.title.get())
