from PyQt5.QtGui import QImage, QFont
from PyQt5.QtCore import Qt
import os, numpy as np

img = QImage(500, 500, QImage.Format_RGB888)


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

img = img.convertToFormat(QImage.Format_RGB888)
assert img.format() == QImage.Format_RGB888
assert img.width()*img.height()*3 == img.byteCount()
arr = np.array(img.bits().asarray(img.byteCount())).reshape(img.width(),img.height(),3)
arr = arr[::-1,:,:]
return arr
