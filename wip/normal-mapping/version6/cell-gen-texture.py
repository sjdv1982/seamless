from PyQt5.QtGui import QImage, QFont
from PyQt5.QtCore import Qt
import os, numpy as np

img = QImage(filename)

img = img.convertToFormat(QImage.Format_RGB888)
assert img.format() == QImage.Format_RGB888
assert img.width()*img.height()*3 == img.byteCount()
arr = np.array(img.bits().asarray(img.byteCount())).reshape(img.width(),img.height(),3)
arr = arr[::-1,:,:]
return arr
