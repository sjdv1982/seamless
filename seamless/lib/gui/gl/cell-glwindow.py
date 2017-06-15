from seamless.qt.QtWidgets import QOpenGLWidget, QApplication
from seamless.qt.QtCore import Qt
from seamless.qt import QtGui

from seamless import add_opengl_context, remove_opengl_context, \
 activate_opengl, deactivate_opengl
from OpenGL import GL
import numpy as np
from math import *

def length(vec):
    return sqrt(np.sum(vec*vec))

def normalize(vec):
    return vec / length(vec
    )
# Camera class, uses code from the camera routines in pyqtgraph's GLViewWidget
class Camera:
    center = np.zeros(3,dtype="float")     ## will always appear at the center of the widget
    distance = 10.0          ## distance of camera from center
    fov =  60                ## horizontal field of view in degrees
    elevation =  30          ## camera's angle of elevation in degrees
    azimuth = 45             ## camera's azimuthal angle in degrees
    width = None
    height = None
    _loading = False

    #authoritative attributes
    _attrs1 = ( "center", "distance", "fov",
              "elevation", "azimuth", "width", "height")

    #derived attributes
    _attrs2 = ("projection_matrix", "modelview_matrix",
        "mvp_matrix", "normal_matrix", "position")

    @property
    def projection_matrix(self):
        # Xw = (Xnd + 1) * width/2 + X
        region = (0, 0, self.width, self.height)

        viewport = region #for now
        x0, y0, w, h = viewport
        dist = self.distance
        fov = self.fov
        nearClip = dist * 0.001
        farClip = dist * 1000.

        r = nearClip * np.tan(fov * 0.5 * np.pi / 180.)
        t = r * h / w

        # convert screen coordinates (region) to normalized device coordinates
        # Xnd = (Xw - X0) * 2/width - 1
        ## Note that X0 and width in these equations must be the values used in viewport
        left  = r * ((region[0]-x0) * (2.0/w) - 1)
        right = r * ((region[0]+region[2]-x0) * (2.0/w) - 1)
        bottom = t * ((region[1]-y0) * (2.0/h) - 1)
        top    = t * ((region[1]+region[3]-y0) * (2.0/h) - 1)

        tr = QtGui.QMatrix4x4()
        tr.frustum(left, right, bottom, top, nearClip, farClip)
        return np.array(tr.data()).reshape((4,4))

    @property
    def _modelview_matrix(self):
        tr = QtGui.QMatrix4x4()
        tr.translate( 0.0, 0.0, -self.distance)
        tr.rotate(self.elevation-90, 1, 0, 0)
        tr.rotate(self.azimuth+90, 0, 0, -1)
        center = self.center
        tr.translate(-center[0], -center[1], -center[2])
        return tr

    @property
    def modelview_matrix(self):
        tr = self._modelview_matrix
        return np.array(tr.data()).reshape((4,4))

    @property
    def normal_matrix(self):
        tr = self._modelview_matrix
        return np.array(tr.normalMatrix().data()).reshape((3,3))

    @property
    def mvp_matrix(self):
        mv = self.modelview_matrix
        p = self.projection_matrix
        return mv.dot(p)

    @property
    def position(self):
        """Return current position of camera based on center, dist, elevation, and azimuth"""
        center = self.center
        dist = self.distance
        elev = self.elevation * pi/180.
        azim = self.azimuth * pi/180.

        pos = np.array((
            center[0] + dist * cos(elev) * cos(azim),
            center[1] + dist * cos(elev) * sin(azim),
            center[2]  + dist * sin(elev)
        ))
        return pos


    def __init__(self):
        self.center = np.zeros(3)

    def _write(self):
        if self._loading:
            return
        data = {}
        for attr in self._attrs1 + self._attrs2:
            v = getattr(self, attr)
            if isinstance(v, np.ndarray):
                v = v.tolist()
            data[attr] = v
        self._data = data
        PINS.camera.set(data)

    def orbit(self, azim, elev):
        """Orbits the camera around the center position. *azim* and *elev* are given in degrees."""
        self.azimuth += azim
        self.elevation = float(np.clip(self.elevation + elev, -90, 90))
        self._write()

    def pan(self, dx, dy, dz, relative=False):
        """
        Moves the center (look-at) position while holding the camera in place.

        If relative=True, then the coordinates are interpreted such that x
        if in the global xy plane and points to the right side of the view, y is
        in the global xy plane and orthogonal to x, and z points in the global z
        direction. Distances are scaled roughly such that a value of 1.0 moves
        by one pixel on screen.

        """
        if not relative:
            self.center += dx, dy, dz
        else:
            cPos = self.position
            cVec = self.center - cPos
            dist = length(cVec)  ## distance from camera to center
            xDist = dist * 2. * tan(0.5 * self.fov * pi / 180.)  ## approx. width of view at distance of center point
            xScale = xDist / self.width
            zVec = np.array((0,0,1.))
            xVec = normalize(np.cross(zVec, cVec))
            yVec = normalize(np.cross(xVec, zVec))
            self.center += xScale * (xVec * dx + yVec * dy + zVec * dz)
        self._write()

    def resize(self, width, height):
        self.width, self.height = width, height
        self._write()

    def load(self, data):
        dif = {}
        try:
            self._loading = True
            for at in self._attrs1:
                curr = getattr(self, at)
                new = data.get(at, None)
                if new is not None:
                    if isinstance(curr, np.ndarray):
                        curr = curr.tolist()
                    if curr != new:
                        dif[at] = new
        finally:
            self._loading = False
        if len(dif):
            for at in dif:
                v = dif[at]
                curr = getattr(self,at)
                if isinstance(curr, np.ndarray):
                    curr[:] = np.array(v)
                else:
                    setattr(self, at, float(v))
            self._write()

class GLWidget(QOpenGLWidget):
    _initialized = False
    _destroyed = False
    _painting = False
    _updating = False
    _mousePos = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.camera = Camera()

    def initializeGL(self):
        super().initializeGL()
        self.camera.width = self.width()
        self.camera.height = self.height()
        self.camera._write()
        activate_opengl()
        if self._destroyed:
            return
        from PyQt5.QtGui import QOpenGLContext
        #print("INIT")
        ctx = self.context()
        assert ctx is QOpenGLContext.currentContext()
        #print("start initializeGL")
        if not self._initialized:
            add_opengl_context(ctx)
            self._initialized = True
        PINS.init.set()
        #print("end initializeGL")
        deactivate_opengl()

    def resizeGL(self, width, height):
        super().resizeGL(width, height)
        if self._destroyed:
            return
        GL.glViewport(0, 0, width, height)
        self.camera.width = width
        self.camera.height = height
        self.camera._write()
        self.update()

    def paintGL(self):
        activate_opengl()
        self._painting = True
        super().paintGL()
        if self._destroyed:
            return
        PINS.paint.set()
        PINS.painted.set()
        self._painting = False
        deactivate_opengl()

    def mousePressEvent(self, ev):
        self._mousePos = ev.pos()

    def mouseMoveEvent(self, ev):
        if self._mousePos is None:
            self._mousePos = ev.pos()
            return
        diff = ev.pos() - self._mousePos
        self._mousePos = ev.pos()

        if ev.buttons() == Qt.LeftButton:
            self.camera.orbit(-diff.x(), diff.y())
        elif ev.buttons() == Qt.MidButton:
            if (ev.modifiers() & Qt.ControlModifier):
                self.camera.pan(diff.x(), 0, diff.y(), relative=True)
            else:
                self.camera.pan(diff.x(), diff.y(), 0, relative=True)

    def keyPressEvent(self, event):
        key = int(event.key())
        k = None

        if key >= 32 and key <= 127:
            k = chr(key)
        else:
            for attr in dir(Qt):
                if not attr.startswith("Key_"):
                    continue
                code = getattr(Qt, attr)
                if code == key:
                    k = attr[4:]
                    break
        if k is None:
            return
        PINS.last_key.set(k)

    def destroy(self, *args, **kwargs):
        self._destroyed = True
        ctx = self.context()
        remove_opengl_context(ctx)
        super().destroy(*args, **kwargs)

    def update(self):
        #print("UPDATE")
        super().update()

widget = GLWidget()

def do_update():
    import threading
    assert threading.current_thread() is threading.main_thread()
    if widget._destroyed:
        return
    if PINS.camera.updated:
        widget.camera.load(PINS.camera.get())
    if PINS.update.updated:
        widget.update()
    if PINS.title.updated:
        widget.setWindowTitle(PINS.title.get())
    if PINS.geometry.updated:
        widget.setGeometry(*PINS.geometry.get())

do_update()
widget.setMouseTracking(True)
widget.show()
