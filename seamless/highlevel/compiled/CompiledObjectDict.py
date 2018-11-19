import weakref
from .CompiledObjectWrapper import CompiledObjectWrapper

class CompiledObjectDict:
    def __init__(self, worker):
        object.__setattr__(self,"_worker", weakref.ref(worker))

    def __getattr__(self, attr):
        worker = self._worker()
        if attr == "value":
            if not worker._has_tf():
                temp = worker._get_htf().get("TEMP")
                if temp is not None and "_main_module" in temp:
                    main_module = temp["_main_module"]
                    if "value" not in main_module:
                        return main_module
            else:
                tf = worker._get_tf(may_translate=False)
                main_module = getattr(tf, "main_module")
                main_module_data = main_module.data.value
                if main_module_data is not None and "objects" in main_module_data:
                    objects = main_module_data["objects"]
                    if "value" not in objects:
                        return objects
        return CompiledObjectWrapper(self._worker(), attr)

    def __setattr__(self, attr, value):
        raise TypeError("Cannot assign directly an entire module object; assign individual elements")

    def __dir__(self):
        worker = self._worker()
        if not worker._has_tf():
            temp = worker._get_htf().get("TEMP", {})
            if temp is not None and "_main_module" not in temp:
                return []
            return temp["_main_module"].keys()
        else:
            tf = worker._get_tf(may_translate=False)
            main_module = getattr(tf, "main_module")
            main_module_data = main_module.data.value
            return main_module_data.keys()

    def __delattr__(self, attr):
        raise NotImplementedError
