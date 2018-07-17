import functools
import weakref

use_caching = True

@functools.lru_cache(10000)
def _long_signature_cell(cell, root):
    if isinstance(cell, (Inchannel, Outchannel)):
        return None #uncachable for now
    result = {}
    mgr = cell._get_manager()
    from_pin = mgr.cell_from_pin.get(cell)
    if from_pin is not None:
        from_pin = from_pin[1]
    from_cell = mgr.cell_from_cell.get(cell)
    if from_cell is not None:
        from_cell = from_cell[1]
    if from_pin is not None:
        worker = from_pin.worker_ref()
        if worker._context()._part_of(root):
            assert isinstance(worker, Transformer) #TODO: reactors
            #TODO: for reactors, also indicate which outputpin; discount editpins
            result["origin"] = "transformer"
            result["dependency"] = _long_signature_transformer(worker, root)
        else:
            result["origin"] = "extern"
            result["path"] = from_pin.path
    elif from_cell is not None:
        if from_cell._context()._part_of(root):
            result["origin"] = "cell"
            result["dependency"] = _long_signature_cell(from_cell, root)
        else:
            result["origin"] = "extern"
            result["path"] = from_cell.path
    else: #source cell
        if cell.status() == "OK":
            result["origin"] = "self"
            result["checksum"] = cell.checksum()
            #TODO: sometimes it is the text checksum we are interested in
            # Depends on the nature of the downstream connection
            # So we would have separate versions of the long_signature of this cell
        else:
            result["origin"] = "none"
    return result

@functools.lru_cache(10000)
def _long_signature_transformer(tf, root):
    result = {}
    mgr = tf._get_manager()
    for pinname, pin in tf._pins.items():
        if not isinstance(pin, InputPinBase):
            continue
        from_cell = mgr.pin_from_cell.get(pin)
        if from_cell is not None:
            from_cell = from_cell[1]
        subresult = {}
        if from_cell is not None:
            ctx = from_cell._context()
            if ctx._part_of(root):
                subresult["origin"] = "cell"
                subresult["dependency"] = _long_signature_cell(from_cell, root)
            else:
                subresult["origin"] = "extern"
                subresult["path"] = from_cell.path
        else:
            subresult["origin"] = "none"
        result[pinname] = subresult
    return result

def long_signature(obj, root):
    """Calculates the long signature of a cell or worker
    It takes into account the direct and indirect upstream dependencies
    Dependencies above root are considered as extern (and their path is stored)"""
    if isinstance(obj, Cell):
        return _long_signature_cell(obj, root)
    elif isinstance(obj, Transformer):
        return _long_signature_transformer(obj, root)
    else:
        raise TypeError()

def _short_signature_cell(cell):
    if isinstance(cell, (Inchannel, Outchannel)):
        return None #TODO
    if cell.status() == "OK":
        return cell.checksum()
        #TODO: sometimes it is the text checksum we are interested in
        # Depends on the nature of the downstream connection
        # So we would have separate versions of the short_signature of this cell
    else:
        return None

def _short_signature_transformer(tf):
    if tf.status() != "OK":
        return None
    result = {}
    mgr = tf._get_manager()
    for pinname, pin in tf._pins.items():
        if not isinstance(pin, InputPinBase):
            continue
        from_cell = mgr.pin_from_cell.get(pin)
        if from_cell is not None:
            from_cell = from_cell[1]
        subresult = _short_signature_cell(from_cell)
        ###assert subresult is not None #if status is OK, no connected cell can be None; WRONG in case of channels!
        result[pinname] = subresult
    return result

def short_signature(obj):
    """Calculates the short signature of a cell or worker
    It takes into account the direct upstream dependencies
    Source or non-source is not a factor, nor is extern/non-extern
    If any of them is None, the short signature is None as well"""
    if isinstance(obj, Cell):
        return _short_signature_cell(obj)
    elif isinstance(obj, Transformer):
        return _short_signature_transformer(obj)
    else:
        raise TypeError()

def _do_cache(new_obj, old_obj, hits):
    if isinstance(new_obj, Cell):
        assert isinstance(old_obj, Cell)
        new_obj._val = old_obj._val
        new_obj._last_checksum = old_obj._last_checksum
        new_obj._last_text_checksum = old_obj._last_text_checksum
        new_obj._exception = old_obj._exception
        new_obj._prelim_val = old_obj._prelim_val
        new_obj._authoritative = old_obj._authoritative
        new_obj._overruled = old_obj._overruled
        old_obj._val = None
        hits["cells"][new_obj] = old_obj
    elif isinstance(new_obj, Transformer):
        assert isinstance(old_obj, Transformer)
        t = old_obj.transformer
        #TODO: thread-safe lock mechanism to modify t atomically
        t.parent = weakref.ref(new_obj)
        t.send_message("@RESTART", None)
        t.output_queue = new_obj.output_queue
        t.output_semaphore = new_obj.output_semaphore
        old_obj.output_thread.join() #happens quickly after @RESTART signal
        new_obj._listen_output_state = old_obj._listen_output_state
        new_obj.transformer = t
        new_obj.transformer_thread = old_obj.transformer_thread
        new_obj._pending_updates = old_obj._pending_updates
        new_obj._last_value = old_obj._last_value
        new_obj._last_value_preliminary = old_obj._last_value_preliminary
        new_obj._message_id = old_obj._message_id
        assert not new_obj.active
        new_obj._last_update_checksums = old_obj._last_update_checksums.copy()
        old_obj.active = False
        old_obj.transformer = None
        old_obj.transformer_thread = None
        old_obj.destroy()
        hits["transformers"][new_obj] = old_obj
    else:
        raise TypeError(new_obj)


def _cache(obj, root, old_paths, hits):
    path = obj.path
    long_sig = long_signature(obj, root)
    if path in old_paths and old_paths[path][0] == long_sig:
        #print("cache hit by preservation", obj)
        p = old_paths.pop(path)
        return _do_cache(obj, p[2], hits)
    for old_path in list(old_paths.keys()):
        p = old_paths[old_path]
        if p[0] == long_sig:
            #print("cache hit by long signature", obj, old_path)
            old_paths.pop(old_path)
            return _do_cache(obj, p[2], hits)
    short_sig = short_signature(obj)
    if short_sig is not None:
        for old_path in list(old_paths.keys()):
            p = old_paths[old_path]
            if p[1] == short_sig:
                #print("cache hit by short signature", obj, old_path)
                old_paths.pop(old_path)
                return _do_cache(obj, p[2], hits)
    #print("cache miss", obj)

def cache(ctx, old_ctx):
    hits = {"transformers": {}, "cells": {}}
    if not use_caching:
        return hits
    old_paths = {}
    def build_paths(c):
        for child in c._children.values():
            if isinstance(child, Context):
                build_paths(child)
            elif isinstance(child, (Cell, Transformer)): #TODO: reactors
                if isinstance(child, (Inchannel, Outchannel)):
                    continue
                path = child.path
                long_sig = long_signature(child, old_ctx)
                short_sig = short_signature(child)
                old_paths[path] = long_sig, short_sig, child
    build_paths(old_ctx)
    def walk(c):
        for child in c._children.values():
            if isinstance(child, Context):
                walk(child)
            elif isinstance(child, (Cell, Transformer)): #TODO: reactors
                _cache(child, ctx, old_paths, hits)
    walk(ctx)
    return hits

from . import Context, Cell, Transformer #TODO: reactors
from .worker import InputPinBase
from .structured_cell import Inchannel, Outchannel

"""
Something to consider (long term): topology hits
  Macro caching can give a topology hit (if the macro code and macro args are the same).
  This is different from the current approach of value hits, which depend on the value of the connected cells)
  Topology hits may interfere with layers, but maybe they could be made to work
"""
