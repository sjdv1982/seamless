if PINS.key.updated:
    k = PINS.key.get()
    try:
        v = int(k)
    except ValueError:
        pass
    else:
        if v in (1,2,3,4):
            state = v
    PINS.repaint.set()

if PINS.paint.updated:
    if state == 1:
        PINS.paint_lines.set()
    elif state == 2:
        PINS.paint_triangles_flat.set()
    elif state == 3:
        PINS.paint_lines.set()
        PINS.paint_triangles_flat.set()
    elif state == 4:
        PINS.paint_triangles_smooth.set()
