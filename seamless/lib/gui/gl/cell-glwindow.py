from seamless.qt.QtWidgets import QOpenGLWidget
from seamless import add_opengl_context, remove_opengl_context
from OpenGL import GL

class GLWidget(QOpenGLWidget):
    _initialized = False
    _destroyed = False
    def initializeGL(self):
        if self._destroyed:
            return
        from PyQt5.QtGui import QOpenGLContext
        print("INIT")
        ctx = self.context()
        assert ctx is QOpenGLContext.currentContext()
        #print("start initializeGL")
        if not self._initialized:
            add_opengl_context(ctx)
            self._initialized = True
        PINS.init.set()
        #print("end initializeGL")

    def resizeGL(self, width, height):
        if self._destroyed:
            return
        GL.glViewport(0, 0, width, height)

    def paintGL(self):
        if self._destroyed:
            return
        #print("start paintGL")
        PINS.paint.set()
        #print("end paintGL")

    def destroy(self, *args, **kwargs):
        self._destroyed = True
        ctx = self.context()
        remove_opengl_context(ctx)
        super().destroy(*args, **kwargs)

widget = GLWidget()

#def on_resize(*args, **kwargs):
#    print("on_resize", args, kwargs)

def do_update():
    if PINS.update.updated:
        widget.update()
    if PINS.title.updated:
        widget.setWindowTitle(PINS.title.get())
    if PINS.geometry.updated:
        widget.setGeometry(*PINS.geometry.get())

do_update()
widget.show()
