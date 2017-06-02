from seamless.qt.QtWidgets import QOpenGLWidget
from seamless import add_opengl_context, remove_opengl_context, \
 activate_opengl, deactivate_opengl
from OpenGL import GL

class GLWidget(QOpenGLWidget):
    _initialized = False
    _destroyed = False
    _painting = False
    _updating = False
    def initializeGL(self):
        super().initializeGL()
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

    def paintGL(self):
        activate_opengl()
        self._painting = True
        super().paintGL()
        if self._destroyed:
            return
        #print("start paintGL")
        PINS.paint.set()
        #print("DRAW")
        #print("end paintGL")
        #if self._updating:
        #    self.update()
        PINS.painted.set()
        self._painting = False
        deactivate_opengl()

    def destroy(self, *args, **kwargs):
        self._destroyed = True
        ctx = self.context()
        remove_opengl_context(ctx)
        super().destroy(*args, **kwargs)

    def update(self):
        #print("UPDATE")
        super().update()

widget = GLWidget()
#def on_resize(*args, **kwargs):
#    print("on_resize", args, kwargs)

def do_update():
    import threading
    assert threading.current_thread() is threading.main_thread()
    if widget._destroyed:
        return
    if PINS.update.updated:
        widget.update()
    if PINS.title.updated:
        widget.setWindowTitle(PINS.title.get())
    if PINS.geometry.updated:
        widget.setGeometry(*PINS.geometry.get())

do_update()
widget.show()
