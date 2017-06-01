from threading import Timer
dead = False
def trigger():
    global t
    if dead:
        return
    PINS.trigger.set()
    t = Timer(PINS.period.get(), trigger)
    t.setDaemon(True)
    t.start()
t = Timer(PINS.period.get(), trigger)
t.setDaemon(True)
t.start()
