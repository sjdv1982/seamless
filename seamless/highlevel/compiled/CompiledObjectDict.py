import weakref
from copy import deepcopy
from .CompiledObjectWrapper import CompiledObjectWrapper
Transformer = None

class CompiledObjectDict:
    def __init__(self, worker):
        global Transformer
        if Transformer is None:
            from ..Transformer import Transformer
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
                tf = worker._get_tf()
                main_module = getattr(tf, "main_module")
                main_module_data = main_module.handle.data
                if main_module_data is not None:
                    if "objects" in main_module_data:
                        objects = main_module_data["objects"]
                        if "value" in objects:
                            return CompiledObjectWrapper(self._worker(), attr)
                    return deepcopy(main_module.handle.data)
            return None
        elif attr == "compiler_verbose":
            htf = worker._get_htf()
            main_module = htf.get("main_module")
            if main_module is None:
                return None
            return main_module.get("compiler_verbose")

        return CompiledObjectWrapper(self._worker(), attr)

    def __setattr__(self, attr, value):
        worker = self._worker()
        if attr == "compiler_verbose":
            assert isinstance(worker, Transformer)
            if worker._get_tf() is None:
                htf = worker._get_htf()
                temp = htf.get("TEMP")
                if temp is None:
                    temp = {}
                    htf["TEMP"] = temp
                if "_main_module" not in temp:
                    temp["_main_module"] = {}
                temp["_main_module"][attr] = value
            else:
                tf = worker._get_tf()
                main_module = getattr(tf, "main_module")
                handle = main_module.handle
                if handle.data is None:
                    handle.set({})
                handle[attr] = value
        else:
            raise TypeError("Cannot assign directly an entire module object; assign individual elements")
        worker._parent()._translate()

    def __dir__(self):
        worker = self._worker()
        if not worker._has_tf():
            temp = worker._get_htf().get("TEMP", {})
            if temp is not None and "_main_module" not in temp:
                return []
            return list(temp["_main_module"].keys()) + ["compiler_verbose"]
        else:
            tf = worker._get_tf()
            main_module = getattr(tf, "main_module")
            main_module_data = main_module.data.value
            if "objects" in main_module_data:
                return list(main_module_data["objects"].keys()) + ["compiler_verbose"]

    def __delattr__(self, attr):
        raise NotImplementedError