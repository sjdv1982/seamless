import numpy as np

if len(filename):
    # Create a texture (from image)
    from PIL import Image
    im = Image.open(filename)
    im = im.resize((2 * radius + 1, 2 * radius + 1))
    im1 = np.asarray(im)
else:
    # Create a texture (random)
    im1 = 255 * np.ones(dtype=np.float32, shape=(2 * radius + 1, 2 * radius + 1, 3))

# Mask it with a disk
L = np.linspace(-radius, radius, 2 * radius + 1)
(X, Y) = np.meshgrid(L, L)
im1 = im1 * np.array((X ** 2 + Y ** 2) <= radius * radius)[:,:,None]

# Convert to float32 (optional)
if as_float:
    im1 = np.array(im1, dtype="float32")/255
texture = im1
return texture
