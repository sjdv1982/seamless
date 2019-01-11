from PyQt5.QtGui import QImage, QFont, QColor
from PyQt5.QtCore import Qt
import os, numpy as np
from scipy.ndimage import sobel, gaussian_filter

arr = np.zeros(texture.shape)

displacement_weight = 2, 1.1
if normal_texture_filename != "":
    img = QImage(normal_texture_filename)
    img = img.convertToFormat(QImage.Format_RGB888)
    assert img.format() == QImage.Format_RGB888
    assert img.width()*img.height() * 3 == img.byteCount()
    tex_arr = np.array(img.bits().asarray(img.byteCount())).reshape(img.width(),img.height(), 3)
    arr += tex_arr
else:
    sigma = 1.3

    tex_arr = texture.sum(axis=-1)/3
    tex_arr2 = np.zeros(arr.shape,dtype=np.float32)
    tex_arr2[:,:,0] = 0.5 - sobel(tex_arr, 0)*displacement_weight[0]/255.0
    tex_arr2[:,:,1] = 0.5 - sobel(tex_arr, 1)*displacement_weight[0]/255.0
    tex_arr2[:,:,2] = 1
    tex_arr2 /= np.linalg.norm(tex_arr2, axis=2,keepdims=True)
    tex_arr3 = gaussian_filter(tex_arr2, sigma=sigma)
    tex_arr3 /= np.linalg.norm(tex_arr3, axis=2,keepdims=True)
    tex_arr3[:,:,:2] *= displacement_weight[1]
    arr += tex_arr3

if inscription != "":
    img = QImage(*texture.shape[:2], QImage.Format_RGB888)

    from PyQt5.QtGui import QPainter
    qp = QPainter()
    try:
        qp.begin(img)
        qp.fillRect(img.rect(), Qt.white)
        qp.setPen(Qt.black)
        fx = 2
        fy = 20
        font = QFont("Arial", int(0.7*img.height()/fy))
        qp.setFont(font)
        mx = img.width() / fx
        my = img.height() / fy
        for x in range(fx):
            for y in range(fy):
                qp.drawText(x*mx, y*my, mx, my, Qt.AlignCenter, inscription)
    finally:
        qp.end()

    txt_arr = np.array(img.bits().asarray(img.byteCount())).reshape(img.width(),img.height(), 3)
    txt_arr = txt_arr[::-1,:]

    txt_arr = np.sum(txt_arr, axis=-1)/3

    txt_arr2 = np.zeros(arr.shape,dtype=np.float32)
    txt_arr2[:,:,0] = 0.5 - sobel(txt_arr, 0)*100/255.0
    txt_arr2[:,:,1] = 0.5 - sobel(txt_arr, 1)*100/255.0
    txt_arr2[:,:,2] = 1
    txt_arr2[:,:,:2] *= displacement_weight[1]

    arr += 0.02 * txt_arr2

arr /= np.linalg.norm(arr, axis=2,keepdims=True)
return (255*arr).astype(np.uint8)
