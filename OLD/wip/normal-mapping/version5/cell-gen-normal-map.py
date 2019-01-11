from PyQt5.QtGui import QImage, QFont
from PyQt5.QtCore import Qt
import os, numpy as np

img = QImage(1000, 1000, QImage.Format_Grayscale8)


from PyQt5.QtGui import QPainter
qp = QPainter()
try:
    qp.begin(img)
    qp.setPen(Qt.black)
    qp.fillRect(img.rect(), Qt.white)
    fx = 5
    fy = 30
    font = QFont("Arial", 0.7*img.height()/fy)
    qp.setFont(font)
    mx = img.width() / fx
    my = img.height() / fy
    for x in range(fx):
        for y in range(fy):
            qp.drawText(x*mx, y*my, mx, my, Qt.AlignCenter, "Love you Isaure")
finally:
    qp.end()

assert img.width()*img.height() == img.byteCount()
arr = np.array(img.bits().asarray(img.byteCount())).reshape(img.width(),img.height())
arr = arr[::-1,:]
print(arr.shape)
arr = arr.astype(np.float32)

from scipy.ndimage import sobel
arr2 = np.zeros(arr.shape + (3,),dtype=np.float32)
arr2[:,:,0] = 0.5 + sobel(arr, 0)/255.0
arr2[:,:,1] = 0.5 + sobel(arr, 1)/255.0
arr2[:,:,2] = 1
arr2 /= np.linalg.norm(arr2, axis=2,keepdims=True)

return (255*arr2).astype(np.uint8)
