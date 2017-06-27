from seamless.qt.QtWidgets import QLabel
from seamless.qt.QtGui import QPainter, QPixmap, QPen
from seamless.qt.QtCore import Qt, QPoint, QRectF
from seamless.qt import QtGui, QtCore, QtWidgets

point_radius = 7

def draw_point(qp, w, h, x, y):
    qp.drawEllipse(
        QPoint(
          x*w,
          y*h,
        ),
        point_radius, point_radius
    )

my_points = SideviewPointArray(PINS.points.get())
myPixmap = QPixmap('orca.png')

class active_point:
    index = None
    @classmethod
    def reset(self):
        ind = self.index
        self.index = None
        self.point_field = None
        self.point_field_index = None
        self.x = None
        self.y = None
        if ind is not None:
            widget.repaint()

    @classmethod
    def find_point(self, x, y):
        w = widget.size().width()
        h = widget.size().height()
        ex, ey = x, y
        if y is None:
            def is_close(px, py):
                return (w*px-ex)**2<point_radius**2
        else:
            def is_close(px, py):
                return (w*px-ex)**2+(h*py-ey)**2<point_radius**2
        for pnr, p in enumerate(my_points):
            if is_close(p.x, p.ytop):
                self.index = pnr
                self.point_field = "ytop"
                break
            elif y is None:
                 continue
            elif p.ybottom is not None and is_close(p.x, p.ybottom):
                self.index = pnr
                self.point_field = "ybottom"
                break
            else:
                found = False
                for ppnr, pp in enumerate(p.ysegments):
                    if is_close(p.x, pp):
                        self.index = pnr
                        self.point_field = "ysegments"
                        self.point_field_index = ppnr
                        found = True
                        break
                if found:
                    break

    @classmethod
    def update(self, x, y):
        if self.index is None:
            return
        self.x, self.y = self.convert(x,y)

    @classmethod
    def convert(self, x, y):
        w = widget.size().width()
        h = widget.size().height()
        return x/w,y/h

    @classmethod
    def commit(self):
        if self.index is None:
            return
        p = my_points[self.index]
        p.x = self.x
        if self.point_field == "ytop":
            p.ytop = self.y
        elif self.point_field == "ybottom":
            p.ybottom = self.y
        elif self.point_field == "ysegments":
            p.ysegments[self.point_field_index] = self.y
        PINS.points.set(my_points)
        self.reset()

active_point.reset()


class MyWidget(QLabel):
    def paintEvent(self, event):
        super().paintEvent(event)
        qp = QPainter()
        qp.begin(self)
        qp.setBrush(Qt.red)
        w = self.size().width()
        h = self.size().height()
        qp.save()
        qp.setPen(Qt.red)
        qp.setFont(QtGui.QFont('Arial', 14))
        txt = """Drag the points with the mouse to change the circles of the orca
Blue points: top of the orca
Cyan points: bottom of the orca
Green points: border between black and white
Cyan and green points are linked to blue points

Shift+LClick creates a new blue point
Ctrl+LClick: adds a cyan point or a green point to a existing blue point
Ctrl+RClick, Shift+RClick: deletes a point
"""
        qp.drawText(QRectF(int(0.05*w),int(0.05*h), int(0.9*w), int(0.3 * h)), txt)
        qp.restore()
        ap = active_point
        api = active_point.index
        ap_pf = active_point.point_field
        ap_pfi = active_point.point_field_index
        for pointnr, point in enumerate(my_points):
            px = point.x
            if api == pointnr:
                px = ap.x
            qp.setBrush(Qt.blue)
            if api == pointnr and ap_pf == "ytop":
                draw_point(qp, w, h, px, ap.y)
            else:
                draw_point(qp, w, h, px, point.ytop)
            if point.ybottom is not None:
                qp.setBrush(Qt.cyan)
                if api == pointnr and ap_pf == "ybottom":
                    draw_point(qp, w, h, px, ap.y)
                else:
                    draw_point(qp, w, h, px, point.ybottom)
            if point.ysegments:
                qp.setBrush(Qt.green)
            for ysegind, ysegment in enumerate(point.ysegments):
                if api == pointnr and ap_pf == "ysegments" \
                  and ap_pfi ==  ysegind:
                    draw_point(qp, w, h, px, ap.y)
                else:
                    draw_point(qp, w, h, px, ysegment)
            if point.ysegments:
                qp.setBrush(Qt.red)

        qp.end()
    def mousePressEvent(self, event):
        global my_points
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        x,y = (event.x(), event.y())
        xx,yy = active_point.convert(x,y)
        if event.buttons() == QtCore.Qt.LeftButton:
            if modifiers == QtCore.Qt.ShiftModifier:
                new_point = SideviewPoint((xx,yy))
                my_points.append(new_point)
                PINS.points.set(my_points)
                self.update()
            if modifiers == QtCore.Qt.ControlModifier:
                active_point.find_point(x, None)
                index = active_point.index
                if index is not None:
                    p = my_points[index]
                    if p.ybottom is None:
                        p.ybottom = yy
                        PINS.points.set(my_points)
                    else:
                        p.ysegments.append(yy)
                        p.ysegments = sorted(p.ysegments)
                        PINS.points.set(my_points)
                    self.update()
                    active_point.index = None
        elif event.buttons() == QtCore.Qt.RightButton:
            if modifiers in (QtCore.Qt.ShiftModifier, QtCore.Qt.ControlModifier):
                active_point.find_point(x,y)
                index = active_point.index
                if index is not None:
                    if active_point.point_field == "ytop":
                        my_points.pop(index)
                        PINS.points.set(my_points)
                    elif active_point.point_field == "ybottom":
                        my_points[index].ybottom = None
                        PINS.points.set(my_points)
                    elif active_point.point_field == "ysegments":
                        findex = active_point.point_field_index
                        my_points[index].ysegments.pop(findex)
                        PINS.points.set(my_points)
                    active_point.index = None
                    self.update()


    def mouseMoveEvent(self, event):
        #if event.buttons() == QtCore.Qt.NoButton:
        #    print("Simple mouse motion")
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers != QtCore.Qt.NoModifier:
            return
        if event.buttons() == QtCore.Qt.LeftButton:
            x,y = (event.x(), event.y())
            if active_point.index is None:
                active_point.find_point(x,y)
            active_point.update(x,y)
            if active_point.index is not None:
                self.repaint()
        #elif event.buttons() == QtCore.Qt.RightButton:
        #    print("Right click drag")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        #if event.buttons() == QtCore.Qt.LeftButton:
        active_point.commit()
        super().mouseReleaseEvent(event)

widget = MyWidget()
widget.setMouseTracking(True)
widget.setPixmap(myPixmap)
widget.setScaledContents(True)
widget.setWindowTitle("Orca sideview")
widget.show()

print("START")
