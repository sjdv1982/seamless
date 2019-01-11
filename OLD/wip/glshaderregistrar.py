from seamless.core.registrar import BaseRegistrar, RegistrarObject
class GLShaderRegistrarObject(RegistrarObject):

    def __init__(self, registrar, registered, data, data_name):
        super().__init__(registrar, registered, data, data_name)
        self._bound = False
        self._shader_id = None
        self._parse(data)

    @property
    def shader_id(self):
        return self._shader_id

    def unregister(self):
        self.destroy()
        namespace = self.registrar._namespace
        t = self.data_name
        if t in namespace:
            del namespace[t]

        self.registrar._unregister(self.data, t)

    def re_register(self, gl_shader):
        self.destroy()
        self._parse(gl_shader)
        super().re_register(gl_shader)
        return self

    def _parse(self, gl_shader):
        #TODO: STUB!
        self.gl_shader = gl_shader

    def bind(self):
        from .. import opengl
        if self._bound:
            return

        self._bound = True

    def destroy():
        from .. import opengl
        if self._destroyed:
            return
        if self._bound and opengl():
            pass #TODO: clean up shaders
        super().destroy()

class GLShaderRegistrar(BaseRegistrar):
    _register_type = "json"
    _registrar_object_class = GLShaderRegistrarObject
    def register(self, gl_shader):
        name = gl_shader["name"]
        shader_obj = self._registrar_object_class(self, [name], gl_shader, name)
        self._namespace[name] = shader_obj
        return shader_obj
