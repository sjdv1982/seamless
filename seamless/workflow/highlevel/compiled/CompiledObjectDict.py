import weakref
from copy import deepcopy
from .CompiledObjectWrapper import CompiledObjectWrapper
Transformer = None

module_attrs = "compiler_verbose", "target", "link_options", "headers"

class CompiledObjectDict:
    def __init__(self, worker):
        global Transformer
        if Transformer is None:
            from ..Transformer import Transformer
        object.__setattr__(self,"_worker", weakref.ref(worker))

    @property
    def headers(self):
        worker = self._worker()
        if not worker._has_tf():
            temp = worker._get_htf().get("TEMP", {})
            if "_main_module" not in temp:
                return None
            return temp["_main_module"].get("headers")
        else:
            tf = worker._get_tf()
            headers_cell = getattr(tf, "main_module_headers_CELL")
            return headers_cell.value

    def _set_headers(self, value):
        worker = self._worker()
        parent = worker._parent()
        target_path = worker._path + ("_main_module", "headers",)
        if isinstance(value, Cell):
            from ..assign import assign_connection
            assert value._parent() == parent
            #TODO: check existing inchannel connections and links (cannot be the same or higher)
            exempt = worker._exempt()
            assign_connection(parent, value._path, target_path, False, exempt=exempt)
            parent._translate()
        else:
            if isinstance(value, Resource):
                value = value.data
            if not worker._has_tf():
                htf = worker._get_htf()
                temp = htf.get("TEMP")
                if temp is None:
                    temp = {}
                    htf["TEMP"] = temp
                if "_main_module" not in temp:
                    temp["_main_module"] = {}
                main_module = temp["_main_module"]
                main_module["headers"] = value
                parent._translate()
            else:
                tf = worker._get_tf()
                headers_cell = getattr(tf, "main_module_headers_CELL")
                headers_cell.set(value)

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
        elif attr == "link_options":
            return worker.link_options
        elif attr in module_attrs:
            htf = worker._get_htf()
            main_module = htf.get("main_module")
            if main_module is None:
                return None
            return main_module.get(attr)

        return CompiledObjectWrapper(self._worker(), attr)

    def __setattr__(self, attr, value):
        worker = self._worker()
        if attr == "link_options":
            return setattr(worker, "link_options", value)
        if attr == "headers":
            return self._set_headers(value)
        if attr in module_attrs:
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
            return list(temp["_main_module"].keys()) + list(module_attrs)
        else:
            tf = worker._get_tf()
            main_module = getattr(tf, "main_module")
            main_module_data = main_module.data
            if "objects" in main_module_data:
                return list(main_module_data["objects"].keys()) + list(module_attrs)
            else:
                return module_attrs

    def __delattr__(self, attr):
        raise NotImplementedError

from ...highlevel.Cell import Cell, Resource