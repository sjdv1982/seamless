class ConnectionWrapper:
    def __init__(self, basepath):
        self.basepath = basepath
        self.connections = []
    def connect(self, source, target, source_subpath, target_subpath):
        if isinstance(source, InputCellWrapper):
            #assert source_subpath is None
            source_full_path = source.path
        else:
            source_full_path = self.basepath + source._path
        if source_subpath is not None:
            if isinstance(source_subpath, str):
                source_subpath = (source_subpath,)
            source_full_path += tuple(source_subpath)

        if isinstance(target, OutputCellWrapper):
            #assert target_subpath is None
            target.clear()
            target_full_path = target.path
        else:
            if not isinstance(target, Cell):
                raise TypeError(type(target))
            if target_subpath is None:
                target._get_hcell().pop("checksum", None)
            target_full_path = self.basepath + target._path
        if target_subpath is not None:
            if isinstance(target_subpath, str):
                target_subpath = (target_subpath,)
            target_full_path += tuple(target_subpath)
        connection = {
            "type": "connection",
            "source": source_full_path,
            "target": target_full_path,
        }
        self.connections.append(connection)

class CellWrapper:
    @property
    def celltype(self):
        hcell = self._node
        return hcell["celltype"]

    @property
    def mimetype(self):
        hcell = self._node
        mimetype = hcell.get("mimetype")
        if mimetype is not None:
            return mimetype
        celltype = hcell["celltype"]
        if celltype == "code":
            language = hcell["language"]
            mimetype = language_to_mime(language)
            return mimetype
        if celltype == "structured":
            datatype = hcell["datatype"]
            if datatype in ("mixed", "binary"):
                mimetype = get_mime(datatype)
            else:
                mimetype = ext_to_mime(datatype)
        else:
            mimetype = get_mime(celltype)
        return mimetype

    @property
    def datatype(self):
        hcell = self._node
        celltype = hcell["celltype"]
        assert celltype == "structured"
        return hcell["datatype"]

    @property
    def language(self):
        hcell = self._node
        celltype = hcell["celltype"]
        if celltype != "code":
            raise AttributeError

    @property
    def hash_pattern(self):
        hcell = self._node
        celltype = hcell["celltype"]
        assert celltype in ("structured", "mixed")
        return hcell["hash_pattern"]

class InputCellWrapper(CellWrapper):
    def __init__(self, connection_wrapper, cell):
        self._connection_wrapper = connection_wrapper
        self._cell = cell
        self._node = cell._get_hcell()
    def connect(self, target, source_path=None, target_path=None):        
        self._connection_wrapper.connect(
            self,
            target,
            source_path,
            target_path
        )
    @property
    def path(self):
        return self._cell._path

class OutputCellWrapper(CellWrapper):
    def __init__(self, connection_wrapper, node, path):
        self._connection_wrapper = connection_wrapper
        self._node = node
        self._path = path
    
    @property
    def path(self):
        return self._path

    def connect_from(self, source, source_path=None, target_path=None):
        self._connection_wrapper.connect(
            source,
            self,
            source_path,
            target_path
        )

    def clear(self):
        self._node["checksum"] = None

    @CellWrapper.celltype.setter
    def celltype(self, value):
        assert value in celltypes, value
        hcell = self._node
        self.clear()
        hcell["celltype"] = value
        if value in ("structured", "mixed"):
            if "hash_pattern" not in hcell:
                hcell["hash_pattern"] = None
        else:
            hcell.pop("hash_pattern", None)



    @CellWrapper.mimetype.setter
    def mimetype(self, value):
        hcell = self._node
        if value.find("/") == -1:
            try:
                ext = value
                value = ext_to_mime(ext)
            except KeyError:
                raise ValueError("Unknown extension %s" % ext) from None
            hcell["file_extension"] = ext
        hcell["mimetype"] = value


    @CellWrapper.datatype.setter
    def datatype(self, value):
        hcell = self._node
        celltype = hcell["celltype"]
        assert celltype == "structured"
        hcell["datatype"] = value

    @CellWrapper.hash_pattern.setter
    def hash_pattern(self, value):
        from ...core.protocol.deep_structure import validate_hash_pattern
        validate_hash_pattern(value)
        hcell = self._node
        celltype = hcell["celltype"]
        assert celltype in ("structured", "mixed")
        hcell["hash_pattern"] = value
        hcell.pop("checksum", None)

    @CellWrapper.language.setter
    def language(self, value):
        from ...compiler import find_language
        hcell = self._node
        celltype = hcell["celltype"]
        if celltype != "code":
            return self._setattr("language", value)
        lang, language, extension = find_language(value)
        old_language = hcell.get("language")
        hcell["language"] = lang
        hcell["file_extension"] = extension

    def mount(self, path=None, mode="rw", authority="cell", persistent=True):
        assert self.celltype != "structured"
        hcell = self._node
        if path is None:
            hcell.pop("mount", None)
        else:
            mount = {
                "path": path,
                "mode": mode,
                "authority": authority,
                "persistent": persistent
            }
            hcell["mount"] = mount

    def add_validator(self, *args, **kwargs):
        raise NotImplementedError("You must connect to the schema...")

    @property
    def schema(self):
        raise NotImplementedError ### TODO: support connections to the schema

    @schema.setter
    def schema(self):
        raise NotImplementedError ### TODO: support connections to the schema

from ..Cell import Cell, celltypes
from ...mime import get_mime, ext_to_mime, language_to_mime, language_to_ext