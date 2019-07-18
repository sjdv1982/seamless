# NOTE: no more unstable. Equilibrate returns when eventloop is empty.
import weakref

class Manager:
    _destroyed = False
    _active = True
    _authority_mode = True # authoritative paths may be modified
    flushing = False
    def __init__(self, ctx):
        from . import (ValueManager, StatusManager, AuthorityManager, 
         LiveGraph, JobManager)
        assert ctx._toplevel
        self.ctx = weakref.ref(ctx)

        from ..events import EventLoop
        self.eventloop = EventLoop(self)
        # keep the eventloop flushing (flushloop? see below....)

        # for now, just a single global mountmanager
        from ..mount import mountmanager
        self.mountmanager = mountmanager

        # adapt it to use the API correctly
        self.values = ValueManager(self)
        self.staatus = StatusManager(self) # TODO livegraph branch: change to "status" once refactor complete
        self.authority = AuthorityManager(self)
        self.livegraph = LiveGraph(self)
        self.jobs = JobManager(self)
        
    ##########################################################################
    # API section I: Registration (divide among subsystems)
    ##########################################################################

    def register_cell(self, cell):
        raise NotImplementedError # livegraph branch
        ccache = self.cell_cache
        ###
        raise NotImplementedError # livegraph branch; delegate to authority manager. 
          # For StructuredCell, decide for outchannels based on inchannels (don't use connections!!!). 
          # In all cases, assigning a value to a non-auth outchannel is an error!
        
        ccache.cell_to_authority[cell] = {None: True} # upon registration, all cells are authoritative
        ###
        ccache.cell_to_accessors[cell] = {None : []}
        self.status[cell] = {None: Status("cell")}

    def register_cell_paths(self, cell, inpaths, outedpaths):
        self.authority.register_cell_paths(cell, inpaths, outedpaths)
        raise NotImplementedError # livegraph branch
        # Previous args: (self, cell, paths, has_auth) (has_auth=True for outedpaths)
        ccache = self.cell_cache        
        for path in paths:
            ccache.cell_to_authority[cell][path] = has_auth
            ccache.cell_to_accessors[cell][path] = []
            self.status[cell][path] = Status("cell")

    def register_transformer(self, transformer):
        raise NotImplementedError # livegraph branch
        
        
        raise NotImplementedError 
        # Generate transformer init event.
        # If a transformer has all of its inputs AND its output defined:
        # - Add it to the transform cache
        # - Add it to the provenance cache    

        tcache = self.transform_cache
        tcache.transformer_to_level0[transformer] = {}
        tcache.transformer_to_cells[transformer] = []
        self.status[transformer] = Status("transformer")

    def register_reactor(self, reactor):
        raise NotImplementedError # livegraph branch

        self.reactors[reactor] = RuntimeReactor(self, reactor)
        self.status[reactor] = Status("reactor")

    def register_macro(self, macro):
        raise NotImplementedError # livegraph branch
        self.status[macro] = Status("macro")


    ##########################################################################
    # API section II: Connection (divide among subsystems))
    ##########################################################################
    
    # TODO: update authority system upon connection!

    def _verify_connect(self, source, target):
        raise NotImplementedError # livegraph branch

        # TODO: make sure that buffer cells never have any connections!
        # TODO: cell should have _unconnected property that describes this...

        from .macro import Path
        assert source._get_manager() is self, source._get_manager()
        assert source._root() is target._root()
        source_macro = source._get_macro()
        target_macro = target._get_macro()
        current_macro = curr_macro()
        if source_macro is not None or target_macro is not None:
            if current_macro is not None:
                if not source_macro._context()._part_of2(current_macro._context()):
                    msg = "%s is not part of current %s"
                    raise Exception(msg % (source_macro, current_macro))
                if not target_macro._context()._part_of2(current_macro._context()):
                    msg = "%s is not part of current %s"
                    raise Exception(msg % (target_macro, current_macro))
        path_source = (source_macro is not current_macro or isinstance(source, Path))
        path_target = (target_macro is not current_macro or isinstance(target, Path))
        if path_source and path_target:
            msg = "Neither %s (governing %s) nor %s (governing %s) was created by current macro %s"
            raise Exception(msg % (source_macro, source, target_macro, target, current_macro))
        return path_source, path_target

    def _connect_cell_transformer(self, cell, pin, cell_subpath):
        """Connects cell to transformer inputpin"""
        raise NotImplementedError # livegraph branch
        #print("connect cell transformer", cell, pin, cell)
        transformer = pin.worker_ref()
        tcache = self.transform_cache
        accessor_dict = tcache.transformer_to_level0[transformer]
        assert pin.name not in accessor_dict, pin #double connection
        io, access_mode, content_type = (
            pin.io,  pin.access_mode, pin.content_type
        )
        if pin.transfer_mode == "module":
            access_mode = "module"
            content_type = "plain"

        if io == "input":
            pass
        elif io == "output":
            raise TypeError(pin) #outputpin, cannot connect a cell to that...
        else:
            raise TypeError(pin)

        accessor = self.get_default_accessor(cell)
        acc = None
        if cell_subpath is not None:
            accessor.subpath = cell_subpath
            acc = accessor
        if access_mode is not None and access_mode != accessor.access_mode:
            accessor.source_access_mode = accessor.access_mode
            accessor.access_mode = access_mode
            acc = accessor
        if content_type is not None and content_type != accessor.content_type:
            accessor.source_content_type = accessor.content_type
            accessor.content_type = content_type
            acc = accessor
        if cell_subpath is not None:
            ccache = self.cell_cache
            if cell_subpath not in ccache.cell_to_accessors[cell]:
                ccache.cell_to_accessors[cell][cell_subpath] = []
            ccache.cell_to_accessors[cell][cell_subpath].append(acc)
        acache = self.accessor_cache
        haccessor = hash(accessor)
        if haccessor not in acache.haccessor_to_workers:
            acache.haccessor_to_workers[haccessor] = [(transformer, acc)]
        else:
            acache.haccessor_to_workers[haccessor].append((transformer, acc))
        accessor_dict[pin.name] = accessor
        self.update_transformer_status(transformer,full=False)

    def _connect_reactor(self, pin, cell, inout, cell_subpath):
        """Connects cell to/from reactor pin"""
        raise NotImplementedError # livegraph branch
        current_upstream = self.cell_cache.cell_from_upstream.get(cell)

        reactor = pin.worker_ref()
        rtreactor = self.reactors[reactor]        
        io, access_mode, content_type = (
            pin.io,  pin.access_mode, pin.content_type
        )
        if pin.transfer_mode == "module":
            access_mode = "module"
            content_type = "plain"

        if io == "input":
            if not inout == "in":
                raise TypeError(pin) # input pin must be the target
        elif io == "edit":
            pass # pin.connect(cell) and cell.connect(pin) are equivalent
        elif io == "output":
            if inout == "in":
                raise TypeError(pin) # output pin cannot be the target
        else:
            raise TypeError(pin)
        
        if io == "edit":
            if pin.name in rtreactor.edit_dict:
                raise TypeError(pin) #Edit pin can connect to only one cell
            current_upstream = self.cell_cache.cell_from_upstream.get(cell)
            if current_upstream is None:
                current_upstream = {}
                self.cell_cache.cell_from_upstream[cell] = current_upstream
            current_upstream2 = current_upstream.get(cell_subpath)
            if current_upstream2 is None:
                current_upstream2 = []
                current_upstream[cell_subpath] = current_upstream2
            if not isinstance(current_upstream2, list):
                raise TypeError("Cell %s is already connected to %s" % (cell, current_upstream2))
            current_upstream2.append(pin)
            rtreactor.edit_dict[pin.name] = (cell,cell_subpath)
        elif inout == "in":
            assert pin.name not in rtreactor.input_dict, pin #double connection
            accessor = self.get_default_accessor(cell)
            acc = None
            if cell_subpath is not None:
                accessor.subpath = cell_subpath
                acc = accessor
            if access_mode is not None and access_mode != accessor.access_mode:
                accessor.source_access_mode = accessor.access_mode
                accessor.access_mode = access_mode
                acc = accessor
            if content_type is not None and content_type != accessor.content_type:
                accessor.source_content_type = accessor.content_type
                accessor.content_type = content_type
                acc = accessor
            acache = self.accessor_cache
            haccessor = hash(accessor)
            if haccessor not in acache.haccessor_to_workers:
                acache.haccessor_to_workers[haccessor] = [(reactor,acc)]
            else:
                acache.haccessor_to_workers[haccessor].append((reactor,acc))
            rtreactor.input_dict[pin.name] = accessor
        elif inout == "out":
            current_upstream = self.cell_cache.cell_from_upstream.get(cell)
            if current_upstream is None:
                current_upstream = {}
                self.cell_cache.cell_from_upstream[cell] = current_upstream
            current_upstream2 = current_upstream.get(cell_subpath)
            if current_upstream2 is not None:
                raise TypeError("%s is already connected from %s" % (cell, current_upstream2))
            current_upstream[cell_subpath] = pin
            output_dict = rtreactor.output_dict
            if not pin.name in output_dict:
                output_dict[pin.name] = []
            output_dict[pin.name].append((cell, cell_subpath))
        else:
            raise ValueError(inout)

        for pinname, pin in reactor._pins.items():
            if pin.io == "input":
                io_dict = rtreactor.input_dict
            elif pin.io == "output":
                io_dict = rtreactor.output_dict
            elif pin.io == "edit":
                io_dict = rtreactor.edit_dict
            if pinname not in io_dict:
                break
        else:
            rtreactor.live = False
            rtreactor.updated = set(reactor._pins.keys())
            self.update_reactor_status(reactor, full=True)


    def _connect_cell_macro(self, cell, pin, cell_subpath):
        """Connects cell to macro pin"""
        raise NotImplementedError # livegraph branch
        macro = pin.worker_ref()
        io, access_mode, content_type = (
            pin.io,  pin.access_mode, pin.content_type
        )
        if pin.transfer_mode == "module":
            access_mode = "module"
            content_type = "plain"

        if io != "input":
            raise TypeError(pin) # input pin must be the target

        assert pin.name not in macro.input_dict, pin #double connection
        accessor = self.get_default_accessor(cell)
        acc = None
        if cell_subpath is not None:
            accessor.subpath = cell_subpath
            acc = accessor
        if access_mode is not None and access_mode != accessor.access_mode:
            accessor.source_access_mode = accessor.access_mode
            accessor.access_mode = access_mode
            acc = accessor
        if content_type is not None and content_type != accessor.content_type:
            accessor.source_content_type = accessor.content_type
            accessor.content_type = content_type
            acc = accessor
        acache = self.accessor_cache
        haccessor = hash(accessor)
        if haccessor not in acache.haccessor_to_workers:
            acache.haccessor_to_workers[haccessor] = [(macro,acc)]
        else:
            acache.haccessor_to_workers[haccessor].append((macro,acc))
        macro.input_dict[pin.name] = accessor

        for pinname, pin in macro._pins.items():
            if pinname not in macro.input_dict:
                break
        else:
            self.update_macro_status(macro)

    def _find_cell_to_cell(self, cell_or_path, subpath):
        # Find to which other cells a cell or path connects
        # inefficient (linear-time) lookup, to be improved
        # Results are returned as accessors
        raise NotImplementedError # livegraph branch
        from .macro import Path
        if isinstance(cell_or_path, Path):
            cell = _cell
            if cell is None:
                return []
        else:
            cell = cell_or_path
        accessors = []
        for source_accessor, target_accessor in self.cell_to_cell:
            ok = False
            if isinstance(source_accessor, tuple):
                path, s_subpath = source_accessor
                assert isinstance(path, Path)
                if path._cell is cell and s_subpath == subpath:
                    accessor = self.get_default_accessor(cell)
                    accessor.subpath = subpath
                    ok = True
            else:
                if source_accessor.cell is cell:
                    if source_accessor.subpath == subpath:
                        ok = True
            if not ok:
                continue
            if isinstance(target_accessor, tuple):
                path, t_subpath = target_accessor
                assert isinstance(path, Path)
                if path._cell is None:
                    continue
                    target_accessor = self.get_default_accessor(path._cell)
                    target_accessor.subpath = t_subpath
            accessors.append(target_accessor)
        return accessors

    def _find_cell_from_cell(self, cell_or_path, subpath):
        # Find which other cell connects to a cell or path
        # inefficient (linear-time) lookup, to be improved
        # Result is returned as an accessor
        raise NotImplementedError # livegraph branch
        from .macro import Path
        if isinstance(cell_or_path, Path):
            if not cell_or_path._incoming:
                return None
            return cell_or_path._cell
        cell = cell_or_path
        for source_accessor, target_accessor in self.cell_to_cell:
            ok = False
            if isinstance(target_accessor, tuple):
                path, t_subpath = target_accessor
                assert isinstance(path, Path)
                if path._cell is cell and t_subpath == subpath:
                    target_accessor = self.get_default_accessor(cell)
                    target_accessor.subpath = subpath
                    ok = True
            elif target_accessor.cell is cell and target_accessor.subpath == subpath:
                ok = True
            if not ok:
                continue
            if isinstance(source_accessor, tuple):
                path, s_subpath = source_accessor
                assert isinstance(path, Path)
                if path._cell is None:
                    return None
                accessor = self.get_default_accessor(path._cell)
                accessor.subpath = s_subpath
                return accessor
            else:
                return source_accessor
        return None

    def _cell_upstream(self, cell, subpath, skip_path=None):
        # Returns the upstream dependency of a cell
        raise NotImplementedError # livegraph branch
        from .cell import Cell
        result = None
        while 1:
            if isinstance(cell, Cell):
                for path in cell._paths:
                    if path is skip_path:
                        continue
                    result0 = self._find_cell_from_cell(path, subpath)
                    if result0 is not None:
                        if result is not None:
                            warn("%s: multiple incoming bound paths have been bound; should not be possible!!" % cell)
                            break
                        result = result0
                if result is not None:
                    break
            result = self._find_cell_from_cell(cell, subpath)
            if result is not None:
                break
            result = self.cell_cache.cell_from_upstream.get(cell)
            if result is not None:
                result = result.get(subpath)
            break
        return result

    def _connect_cell_cell(self, source, target, source_subpath, target_subpath):
        raise NotImplementedError # livegraph branch
        from .macro import Path, create_path
        from .cell import Cell
        ispath_source, ispath_target = self._verify_connect(source, target)     
        current_upstream = self._cell_upstream(target, target_subpath)
        if current_upstream is not None:
            raise TypeError("Cell %s is already connected to %s" % (target, current_upstream))            

        connection = []
        accessors = []
        for cell, ispath_cell, subpath in \
          (source, ispath_source, source_subpath), (target, ispath_target, target_subpath):
            if isinstance(cell, Cell):
                if cell._celltype == "structured": 
                    raise TypeError
                accessor = self.get_default_accessor(cell)
                accessor.subpath = subpath
            else:
                assert isinstance(cell, Path)
                assert ispath_cell, (cell, ispath_cell)
                accessor = None
            if ispath_cell:
                path = create_path(cell)
                if cell is target:
                    assert not path._incoming, cell
                    path._incoming = True
                connect = (path, subpath)
            else:
                connect = accessor
            connection.append(connect)
            if accessor is not None:
                accessors.append(accessor)
        self.cell_to_cell.append(connection)
        if len(accessors) == 2:
            self.update_accessor_accessor(*accessors, only_if_defined=True)

    def connect_cell(self, cell, other, cell_subpath):
        #print("connect_cell", cell, other, cell_subpath)
        raise NotImplementedError # livegraph branch
        from . import Transformer, Reactor, Macro
        from .link import Link
        from .cell import Cell
        from .worker import PinBase, EditPin
        from .macro import Path
        from .structured_cell import Inchannel
        if isinstance(cell, Link):
            cell = cell.get_linked()
        if not isinstance(cell, (Cell, Path)):
            raise TypeError(cell)
        if isinstance(other, Link):
            other = other.get_linked()

        other_subpath = None
        if isinstance(other, Inchannel):
            other_subpath = other.name
            other = other.structured_cell().data      

        if isinstance(other, (Cell, Path)):
            self._connect_cell_cell(cell, other, cell_subpath, other_subpath)
        elif isinstance(other, PinBase):
            path_cell, path_other = self._verify_connect(cell, other)            
            if path_other:
                msg = str(other) + ": macro-generated pins/paths may not be connected outside the macro"
                raise Exception(msg)
            if path_cell:
                msg = str(cell) + ": macro-generated cells/paths may only be connected to cells, not %s"
                raise Exception(msg % other)                
            worker = other.worker_ref()
            if isinstance(worker, Transformer):
                self._connect_cell_transformer(cell, other, cell_subpath)
            elif isinstance(worker, Reactor):
                mode = "edit" if isinstance(other, EditPin) else "in"
                self._connect_reactor(other, cell, mode, cell_subpath)
            elif isinstance(worker, Macro):
                self._connect_cell_macro(cell, other, cell_subpath)
            else:
                raise TypeError(type(worker))
        else:
            raise TypeError(type(other))
        self.schedule_jobs()

    def cell_from_pin(self, pin):
        raise NotImplementedError # livegraph branch
        from . import Transformer, Reactor, Macro
        from .worker import InputPin, OutputPin, EditPin
        worker = pin.worker_ref()
        if worker is None:
            raise ValueError("Worker has died")
        if isinstance(worker, Transformer):            
            if isinstance(pin, InputPin):
                accessor_dict = self.transform_cache.transformer_to_level0[worker]
                return accessor_dict.get(pin.name)
            elif isinstance(pin, OutputPin):
                return self.transform_cache.transformer_to_cells.get(worker, [])
            else:
                raise TypeError(pin)
        elif isinstance(worker, Reactor):
            rt_reactor = self.reactors[worker]
            if isinstance(pin, InputPin):
                accessor = rt_reactor.input_dict.get(pin.name)
                if accessor is None:
                    return None
                else:
                    return accessor.cell, accessor.subpath
            elif isinstance(pin, EditPin):
                return rt_reactor.edit_dict.get(pin.name)
            elif isinstance(pin, OutputPin):
                return rt_reactor.output_dict.get(pin.name, [])
            else:
                raise TypeError(pin)
        elif isinstance(worker, Macro):
            accessor = worker.input_dict.get(pin, None)
            if accessor is None:
                return None
            else:
                return accessor.cell, accessor.subpath
        else:
            raise TypeError(worker)


    def connect_pin(self, pin, cell):
        raise NotImplementedError # livegraph branch
        #print("connect_pin", pin, cell)
        from . import Transformer, Reactor, Macro
        from .link import Link
        from .cell import Cell
        from .macro import Path
        from .structured_cell import Inchannel
        from .worker import PinBase, InputPin, OutputPin, EditPin
        cell_subpath = None
        if isinstance(cell, Link):
            cell = cell.get_linked()
        cell_subpath = None
        if isinstance(cell, Inchannel):
            cell_subpath = cell.name
            cell = cell.structured_cell().data
        if not isinstance(cell, (Cell, Path)):
            raise TypeError(cell)
        if not isinstance(pin, PinBase) or isinstance(pin, InputPin):
            raise TypeError(pin)

        path_pin, path_cell = self._verify_connect(pin, cell)
        if path_pin:
            msg = str(pin) + ": macro-generated pins may not be connected outside the macro"
            raise Exception(msg)

        worker = pin.worker_ref()
        if isinstance(worker, Transformer):
            tcache = self.transform_cache
            tcache.transformer_to_cells[worker].append((cell, cell_subpath))
            level1 = tcache.transformer_to_level1.get(worker)
            if level1 is not None:
                hlevel1 = level1.get_hash()
                checksum = tcache.get_result(hlevel1)
                if checksum is not None:
                    if cell_subpath is not None: raise NotImplementedError ###see update_accessor_accessor
                    self.set_cell_checksum(cell, checksum)
            self.update_transformer_status(worker,full=False, new_connection=True)
        elif isinstance(worker, Reactor):
            mode = "edit" if isinstance(pin, EditPin) else "out"
            self._connect_reactor(pin, cell, mode, cell_subpath)
        else:
            raise TypeError(worker)
        self.schedule_jobs()

    ##########################################################################
    # API section III: Set cell values
    ##########################################################################

    # TODO: 
    # - setting by checksum is an immediate passthrough
    # - all others create an event, and wait for it (because setting a cell value is blocking)
    # TODO: "updated paths" notification from Monitor structuredcell backend should go here as well
    # TODO: auth/non-auth mode

    def set_cell_checksum(self, cell, checksum, status=None):
        raise NotImplementedError # livegraph branch
        # TODO: 
        # - Ditch status argument
        # - Insert an event, and wait for it
        # - NO CHECK that cell is authoritative! (assumed that you know what you are doing)
        from .macro_mode import macro_mode_on, get_macro_mode
        from .mount import is_dummy_mount
        assert cell._get_manager() is self
        ccache = self.cell_cache
        old_checksum = ccache.cell_to_buffer_checksums.get(cell)
        vcache = self.value_cache
        if checksum != old_checksum:
            ccache.cell_to_buffer_checksums[cell] = checksum
            if old_checksum is not None:
                vcache.decref(old_checksum, has_auth=has_auth)
            # We don't know the buffer value, but we don't need to
            # an incref will take place anyway, possibly on a dummy item
            # The result value will tell us if the buffer value is known
            buffer_known = vcache.incref(checksum, buffer=None, has_auth=has_auth)
            share_callback = cell._share_callback
            if share_callback is not None:
                share_callback()
            if buffer_known and not is_dummy_mount(cell._mount):
                if not get_macro_mode():
                    self.mountmanager.add_cell_update(cell)            
            if cell._observer is not None:
                cell._observer(checksum.hex())
            for traitlet in cell._traitlets:
                traitlet.receive_update(checksum.hex())
            #if cell._monitor is None:
            self._update_status(
                cell, (checksum is not None), 
                origin=None, cell_subpath=None
            )

    def set_cell(self, cell, value, *, subpath,
      from_buffer=False, origin=None, buffer_checksum=None,
      ):
        raise NotImplementedError # livegraph branch
        
        # "origin" indicates the worker that generated the .set_cell call
        # TODO: get rid of origin?
        # TODO: auth/non-auth mode (see LIVEGRAPH-TODO.txt)

        # TODO: 
        # - Insert an event, and wait for it
        # - CHECK that cell is authoritative for that path! 

        if value is None:
            raise NotImplementedError # update!
            return
        from .macro_mode import macro_mode_on, get_macro_mode
        from .mount import is_dummy_mount
        assert cell._get_manager() is self
        assert buffer_checksum is None or from_buffer == True        
        ccache = self.cell_cache
        auth = ccache.cell_to_authority[cell][subpath]
        has_auth = (auth != False)     
        if subpath is not None: 
            raise NotImplementedError ### deep cells

        old_checksum = ccache.cell_to_buffer_checksums.get(cell)
        result = deserialize(
            cell._celltype, cell._subcelltype, cell.path,
            value, from_buffer=from_buffer, buffer_checksum=buffer_checksum,
            source_access_mode=None,
            source_content_type=None
        )
        buffer, checksum, obj, semantic_obj, semantic_checksum = result
        vcache = self.value_cache
        semantic_key = SemanticKey(
            semantic_checksum,
            cell._default_access_mode,
            None
        )
        if checksum != old_checksum:
            ccache.cell_to_buffer_checksums[cell] = checksum
            if old_checksum is not None:
                vcache.decref(old_checksum, has_auth=has_auth)
            vcache.incref(checksum, buffer, has_auth=has_auth)
            vcache.add_semantic_key(semantic_key, semantic_obj)
            accessor = self.get_default_accessor(cell)
            accessor.subpath = subpath
            expression = accessor.to_expression(checksum)
            self.expression_cache.expression_to_semantic_key[expression.get_hash()] = semantic_key
            share_callback = cell._share_callback
            if share_callback is not None:
                share_callback()
            if subpath is None and not is_dummy_mount(cell._mount):
                if not get_macro_mode() and origin is not cell._context():
                    self.mountmanager.add_cell_update(cell)
            if cell._observer is not None:
                cell._observer(checksum.hex())
            for traitlet in cell._traitlets:
                traitlet.receive_update(checksum.hex())
            self._update_status(
              cell, (checksum is not None), 
              cell_subpath=subpath, has_auth=has_auth, origin=origin
            )
        else:
            # Just refresh the semantic key timeout
            vcache.add_semantic_key(semantic_key, semantic_obj)

    def set_cell_label(self, cell, label):
        raise NotImplementedError # livegraph branch
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)
        if checksum is None:
            raise ValueError("cell is undefined")
        self.label_cache.set(label, checksum)

    def set_cell_from_label(self, cell, label, subpath):
        if subpath is not None: raise NotImplementedError ###deep cells
        checksum = self.get_checksum_from_label(label)
        if checksum is None:
            raise Exception("Label has no checksum")
        return self.set_cell_checksum(cell, checksum)

    def verify_modified_paths(self, cell, modified_paths):
        return self.authority.verify_modified_paths(cell, modified_paths, self._authority_mode)

    ##########################################################################
    # API section IV: Get cell values
    ##########################################################################

    def get_cell_label(self, cell):
        raise NotImplementedError # livegraph branch
        # TODO: passthrough to .livegraph?
        checksum = self.cell_cache.cell_to_buffer_checksums.get(cell)
        if checksum is None:
            return None
        return self.label_cache.get_label(checksum)

    def get_checksum_from_label(self, label):
        return self.values.get_checksum_from_label(label)

    def get_value_from_checksum(self, checksum):
        raise NotImplementedError #livegraph branch
        # This one is tricky; best to call values.get_value_from_checksum_async as an event, and wait for it

    ##########################################################################
    # API section V: Set worker results (passthrough)
    ##########################################################################

    def set_transformation_undefined(self, level1):
        return self.jobs.set_transformation_undefined(level1)

    def set_reactor_result(self, rtreactor, pinname, value):
        return self.livegraph.set_reactor_result(rtreactor, pinname, value)

    def set_reactor_exception(self, rtreactor, codename, exception):
        return self.livegraph.set_reactor_exception(rtreactor, codename, exception)

    def set_macro_exception(self, macro, exception):
        return self.livegraph.set_macro_exception(macro, exception)

    def set_transformation_result(self, level1, level2, value, checksum, prelim):
        return self.jobs.set_transformation_result(level1, level2, value, checksum, prelim)

    def set_transformation_stream_result(self, tf, k):
        return self.jobs.set_transformation_stream_result(self, tf, k)

    def set_transformation_result_exception(self, level1, level2, exception):
        return self.jobs.set_transformation_result_exception(level1, level2, exception)

    def set_transformation_undefined(self, level1):
        return self.jobs.set_transformation_undefined(level1)

    ### TODO: insert equilibration API section (see below)

    ##########################################################################
    # API section VII: Destruction
    ##########################################################################

    def _destroy_cell(self, cell):
        self.authority.destroy_cell(cell)
        raise NotImplementedError # livegraph branch
        ccache = self.cell_cache
        ccache.cell_to_accessors.pop(cell, None)
        ccache.cell_to_buffer_checksums.pop(cell, None)
        ccache.cell_from_upstream.pop(cell, None)

        for item in list(self.cell_to_cell):
            source, target = item
            destroy = False
            if isinstance(source, Accessor) and source.cell is cell:
                destroy = True
            if isinstance(target, Accessor) and target.cell is cell:
                destroy = True
            if destroy:
                self.cell_to_cell.remove(item)

    def _destroy_worker(self, worker):
        raise NotImplementedError # livegraph branch
        cache = self.accessor_cache.haccessor_to_workers        
        for k,v in cache.items():
            v[:] = [vv for vv in v if vv[0] is not worker]
    

    def _destroy_transformer(self, transformer):
        raise NotImplementedError # livegraph branch
        self._destroy_worker(transformer)
        tcache = self.transform_cache
        tcache.transformer_to_level0.pop(transformer)
        levels1 = []
        level1 = tcache.transformer_to_level1.pop(transformer, None)
        if level1 is not None:
            levels1.append(level1)
        levels1a = tcache.stream_transformer_to_levels1.pop(transformer, None)
        if levels1a is not None:
            levels1.extend(levels1a.values())
        for level1 in levels1:
            hlevel1 = level1.get_hash()
            tcache.decref(level1)
            tf = tcache.transformer_from_hlevel1.pop(hlevel1, None)
            if tf is not transformer:
                tcache.transformer_from_hlevel1[hlevel1] = tf
            else:
                # restore transformer_from_hlevel1 to an alternative tf
                #TODO: use reverse cache
                for tf, tf_level1 in tcache.transformer_to_level1.items():
                    if tf_level1.get_hash() == hlevel1:
                        tcache.transformer_from_hlevel1[hlevel1] = tf
                        break
        tcache.transformer_to_cells.pop(transformer, None)
        self.unstable.discard(transformer)

    def _destroy_macro(self, macro):        
        """destroys macro and its generated context
        NOTE: it is NOT necessary to destroy macro._paths or filter cell-cell connections
        Reasons:
        - Paths under macro control (i.e. non-global paths) are always expanded to cells first
          So from a manager perspective, they do not really exist
           and the cell is destroyed together with the macro.
        - Global paths do exist at a cell-cell connection level (and as upstreams)
          but they are never destroyed.
        - The third kind of paths is those constructed on the direction of verify_connect
          This involves connections into paths, whose target is controlled by a different macro.
          The other end of the connection MUST be under the control of the current macro;
           this is a requirement of verify_connect
          Therefore, the other end is also destroyed at the same time, and this will clean up
           the connection as well (self._destroy_cell).          
        """
        raise NotImplementedError # livegraph branch
        if macro._unbound_gen_context is not None:
            macro._unbound_gen_context.destroy()
        if macro._gen_context is not None:
            macro._gen_context.destroy()
        self._destroy_worker(macro)

    def _destroy_reactor(self, reactor):
        self._destroy_worker(macro)

    def destroy(self, from_del=False):
        raise NotImplementedError # livegraph branch
        if self._destroyed:
            return
        self._destroyed = True
        self.temprefmanager_future.cancel()
        self.flush_future.cancel()

    def __del__(self):
        self.destroy(from_del=True)



"""
##########################################################################
# API section VI: Equilibration
##########################################################################

# REQUIRES COMPLETE OVERHAUL
    self.flush_future = asyncio.ensure_future(self._flushloop())

    async def _flush(self):
        self.flushing = True
        try:
            async for dummy in self.eventloop.flush():
                pass
        finally:
            self.flushing = False

    async def _flushloop(self):
        while 1:
            try:
                await self._flush()
            except:
                import traceback
                traceback.print_exc()
            await asyncio.sleep(0)

    async def equilibrate(self, timeout, report, path):
        await self.mountmanager.async_tick()
        await self._flush()
        delta = None
        if timeout is not None:
            deadline = time.time() + timeout
        lpath = len(path)
        def get_unstable():
            return {w for w in self.unstable if w.path[:lpath] == path}
        while 1:
            unstable = get_unstable()
            if not len(unstable):
                break
            if timeout is not None:
                remain = deadline - time.time()
                if remain <= 0:
                    break
                if delta is None or remain < delta:
                    delta = remain
            if report is not None:
                if delta is None or report < delta:
                    delta = report
            cache_jobs = []
            for k,v in self.cache_task_manager.tasks.items():
                cache_jobs.append(v.future)
            if len(cache_jobs):
                if delta is None:
                    await asyncio.gather(*cache_jobs)
                else:
                    await asyncio.wait(cache_jobs, timeout=delta)                    
                if delta is not None:
                    continue
            self.jobscheduler.cleanup()
            unstable = get_unstable()
            if not len(unstable):
                break
            jobs = []
            for job in itertools.chain(
                  self.jobscheduler.jobs.values(),
                  self.jobscheduler.remote_jobs.values(),                  
                ):
                jobs.append(job.future)
                                    
            if not len(jobs):
                tasks = list(self.cache_task_manager.tasks.values())
                if not len(tasks):
                    raise Exception("No jobs, but unstable workers: %s" % unstable)
                asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED, timeout=delta)
                continue
            if delta is None:
                await asyncio.gather(*jobs)
            else:
                await asyncio.wait(jobs, timeout=delta)
                if report is not None:
                    unstable = get_unstable()                    
                    if len(unstable):
                        unstable = sorted(unstable,key=lambda w:w.path)
                        print("Waiting for:", unstable)
        return self.unstable

"""

'''
# DO WE NEED THIS?

    def get_id(self):
        self._ids += 1
        return self._ids


    def value_get(self, checksum):
        """For communion server"""
        value = self.value_cache.get_buffer(checksum)
        if value is None:
            return None
        return value[2]

from . import library
'''