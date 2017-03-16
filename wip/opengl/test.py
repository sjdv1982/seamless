import numpy as np
from OpenGL.arrays import vbo
from OpenGL.GL import shaders
from OpenGL.GL import *
from OpenGL import GL as gl

from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QOpenGLWidget, QSlider,
        QWidget)


from GLStore import GLStore, GLSubStore
from Renderer import Renderer, VertexAttribute

vertex_code = """
    uniform float scale;
    attribute vec4 color;
    attribute vec2 position;
    varying vec4 v_color;
    void main()
    {
        gl_Position = vec4(scale*position, 0.0, 1.0);
        v_color = color;
    } """

fragment_code = """
    varying vec4 v_color;
    void main()
    {
        gl_FragColor = v_color;
    } """

class GLWidget(QOpenGLWidget):

    def __init__(self, parent, init_callback, paint_callback):
        assert callable(init_callback)
        assert callable(paint_callback)
        self.init_callback = init_callback
        self.paint_callback = paint_callback
        super().__init__(parent)

    def initializeGL(self):
        self.init_callback()
        # Build data
        self.data = np.zeros(4, [("position", np.float32, 2),
                                 ("color",    np.float32, 4)])
        self.data['color'] = [(1, 0, 0, 1), (0, 1, 0, 1),
                              (0, 0, 1, 1), (1, 1, 0, 1)]
        self.data['position'] = [(-1, -1), (-1, +1),
                                 (+1, -1), (+1, +1)]

        vertex_shader = shaders.compileShader(vertex_code, GL_VERTEX_SHADER)

        fragment_shader = shaders.compileShader(fragment_code, GL_FRAGMENT_SHADER)

        self.program = shaders.compileProgram(vertex_shader, fragment_shader)
        shaders.glUseProgram(self.program)

        class dummy:
            pass
        d = dummy(); d.data = self.data
        self.d1 = d
        store = GLStore(d)
        store.bind()

        mapping = {
            "command": "triangle_strip",
            "attributes": {
                "position": {
                    "dtype": "vec2",
                    "array": "default",
                    "rae": "['position'][:]",
                },
                "color": {
                    "dtype": "vec4",
                    "array": "default",
                    "rae": "['color'][:]",
                },
            }
        }
        self.storedict = {"default": store}
        print(self.storedict["default"].parent().data)

        #
        indices = np.array((1,2,3,0,1,2),dtype=np.uint16)
        d=dummy(); d.data = indices
        self.d2 = d
        self.storedict["indices"] = GLStore(d)
        self.storedict["indices"].bind()
        print(self.storedict["indices"].parent().data)
        mapping["indices"] = {
                            "dtype": "short",
                            "array": "indices",
                        }
        mapping["command"] = "triangles_indexed"

        #
        self.renderer = Renderer(mapping, self.program, self.storedict)
        print(self.storedict["indices"].parent().data)
        print(self.storedict["default"].parent().data)
        self.renderer.bind()

        # Bind uniforms
        # --------------------------------------
        self.loc_scale = gl.glGetUniformLocation(self.program, "scale")

    def resizeGL(self, width, height):
        glViewport(0, 0, width, height)

    def paintGL(self):
        self.paint_callback()
        #glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glEnable(GL_BLEND)
        glDisable(GL_DEPTH_TEST)
        glClear(GL_COLOR_BUFFER_BIT)
        gl.glUniform1f(self.loc_scale, 1.0)
        self.renderer.draw()

if __name__ == '__main__':

    from seamless import silk
    silk.register("""
    Type Vec4 {
        Float x
        Float y
        Float z
        Float w
    }
    """)
    Vec4Array = silk.Silk.Vec4Array
    a = Vec4Array((1,2,3,4),(5,6,7,9))
    aa = a.numpy()

    import sys
    app = QApplication(sys.argv)
    window = GLWidget(None, lambda: None, lambda: None)
    window.show()
    sys.exit(app.exec_())
