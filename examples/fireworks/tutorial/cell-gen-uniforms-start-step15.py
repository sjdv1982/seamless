import time
import numpy as np
start_time = None

def new_explosion():
    global start_time

    N = PINS.N.get()
    if PINS.uniforms.defined:
        uniforms = PINS.uniforms.get()
    else:
        uniforms = {}

    # New centerpos
    centerpos = np.random.uniform(-0.5, 0.5, (3,))
    uniforms['u_centerPosition'] = tuple(centerpos)

    alpha = 1.0 / N ** 0.08
    color = np.random.uniform(0.1, 0.9, (3,))
    uniforms['u_color'] = tuple(color) + (alpha,)

    gravity = PINS.gravity.get()
    uniforms['u_gravity'] = gravity

    start_time = time.time()
    uniforms['u_time'] = 0
    PINS.uniforms.set(uniforms)

def update():
    if start_time is None:
        return
    uniforms = PINS.uniforms.get()
    curr_time = time.time() - start_time
    uniforms['u_time'] = curr_time
    pointsize = PINS.pointsize.get()
    uniforms['u_pointsize'] = pointsize
    shrink_with_age = PINS.shrink_with_age.get()
    uniforms['u_shrink_with_age'] = shrink_with_age
    PINS.uniforms.set(uniforms)
