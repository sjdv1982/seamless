
if PINS.circles.updated or PINS.fincircles.updated:
    build_circles()
    widget.repaint()

if PINS.ellipsity.updated:
    ellipsity = PINS.ellipsity.get()
    widget.repaint()

if PINS.depth.updated:
    depth = PINS.depth.get()
    widget.repaint()

if PINS.reaction_time.updated:
    reaction_time = PINS.reaction_time.get()
    widget.repaint()

if PINS.max_speed.updated:
    max_speed = PINS.max_speed.get()
    widget.repaint()
