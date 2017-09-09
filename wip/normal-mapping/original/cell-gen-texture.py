from PyQt5.QtGui import QImage
from PyQt5.QtCore import Qt
import os, numpy as np

img = QImage(os.path.join("textures", "Bricks.png"))
img = img.convertToFormat(QImage.Format_RGB888)
assert img.format() == QImage.Format_RGB888
assert img.width()*img.height()*3 == img.byteCount()
arr = np.array(img.bits().asarray(img.byteCount())).reshape(img.width(),img.height(),3)
return arr
