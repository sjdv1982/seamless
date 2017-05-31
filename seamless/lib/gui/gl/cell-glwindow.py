from seamless.qt.QtWidgets import QOpenGLWidget
from seamless import add_opengl_context, remove_opengl_context
from OpenGL import GL

class GLWidget(QOpenGLWidget):
    _initialized = False
    def initializeGL(self):
        #print("start initializeGL")
        if not self._initialized:
            add_opengl_context(self)
            self._initialized = True
        PINS.init.set()
        #print("end initializeGL")

    def resizeGL(self, width, height):
        GL.glViewport(0, 0, width, height)

    def paintGL(self):
        #print("start paintGL")
        PINS.paint.set()
        #print("end paintGL")

    def destroy(self, *args, **kwargs):
        remove_opengl_context(self)
        super().destroy(*args, **kwargs)

widget = GLWidget()

def on_resize(*args, **kwargs):
    print("on_resize", args, kwargs)

def do_update():
    if PINS.update.updated:
        widget.update()
    if PINS.title.updated:
        widget.setWindowTitle(PINS.title.get())
    if PINS.geometry.updated:
        widget.setGeometry(*PINS.geometry.get())

do_update()
widget.show()
