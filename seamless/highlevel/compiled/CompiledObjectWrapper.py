import weakref, functools

from ..proxy import Proxy, CodeProxy
from ..Cell import Cell
from ..Resource import Resource
from ...mime import language_to_mime

properties = [
    "language", "code", "extension", "compiler", "target",
    "options", "profile_options", "debug_options", 
    "headers"
]

class CompiledObjectWrapper:
    def __init__(self, worker, obj):
        self._worker = weakref.ref(worker)
        self._obj = obj

    @property
    def _path(self):
        return self._worker()._path + ("_main_module" , self._obj)

    def __setattr__(self, attr, value):
        if attr in ("_worker", "_obj"):
            return object.__setattr__(self, attr, value)
        if attr not in properties:
            raise AttributeError
        worker = self._worker()
        parent = worker._parent()
        target_path = worker._path + ("_main_module", self._obj, attr)
        if isinstance(value, Cell):
            from ..assign import assign_connection
            assert value._parent() == parent
            #TODO: check existing inchannel connections and links (cannot be the same or higher)
            exempt = worker._exempt()
            assign_connection(parent, value._path, target_path, False, exempt=exempt)
            parent._translate()
        else:
            objname = self._obj
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
                if "objects" not in main_module:
                    main_module["objects"] = {}
                if objname not in main_module["objects"]:
                    main_module["objects"][objname] = {}
                main_module["objects"][objname][attr] = value
                parent._translate()
            else:
                tf = worker._get_tf()
                main_module = getattr(tf, "main_module")
                handle = main_module.handle
                if handle.data is None:
                    handle.set({"objects":{}})
                if "objects" not in handle:
                    handle["objects"] = {}
                if objname not in handle["objects"]:
                    handle["objects"][objname] = {"code": ""}
                handle["objects"][objname][attr] = value
                parent._translate()

    def __getattr__(self, attr):
        if attr not in properties:
            raise AttributeError(attr)
        worker = self._worker()
        pull_source = None
        if attr == "code":
            getter = self._codegetter
            dirs = ["value", "mount", "mimetype"]
            pull_source = self._pull_source
            proxycls = CodeProxy
        else:
            getter = functools.partial(self._valuegetter, attr)
            dirs = ["value"]
            proxycls = Proxy
        return proxycls(self, (attr,), "r", pull_source=pull_source, getter=getter, dirs=dirs)

    def _codegetter(self, attr):
        if attr == "value":
            return self._get_value("code")
        elif attr == "mount":
            raise NotImplementedError #maybe it should never...
        elif attr == "mimetype":
            language = self._get_value("language")
            if language is None:
                return None
            mimetype = language_to_mime(language)
            return mimetype
        else:
            raise AttributeError(attr)

    def _valuegetter(self, attr, attr2):
        if attr2 != "value":
            raise AttributeError(attr2)
        return self._get_value(attr)

    def _get_value(self, attr):
        if attr not in properties:
            raise AttributeError(attr)
        worker = self._worker()
        if not worker._has_tf():
            temp = worker._get_htf().get("TEMP", {})
            if "_main_module" not in temp:
                return None
            data = temp["_main_module"].get(self._obj)
            if data is None:
                return None
            return data.get(attr)
        else:
            tf = worker._get_tf()
            main_module = getattr(tf, "main_module")
            main_module = getattr(tf, "main_module")
            handle = main_module.handle
            if handle.data is None:
                return None
            if "objects" not in handle:
                return None
            if self._obj not in handle["objects"]:
                return None
            obj = handle["objects"][self._obj]
            return obj.get(attr)

    def _pull_source(self, path):
        from ..assign import assign_connection
        from ..Transformer import Transformer
        from ...compiler import find_language
        worker = self._worker()
        parent = worker._parent()

        new_path = path
        target_path = worker._path + ("_main_module", self._obj, "code")
        language = None
        if isinstance(worker, Transformer):
            m = getattr(worker.main_module,self._obj)
            if m is not None:
                language = m.language.value
        if language is None:
            language = self._get_value("language")
        if language is None:
            print("%s: cannot detect language, default to c." % str(target_path))
            language = "c"
        file_extension = self._get_value("extension")
        if file_extension is None:
            _, _, file_extension = parent.environment.find_language(language)
        value = self._get_value("code")
        cell = {
            "path": new_path,
            "type": "cell",
            "celltype": "code",
            "language": language,
            "file_extension": file_extension,
            "transformer": True,
            "UNTRANSLATED": True,
        }
        if value is not None:
            assert isinstance(value, str), type(value)
            setattr(self, "code", value)
        child = Cell(parent=parent, path=new_path) #inserts itself as child
        parent._graph[0][new_path] = cell
        mimetype = language_to_mime(language)
        child.mimetype = mimetype
        assign_connection(parent, new_path, target_path, False)
        self._delattr("code")
        parent._translate()


    def _delattr(self, attr):
        worker = self._worker()
        if not worker._has_tf():
            htf = worker._get_htf()
            temp = htf.get("TEMP")
            if temp is not None:
                if "_main_module" in temp:
                    main_module = temp["_main_module"]
                    objname = self._obj
                    if objname in main_module:
                        return main_module[objname].pop(attr, None)
        else:
            tf = worker._get_tf()
            main_module = getattr(tf, "main_module")
            main_module_handle = main_module.handle
            main_module_data = main_module.data
            if main_module_data is not None:
                objname = self._obj
                if objname in main_module_data:
                    return main_module_handle[objname].pop(attr, None)

    def __delattr__(self, attr):
        return self._delattr(attr)

    def __dir__(self):
        worker = self._worker()
        if not worker._has_tf():
            temp = worker._get_htf().get("TEMP", {})
            if "_main_module" not in temp:
                return []
            if self._obj not in temp["_main_module"]:
                return []
        else:
            tf = worker._get_tf()
            main_module = getattr(tf, "main_module")
            main_module_data = main_module.data
            if "objects" not in main_module_data:
                return []
            if self._obj not in main_module_data["objects"]:
                return []
        return properties
