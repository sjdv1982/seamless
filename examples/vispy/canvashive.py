from weakref import ref
import hive
from vispy import gloo, app
from seamless.silk import Silk

class HiveCls_Canvas(app.Canvas):
    def __init__(self, *args, **kwargs):
        self._program = None
        self._hive = ref(hive.get_run_hive())
        self._hive()._canvas = ref(self)
        app.Canvas.__init__(self,*args, **kwargs)

        # Enable blending
        gloo.set_state(blend=True, clear_color='black',
                       blend_func=('src_alpha', 'one'))

        gloo.set_viewport(0, 0, self.physical_size[0], self.physical_size[1])
        self._timer = app.Timer('auto', connect=self.update, start=True)

    def create_program(
            self,
            vert_shader, frag_shader, vertexbuffer, texture_dict
    ):
        """Creates gloo program
        vert_shader: GLSL code for vertex shader
        frag_shader: GLSL code for fragment shader
        vertexbuffer: Vertex buffer in Silk or Numpy format
        texture_dict: a dict of (texture name, 2D Numpy array) pairs
        """
        first = (self._program is None)
        if not first:
            self.show(visible=False)
        self._program = gloo.Program(vert_shader, frag_shader)
        if isinstance(vertexbuffer, Silk.SilkObject):
            vertexbuffer = vertexbuffer.make_numpy()
        self._program.bind(gloo.VertexBuffer(vertexbuffer))
        for texname, tex in texture_dict.items():
            self._program[texname] = gloo.Texture2D(tex)
        self.show(visible=True)

    def on_resize(self, event):
        width, height = event.physical_size
        gloo.set_viewport(0, 0, width, height)

    def on_draw(self, event):
        gloo.clear()
        self._hive().draw()

def build_canvashive(cls, i, ex, args):
    i.draw = hive.triggerfunc()

    ex.v_vert_shader = hive.attribute(start_value=None)
    ex.v_frag_shader = hive.attribute(start_value=None)
    ex.v_vertexbuffer = hive.attribute(start_value=None)
    ex.v_texture_dict = hive.attribute(start_value=None)
    ex.program = hive.property(cls, "_program")
    ex.title = hive.property(cls, "title")

    def create_program(self):
        if self.v_vert_shader is None or \
           self.v_frag_shader is None or \
           self.v_vertexbuffer is None or \
           self.v_texture_dict is None:
            self._canvas().show(visible=False)
            return
        self._canvas().create_program(
            self.v_vert_shader,
            self.v_frag_shader,
            self.v_vertexbuffer,
            self.v_texture_dict
        )
        self.program_rebuilt()

    i.create_program = hive.modifier(create_program)

    i.vert_shader_in = hive.push_in(ex.v_vert_shader)
    ex.vert_shader = hive.antenna(i.vert_shader_in)
    hive.trigger(i.vert_shader_in, i.create_program)

    i.frag_shader_in = hive.push_in(ex.v_frag_shader)
    ex.frag_shader = hive.antenna(i.frag_shader_in)
    hive.trigger(i.frag_shader_in, i.create_program)

    i.vertexbuffer_in = hive.push_in(ex.v_vertexbuffer)
    ex.vertexbuffer = hive.antenna(i.vertexbuffer_in)
    hive.trigger(i.vertexbuffer_in, i.create_program)

    i.texture_dict_in = hive.push_in(ex.v_texture_dict)
    ex.texture_dict = hive.antenna(i.texture_dict_in)
    hive.trigger(i.texture_dict_in, i.create_program)

    ex.draw = hive.hook(i.draw)
    i.program_rebuilt = hive.triggerfunc()
    ex.program_rebuilt = hive.hook(i.program_rebuilt)

CanvasHive = hive.hive("CanvasHive", build_canvashive, HiveCls_Canvas)
