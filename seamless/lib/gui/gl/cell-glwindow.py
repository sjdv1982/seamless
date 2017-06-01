from seamless.qt.QtWidgets import QOpenGLWidget
from seamless import add_opengl_context, remove_opengl_context
from OpenGL import GL

class GLWidget(QOpenGLWidget):
    _initialized = False
    _destroyed = False
    def initializeGL(self):
        super().initializeGL()
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

    def resizeGL(self, width, height):
        super().resizeGL(width, height)
        if self._destroyed:
            return
        GL.glViewport(0, 0, width, height)

    def paintGL(self):
        self._painting = True
        self._updating = False
        super().paintGL()
        if self._destroyed:
            return
        #print("start paintGL")
        PINS.paint.set()
        #print("end paintGL")
        self._painting = False
        if self._updating:
            self.update()

    def destroy(self, *args, **kwargs):
        self._destroyed = True
        ctx = self.context()
        remove_opengl_context(ctx)
        super().destroy(*args, **kwargs)

widget = GLWidget()

#def on_resize(*args, **kwargs):
#    print("on_resize", args, kwargs)

def do_update():
    import threading
    assert threading.current_thread() is threading.main_thread()
    if widget._destroyed:
        return
    if PINS.update.updated and not widget._painting:
        # ... Check for widget._painting:
        #   This seems to solve the Heisenbug in cell-program.py,
        #    see also test-gl-BUG.py
        # Still requires run_qt, else there are freezes
        widget.update()
    if PINS.title.updated:
        widget.setWindowTitle(PINS.title.get())
    if PINS.geometry.updated:
        widget.setGeometry(*PINS.geometry.get())

do_update()
widget.show()
