from . import RegistrarObject, BaseRegistrar

class SilkRegistrarObject(RegistrarObject):

    def unregister(self):
        from seamless import silk
        silk.unregister(self.registered)
        self.registrar._unregister(self.data, self.data_name)

    def re_register(self, silkcode):
        context = self.context
        if context is None:
            return self
        self.unregister()
        from seamless import silk
        registered_types = silk.register(silkcode)
        updated_keys = [k for k in registered_types]
        updated_keys += [k for k in self.registered if k not in updated_keys]
        updated_keys2 = []
        updated_keys2 += updated_keys
        for ar in 1,2,3:
            for k in updated_keys:
                updated_keys2.append(k + ar * "Array")
        #TODO: figure out dependent types and add them
        self.registered = registered_types
        self.registrar.update(context, updated_keys2)
        self.registrar._register(self.data,self.data_name)
        super().re_register(silkcode)
        return self

class SilkRegistrar(BaseRegistrar):
    #TODO: setting up private Silk namespaces for subcontexts
    _register_type = ("text", "code", "silk")
    _registrar_object_class = SilkRegistrarObject

    #@macro(type=("text", "code", "silk"), with_context=False,_registrar=True)
    def register(self,silkcode, name=None):
        self._register(silkcode,name)
        from seamless import silk
        registered_types = silk.register(silkcode)
        return self._registrar_object_class(self, registered_types, silkcode, name)

    def get(self, key):
        from seamless.silk import Silk
        try:
            return getattr(Silk, key)
        except AttributeError:
            raise KeyError(key)
