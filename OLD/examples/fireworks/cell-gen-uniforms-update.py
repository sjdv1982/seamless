if PINS.N.updated or PINS.reset.updated or start_time is None:
    new_explosion()
if PINS.update.updated or PINS.pointsize.updated:
    update()
