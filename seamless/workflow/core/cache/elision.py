"""Macro elision cache and routines
"""

import weakref
import json

elision_cache = {}

class Elision:
    def __init__(self, livegraph, macro, input_cells, output_cells):
        #print("ELISION", macro, input_cells, output_cells)
        old_elision = livegraph.macro_elision.get(macro)
        if old_elision is not None:
            old_elision.destroy()
        self.livegraph = weakref.ref(livegraph)
        input_cells2 = {}
        output_cells2 = {}
        mpath = macro.path
        mmacro = macro._get_macro()
        if mmacro is not None:
            mpath = mpath[len(mmacro.path)+1:]
        for cells, cells2 in [(input_cells, input_cells2),(output_cells, output_cells2)]:
            for c, p in cells.items():
                assert isinstance(c, Cell)
                assert isinstance(p, Path)
                assert p._macro is macro._get_macro(), (p._macro, macro)
                path0 = p._path
                assert path0[:len(mpath)] == mpath, (path0, macro, mpath)
                path = path0[len(mpath):]
                assert path[0] == "ctx", path0
                path = path[1:]
                cells2[c] = path

        livegraph.macro_elision[macro] = self
        for c in input_cells:
            if c not in livegraph.cell_to_macro_elision:
                livegraph.cell_to_macro_elision[c] = []
            livegraph.cell_to_macro_elision[c].append(self)
        for c in output_cells:
            if c in livegraph.cell_from_macro_elision:
                elision = livegraph.cell_from_macro_elision[c]
                elision.destroy()
            livegraph.cell_from_macro_elision[c] = self

        self.macro = macro
        self.input_cells = input_cells2
        self.output_cells = output_cells2


    def update(self):
        """Triggered if one of the output cells changes value"""
        from .database_client import database
        from . import buffer_remote
        from ..protocol.serialize import serialize_sync as serialize
        if self.macro._in_elision:
            return
        elision_checksum = self.get_elision_checksum()
        if elision_checksum is None:
            return
        elision_result = self.get_elision_result()
        if elision_result is None:
            return
        #print("ELISION UPDATE", self.macro, elision_checksum.hex(), elision_result)
        elision_result_buffer = serialize(elision_result, "plain")
        elision_result_checksum = calculate_checksum(elision_result_buffer)
        buffer_remote.write_buffer(elision_result_checksum, elision_result_buffer)
        database.set_elision_result(elision_checksum, elision_result_checksum)
        elision_cache[elision_checksum] = elision_result


    def get_elision_checksum(self):
        for c in list(self.input_cells.keys()) + list(self.output_cells.keys()):
            if c._prelim:
                return None
            if c._checksum is None and not c._void:
                return None
        elision_dict = {}
        elision_dict["params"] = {}
        for k,v in self.macro._last_inputs.items():
            if v is not None:
                v = v.hex()
            elision_dict["params"][k] = v
        elision_dict["input_cells"] = {}
        for c,p in self.input_cells.items():
            cs = c._checksum
            if cs is not None:
                cs = cs.hex()
            pp = json.dumps(tuple(p))
            elision_dict["input_cells"][pp] = cs
        elision_checksum = calculate_dict_checksum(elision_dict)
        #print("ELISION DICT", self.macro, elision_checksum.hex(), elision_dict)
        return elision_checksum


    def get_elision_result(self):
        cs = self.get_elision_checksum()
        if cs is None:
            return None
            
        elision_result = {}
        for c,p in self.output_cells.items():
            upstream = self.livegraph().cell_to_upstream[c]
            path = upstream.source
            cc = path._cell
            celltype = None
            hash_pattern = None
            if cc is None:
                checksum = None
            else:
                checksum = cc._checksum
                if checksum is None and not cc._void:
                    return
            if checksum is not None:
                celltype = cc._celltype
                if celltype == "mixed":
                    hash_pattern = cc._hash_pattern
            if checksum is not None:
                checksum = checksum.hex()
            pp = json.dumps(tuple(p))
            elision_result[pp] = celltype, hash_pattern, checksum
        # TODO: record pseudo-connections
        #print("ELISION-RESULT", elision_result)
        return elision_result


    def destroy(self):
        livegraph = self.livegraph()
        macro = self.macro
        if macro in livegraph.macro_elision:
            livegraph.macro_elision.pop(macro)
        for c in self.input_cells:
            if c in livegraph.cell_to_macro_elision \
              and self in livegraph.cell_to_macro_elision[c]:
                livegraph.cell_to_macro_elision[c].remove(self)
                if not len(livegraph.cell_to_macro_elision[c]):
                    livegraph.cell_to_macro_elision.pop(c)
        for c in self.output_cells:
            if c in livegraph.cell_from_macro_elision:
                livegraph.cell_from_macro_elision.pop(c)


def elide(macro: "Macro"):
    from .database_client import database
    from ..protocol.get_buffer import get_buffer
    from ..protocol.deserialize import deserialize_sync
    topmacro = macro._get_macro()
    if topmacro is None:
        topmacro = macro
    if not topmacro.allow_elision:
        #print("ELISION DISABLED", macro, topmacro)
        return False

    manager = macro._get_manager()
    livegraph = manager.livegraph
    elision = livegraph.macro_elision.get(macro)
    if elision is None:
        #print("NO ELISION", macro)
        return False

    elision_checksum = elision.get_elision_checksum()
    if elision_checksum is None:
        #print("CACHE MISS", macro)
        return False
    cache_hit = elision_cache.get(elision_checksum)
    if cache_hit is None:
        #print("CACHE MISS", macro, elision_checksum.hex())
        db_cache_hit = database.get_elision_result(elision_checksum)
        if db_cache_hit is None:
            #print("DB CACHE MISS", macro, elision_checksum.hex())
            return False
        else:
            #print("DB CACHE HIT?", macro, elision_checksum.hex())
            elision_result_buffer = get_buffer(db_cache_hit, remote=True)
            if elision_result_buffer is not None:
                #print("DB CACHE HIT!", macro, elision_checksum.hex())
                cache_hit = deserialize_sync(elision_result_buffer, db_cache_hit, "plain", copy=True)
                elision_cache[elision_checksum] = cache_hit
            else:
                return False
    else:
        #print("CACHE HIT", macro, elision_checksum.hex())
        pass

    elision_result = {}
    for p0,v in cache_hit.items():
        p = tuple(json.loads(p0))
        elision_result[p] = v

    for c,p in elision.output_cells.items():
        assert p in elision_result, p

    if macro._gen_context is not None:
        macro._gen_context.destroy()
        macro._gen_context = None
    def callback(ctx, namespace):
        for c,p in elision.output_cells.items():
            sub_celltype, sub_hash_pattern, sub_checksum = elision_result[p]
            sub = ctx
            for pp in p[:-1]:
                if not hasattr(sub, pp):
                    setattr(sub, pp, context(toplevel=False))
                sub = getattr(sub, pp)
            if sub_celltype == "mixed":
                cc = cell(sub_celltype, hash_pattern=sub_hash_pattern)
            else:
                cc = cell(sub_celltype)
            setattr(sub, p[-1], cc)
            cc.set_checksum(sub_checksum)
            # TODO: restore pseudo-connections
    macro._execute(callback, {}, [])
    return True

from ..macro import Macro, Path, path as make_path
from ..cell import Cell, cell
from ..context import context
