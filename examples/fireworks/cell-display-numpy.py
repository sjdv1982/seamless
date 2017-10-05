from PyQt5.QtWidgets import QMainWindow, QLabel, QWidget, QFrame, QSizePolicy
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, QSize
import numpy as np

w = QMainWindow(size=QSize(400, 400))
ww = QWidget()
w.setCentralWidget(ww)
asp = AspectLayout(1.0)
ww.setLayout(asp)
w.setWindowFlags(Qt.WindowStaysOnTopHint)

l = QLabel()
l.setScaledContents(True)
l.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum))
asp.addWidget(l)
l.setParent(ww)
l.setFrameStyle(QFrame.NoFrame)
w.show()

def update():
    if PINS.title.updated:
        w.setWindowTitle(PINS.title.get())
    global arr
    arr = PINS.array.get()
    assert arr.dtype in (float, np.float32, np.uint8), arr.dtype
    arr = np.ascontiguousarray(arr)
    if arr.ndim == 1:
        arr = arr.reshape((len(arr), 1))
    if arr.ndim == 3:
        if arr.shape[-1] == 4:
            arr = np.ascontiguousarray(arr[:,:,:3])
        assert arr.shape[-1] == 3
        if arr.dtype == np.uint8:
            arr_norm_255 = arr
        else:
            amin = arr.min(axis=0).min(axis=0)
            amax = arr.max(axis=0).max(axis=0)
            arange = np.maximum(amax-amin, 1e-12)
            arr_norm = (arr - amin) / arange
            arr_norm_255 = ((arr_norm- 1e-6)*256).astype(np.uint8)
        width, height = arr.shape[1], arr.shape[0]
        im = QImage(arr_norm_255, width, height, width*3, QImage.Format_RGB888)
    elif arr.ndim == 2:
        if arr.dtype == np.uint8:
            arr_norm_255 = arr
        else:
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
    aspect = width / height
    asp.aspect = aspect
    cwidth, cheight = w.size().width(), w.size().height()
    l.setPixmap(pm)
    l.setMinimumSize(1,1)
    scalex = width/cwidth
    scaley = height/cheight
    scale = max(scalex, scaley)
    if scale > 1:
        w.resize(width/scale, height/scale)
    w.updateGeometry()
def destroy():
    global w, l
    del l
    del w

#update()
