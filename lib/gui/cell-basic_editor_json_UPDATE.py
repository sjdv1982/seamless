if value.updated:
    b.setText(json.dumps(value.get(), indent=2))
if title.updated:
    w.setWindowTitle(title.get())
