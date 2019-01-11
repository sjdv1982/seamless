import time

def new_explosion():
    global start_time
    start_time = time.time()

def update():
    u_time = time.time() - start_time
    PINS.uniforms.set({
        "u_time": u_time,
    })

new_explosion()
