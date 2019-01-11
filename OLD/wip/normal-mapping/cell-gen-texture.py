from PyQt5.QtGui import QImage, QFont, QColor
from PyQt5.QtCore import Qt
import os, numpy as np

img = QImage(filename)
img = img.convertToFormat(QImage.Format_RGB888)
assert img.format() == QImage.Format_RGB888
assert img.width()*img.height()*3 == img.byteCount()

if inscription != "":
    img2 = QImage(img.width(), img.height(), QImage.Format_RGB888)

    from PyQt5.QtGui import QPainter
    qp = QPainter()
    try:
        qp.begin(img2) #different results than painting on img!
        qp.drawImage(0,0,img)
        qp.setPen(QColor(255,185,50))
        fx = 2
        fy = 20
        font = QFont("Arial", int(0.7*img.height()/fy))
        qp.setFont(font)
        mx = img.width() / fx
        my = img.height() / fy
        for x in range(fx):
            for y in range(fy):
                qp.drawText(x*mx, y*my, mx, my, Qt.AlignCenter,inscription)
    finally:
        qp.end()
    img = img2

arr = np.array(img.bits().asarray(img.byteCount())).reshape(img.width(),img.height(),3)
arr = arr[::-1,:,:]
return arr
