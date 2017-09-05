from PyQt5.QtWidgets import QMainWindow, QLabel, QLayout, QHBoxLayout, QVBoxLayout, QWidget
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, QSize
import numpy as np

class AspectLayout(QLayout):
    def __init__(self, aspect):
        self.aspect = aspect
        self.item = None
        super().__init__()
    def addItem(self, item):
        assert self.item is None, "AspectLayout can contain only 1 widget"
        self.item = item
    def itemAt(self, index):
        if index != 0:
            return None
        if self.item is None:
            return None
        return self.item
    def takeAt(self, index):
        if index != 0:
            return None
        if self.item is None:
            return None
        result = self.item
        self.item = None
        return result
    def sizeHint(self):
        if self.item is None:
            return QSize(0,0)
        w,h = self.item.sizeHint()
        return w, self.aspect * w
    def hasHeightForWidth(self):
        print("OK")
        return True
    def count(self):
        if self.item is None:
            return 0
        else:
            return 1
    def heightForWidth(self, width):
        print("O", self.aspect, width)
        return int(self.aspect * width)

w = QWidget()
asp = AspectLayout(1.0)
w.setLayout(asp)
w.setWindowFlags(Qt.WindowStaysOnTopHint)

l = QLabel()
l.setScaledContents(True)
asp.addWidget(l)
w.show()

def update():
    global arr
    arr = PINS.array.get()
    assert arr.dtype in (float, np.float32), arr.dtype
    arr = np.ascontiguousarray(arr)
    if arr.ndim == 3:
        assert arr.shape[-1] == 3
        amin = arr.min(axis=0).min(axis=0)
        amax = arr.max(axis=0).max(axis=0)
        arange = np.maximum(amax-amin, 1e-12)
        arr_norm = (arr - amin) / arange
        arr_norm_255 = ((arr_norm- 1e-6)*256).astype(np.uint8)
        width, height = arr.shape[1], arr.shape[0]
        im = QImage(arr_norm_255, width, height, QImage.Format_RGB888)
    pm = QPixmap.fromImage(im)
    asp.aspect = height / width
    w.updateGeometry()
    l.setPixmap(pm)
def destroy():
    global w, l
    del l
    del w

update()
