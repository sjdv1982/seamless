from seamless.qt.QtWidgets import QLabel
from seamless.qt.QtGui import QPainter, QPixmap, QPen
from seamless.qt.QtCore import Qt, QPoint, QRect, QUrl
from seamless.qt import QtCore
from math import asin, acos, pi, sqrt
import itertools
import random
import numpy as np
import time
displacement = np.zeros((10000, 2))

from PyQt5.QtMultimedia import QSoundEffect
sound1 = QSoundEffect()
sound1.setSource(QUrl.fromLocalFile("orca.wav"))
sound1.setVolume(0.09)

sound2 = QSoundEffect()
sound2.setSource(QUrl.fromLocalFile("orca2.wav"))
sound2.setVolume(0.09)

orca_sound = None
sound3 = QSoundEffect()
sound3.setSource(QUrl.fromLocalFile("underwater.wav"))
sound3.setVolume(0.20)
all_circles = []
def build_circles():
    global all_circles, lead_y
    circles = sorted(
      SideviewPointArray(PINS.circles.get()),
      key=lambda p:-p.x
    )
    lead = circles[-1]
    lead_y = (lead.ytop + lead.ybottom)/2

    #3-fold interpolation
    circles2 = []
    split = 2
    for n in range(len(circles)-1):
        c1 = circles[n]
        c2 = circles[n+1]
        if c1.ybottom is None or c2.ybottom is None:
            continue
        circles2.append(c1)
        for nn in range(split):
            f = (nn+1.0)/(split+1)
            x = (1-f) * c1.x + f * c2.x
            ytop = (1-f) * c1.ytop + f * c2.ytop
            ybottom = (1-f) * c1.ybottom + f * c2.ybottom
            if len(c1.ysegments) == len(c2.ysegments):
                ysegments = []
                for nnn in range(len(c1.ysegments)):
                    yseg = (1-f) * c1.ysegments[nnn] + f * c2.ysegments[nnn]
                    ysegments.append(yseg)
            else:
                if f <= 0.5:
                    ysegments = c1.ysegments
                else:
                    ysegments = c2.ysegments
            p = SideviewPoint(x,ytop,ybottom=ybottom,ysegments=ysegments)
            circles2.append(p)
    circles2.append(circles[-1])


    fincircles = FinCircleArray(PINS.fincircles.get())
    all_circles = sorted(
      itertools.chain(circles2, fincircles),
      key=lambda p:-p.x
    )

def draw_circle(painter, center, radius, ysegments):
    painter.setBrush(Qt.black)
    if not len(ysegments):
        painter.drawEllipse(
            QPoint(
                center[0],
                center[1]
            ),
            radius*ellipsity, radius
        )
    else:
        angles = [0]
        for y in ysegments:
            ang = acos(max(min(y,1),-1))
            angles.append(ang/pi*180)
        for a in list(reversed(angles)):
            angles.append(360-a)
        for n in range(len(angles)-1):
            start = 16 * (angles[n]+90) #0 = 3 o'clock, but we start at 12 o'clock
            arc = 16 * (angles[n+1] - angles[n]) #Qt wants the size in 1/16 of a deg
            painter.drawPie(
                QRect(
                    center[0] - radius * ellipsity,
                    center[1] - radius,
                    2 * radius * ellipsity,
                    2* radius
                ),
                start, arc
            )
            if not n % 2:
                painter.setBrush(Qt.white)
            else:
                painter.setBrush(Qt.black)

class MyWidget(QLabel):
    _following = False
    painter = None
    def paintEvent(self, event):
        super().paintEvent(event)
        if not sound3.loopsRemaining():
            sound3.play()
        global curr_time
        new_time = time.time()
        d = new_time - curr_time
        if d >= reaction_time:
            displacement[:] = displacement[0]
        else:
            steps = int(d/reaction_time * len(displacement)+0.5)
            if steps > 0:
                displacement[steps:] = displacement[:-steps]
                displacement[:steps] = displacement[0]
        d = displacement[::20] - displacement[0]
        if np.max(d*d) < 1:
            timer.stop()
        curr_time = new_time
        qp = self.painter = QPainter()
        qp.begin(self)
        qp.setPen(Qt.NoPen)
        w = self.size().width()
        h = self.size().height()
        for circle in all_circles:
            qp.setBrush(Qt.black)
            px = circle.x
            depthfactor = depth**0.2 * depth**(-px)
            dispos = int(px*len(displacement)+0.5)
            dis = displacement[dispos]
            if isinstance(circle, SideviewPoint):
                if circle.ybottom is None:
                    continue
                mid = (circle.ytop + circle.ybottom) / 2
                radius = abs((circle.ytop - circle.ybottom) / 2)
                ysegments = [-(y-mid)/radius for y in circle.ysegments]
                draw_circle(qp, (dis[0],(mid-lead_y)*h*depthfactor+dis[1]),
                             radius*h*depthfactor, ysegments)
            elif isinstance(circle, FinCircle):
                mid = (circle.distance + circle.yradius) * depthfactor
                #pr
                qp.save()
                qp.translate(dis[0],dis[1] + (circle.ycenter - lead_y) * h * depthfactor)
                qp.rotate(180)
                qp.rotate(circle.rotation)
                qp.translate(0,mid*h)
                qp.drawEllipse(
                    QPoint(0,0),
                    w*circle.xradius*depthfactor,
                    h*circle.yradius*depthfactor
                )
                qp.restore()
        self.painter.end()
        if self._following:
            self.follow()

    def follow(self):
        global orca_sound
        if orca_sound is None or not orca_sound.loopsRemaining():
            if random.random() < 0.5:
                orca_sound = sound1
            else:
                orca_sound = sound2
            orca_sound.play()
        if not sound3.loopsRemaining():
            sound3.play()
        max_displ = max_speed / 1000 * \
            max(self.size().width(), self.size().height())
        curr_displacement = displacement[0]
        new_displacement = self.target
        delta_displacement_sq = (curr_displacement[0]-new_displacement[0])**2 + \
          (curr_displacement[1]-new_displacement[1])**2
        if delta_displacement_sq <= max_displ*max_displ:
            displacement[0] = new_displacement
            self._following = False
        else:
            frac = max_displ/sqrt(delta_displacement_sq)
            displacement[0] = (
                frac * new_displacement[0] + (1-frac) * curr_displacement[0],
                frac * new_displacement[1] + (1-frac) * curr_displacement[1],
            )
            if not timer.isActive():
                timer.start(20)
            self._following = True

    def leaveEvent(self, event):
        self.target = (
            0.5 * widget.size().width(),
            0.7 * widget.size().height(),
        )
        self.follow()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self.target = (
            event.x(),
            event.y(),
        )
        self.follow()
        super().mouseMoveEvent(event)

widget = MyWidget()
widget.setMouseTracking(True)
myPixmap = QPixmap('sea.jpeg')
widget.setPixmap(myPixmap)
widget.setScaledContents(True)
widget.setWindowTitle("Isaure's Orca Screensaver")
curr_time = time.time()
widget.show()
displacement[:] =(
    0.5 * widget.size().width(),
    0.7 * widget.size().height(),
)

timer = QtCore.QTimer()
timer.timeout.connect(lambda: widget.repaint())
