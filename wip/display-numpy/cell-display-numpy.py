from PyQt5.QtWidgets import QMainWindow, QLabel, QLayout, QHBoxLayout, QVBoxLayout, QWidget, QFrame
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, QSize
import numpy as np

#partially based on code ported from https://gist.github.com/pavel-perina/1324ff064aedede0e01311aab315f83d

class AspectLayout(QLayout):
    def __init__(self, aspect):
        self.aspect = aspect
        self.item = None
        super().__init__()
        self.setContentsMargins(0,0,0,0)

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

    def setGeometry(self, rect):
        super().setGeometry(rect)
        margins = self.getContentsMargins()
        if self.item is not None:
            availW = rect.width() - margins[1] - margins[3]
            availH = rect.height() - margins[0] - margins[2]
            h = availH
            w = h * self.aspect
            if w > availW:
                x = margins[1]
                w = availW
                h = w/self.aspect
                if self.item.alignment() &  Qt.AlignTop:
                    y = margins[0]
                elif self.item.alignment() &  Qt.AlignBottom:
                    y = rect.height() - margins[2] - h
                else:
                    y = margins[0] + (availH-h) / 2
            else:
                y = margins[0]
                if self.item.alignment() &  Qt.AlignLeft:
                    x = margins[1]
                elif self.item.alignment() &  Qt.AlignRight:
                    x = rect.width() - margins[3] - w
                else:
                    x = margins[1] + (availW-w) / 2
            self.item.widget().setGeometry(
                rect.x() + x,
                rect.y() + y,
                w, h)

    def sizeHint(self):
        margins = self.getContentsMargins()
        if self.item is None:
            return QSize(margins[0]+margins[2],margins[1]+margins[3])
        s = self.item.sizeHint()
        w, h = s.width(), s.height()
        return QSize(margins[0]+margins[2] + w, margins[1]+margins[3] + h)

    def minimumSize(self):
        margins = self.getContentsMargins()
        if self.item is None:
            return QSize(margins[0]+margins[2],margins[1]+margins[3])
        s = self.item.minimumSize()
        w, h = s.width(), s.height()
        return QSize(margins[0]+margins[2] + w, margins[1]+margins[3] + h)

    def expandingDirections(self):
       return Qt.Horizontal | Qt.Vertical

    def hasHeightForWidth(self):
        return False

    def count(self):
        if self.item is None:
            return 0
        else:
            return 1

    def heightForWidth(self, width):
        margins = self.getContentsMargins()
        height = (width - margins[1] - margins[3]) / self.aspect
        height += margins[0] + margins[2]
        return int(height)

w = QWidget()
asp = AspectLayout(1.0)
w.setLayout(asp)
w.setWindowFlags(Qt.WindowStaysOnTopHint)

l = QLabel()
l.setScaledContents(True)
asp.addWidget(l)
l.setFrameStyle(QFrame.NoFrame)
w.show()

def update():
    global arr
    arr = PINS.array.get()
    assert arr.dtype in (float, np.float32), arr.dtype
    arr = np.ascontiguousarray(arr)
    if arr.ndim == 1:
        arr = arr.reshape((len(arr), 1))
    if arr.ndim == 3:
        assert arr.shape[-1] == 3
        amin = arr.min(axis=0).min(axis=0)
        amax = arr.max(axis=0).max(axis=0)
        arange = np.maximum(amax-amin, 1e-12)
        arr_norm = (arr - amin) / arange
        arr_norm_255 = ((arr_norm- 1e-6)*256).astype(np.uint8)
        width, height = arr.shape[1], arr.shape[0]
        im = QImage(arr_norm_255, width, height, width*3, QImage.Format_RGB888)
    elif arr.ndim == 2:
        amin = arr.min()
        amax = arr.max()
        arange = np.maximum(amax-amin, 1e-12)
        arr_norm = (arr - amin) / arange
        arr_norm_255 = ((arr_norm- 1e-6)*256).astype(np.uint8)
        arr_color = np.zeros((arr.shape) + (3,), dtype=np.uint8)
        arr_color[:,:,0] = arr_norm_255
        arr_color[:,:,1] = 128 - np.abs(arr_norm_255.astype(int)-128)
        arr_color[:,:,2] = 255 - arr_norm_255
        width, height = arr_color.shape[1], arr_color.shape[0]
        im = QImage(arr_color, width, height, width*3, QImage.Format_RGB888)

    pm = QPixmap.fromImage(im)
    asp.aspect = width / height
    w.updateGeometry()
    l.setPixmap(pm)
def destroy():
    global w, l
    del l
    del w

update()
