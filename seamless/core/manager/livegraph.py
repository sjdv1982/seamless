import weakref
from ..status import StatusReasonEnum
from .. import destroyer

# NOTE: distinction between simple cells (no StructuredCell monitor), StructuredCell data cells, and StructuredCell buffer cells

class LiveGraph:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.accessor_to_upstream = {} # Mapping of read accessors to the cell or worker that defines it.
                                    # Mapping is a tuple (cell-or-worker, pinname), where pinname is None except for reactors.
        self.expression_to_accessors = {} # Mapping of expressions to the list of read accessors that resolve to it
        self.cell_to_upstream = {} # Mapping of simple cells to the read accessor that defines it.
        self.cell_to_downstream = {} # Mapping of simple cells to the read accessors that depend on it.
        self.cell_to_editpins = {}
        self.paths_to_upstream = {} # Mapping of buffercells-to-dictionary-of-path:upstream-write-accessor.
        self.paths_to_downstream = {} # Mapping of datacells-to-dictionary-of-path:list-of-downstream-read-accessors
        self.transformer_to_upstream = {} # input pin to read accessor
        self.transformer_to_downstream = {}
        self.reactor_to_upstream = {} # input pin to read accessor
        self.reactor_to_downstream = {} # Unlike all other X_to_downstream, this is a dict
        self.editpin_to_cell = {}
        self.macro_to_upstream = {} # input pin to read accessor
        self.macropath_to_upstream = {}
        self.macropath_to_downstream = {}        

        self.datacells = {}
        self.buffercells = {}
        self.schemacells = {} # cell-to-structuredcell to which it serves as schema; can be multiple

        self.rtreactors = {}

        self.temp_auth = weakref.WeakKeyDictionary()
        self._will_lose_authority = set()

        self._destroying = set()

    def register_cell(self, cell):
        assert cell._monitor is None # StructuredCells get registered later
        self.cell_to_upstream[cell] = None
        self.cell_to_downstream[cell] = []
        self.cell_to_editpins[cell] = []
        self.schemacells[cell] = []

    def register_transformer(self, transformer):
        inputpins = [pinname for pinname in transformer._pins \
            if transformer._pins[pinname].io == "input" ]
        upstream = {pinname:None for pinname in inputpins}
        self.transformer_to_upstream[transformer] = upstream
        self.transformer_to_downstream[transformer] = []

    def register_reactor(self, reactor):
        # Editpins are neither upstream nor downstream,
        #  but have a separate cell_to_editpins mapping
        manager = self.manager()
        inputpins = [pinname for pinname in reactor._pins \
            if reactor._pins[pinname].io == "input" ]
        outputpins = [pinname for pinname in reactor._pins \
            if reactor._pins[pinname].io == "output" ]
        editpins = [pinname for pinname in reactor._pins \
            if reactor._pins[pinname].io == "edit" ]
        upstream = {pinname:None for pinname in inputpins}
        self.reactor_to_upstream[reactor] = upstream
        downstream = {pinname:[] for pinname in outputpins}
        self.reactor_to_downstream[reactor] = downstream
        editpin_cell = {pinname:None for pinname in editpins}
        self.editpin_to_cell[reactor] = editpin_cell
        self.rtreactors[reactor] = RuntimeReactor(
            manager,
            reactor,
            inputpins, outputpins, editpins
        )


    def register_macro(self, macro):
        inputpins = [pinname for pinname in macro._pins]
        upstream = {pinname:None for pinname in inputpins}
        self.macro_to_upstream[macro] = upstream

    def register_structured_cell(self, structured_cell):
        buffercell = structured_cell.buffer
        assert buffercell in self.cell_to_upstream
        assert self.cell_to_upstream[buffercell] is None
        assert not len(self.cell_to_downstream[buffercell])

        datacell = structured_cell.data
        assert buffercell is not datacell
        assert datacell in self.cell_to_upstream
        assert self.cell_to_upstream[datacell] is None
        assert not len(self.cell_to_downstream[datacell])

        self.buffercells[buffercell] = structured_cell
        self.datacells[datacell] = structured_cell

        schemacell = structured_cell.schema
        if schemacell is not None:
            assert schemacell in self.schemacells
            self.schemacells[schemacell].append(structured_cell)

        inchannels = list(structured_cell.inchannels.keys())
        outchannels = list(structured_cell.outchannels.keys())

        inpathdict = {path: None for path in inchannels}
        self.paths_upstream[buffercell] = inpathdict

        outpathdict = {path: None for path in outchannels}
        self.paths_downstream[datacell] = outpathdict

    def register_macropath(self, macropath):
        self.macropath_to_upstream[macropath] = None
        self.macropath_to_downstream[macropath] = []

    def incref_expression(self, expression, accessor):
        if expression not in self.expression_to_accessors:
            #print("CREATE")
            assert expression not in self.expression_to_accessors
            self.expression_to_accessors[expression] = []
            manager = self.manager()
            manager.taskmanager.register_expression(expression)
            manager.cachemanager.register_expression(expression)
            manager.cachemanager.incref_checksum(expression.checksum, expression, False)
        #print("INCREF", expression.celltype, expression.target_celltype)
        self.expression_to_accessors[expression].append(accessor)

    def decref_expression(self, expression, accessor):        
        accessors = self.expression_to_accessors[expression]        
        accessors.remove(accessor)
        #print("DECREF", expression.celltype, expression.target_celltype, accessors)
        if not len(accessors):
            self.expression_to_accessors.pop(expression)
            manager = self.manager()
            manager.cachemanager.decref_checksum(expression.checksum, expression, False)            
            manager.taskmanager.destroy_expression(expression)
    
    def connect_pin_cell(self, current_macro, source, target):
        """Connect a pin to a simple cell"""
        assert target._monitor is None
        assert self.has_authority(target), target
        if isinstance(source, EditPin):
            assert target._get_macro() is None # Cannot connect edit pins to cells under macro control

        manager = self.manager()
        pinname = source.name
        worker = source.worker_ref()
        
        if isinstance(worker, Transformer):
            to_downstream = self.transformer_to_downstream[worker]
        elif isinstance(worker, Reactor):
            to_downstream = self.reactor_to_downstream[worker][pinname]
        elif isinstance(worker, Macro):
            raise TypeError(worker)

        celltype = source.celltype
        if celltype is None:
            celltype = target._celltype
        read_accessor = ReadAccessor(
            manager, None, celltype
        )
        if isinstance(worker, Reactor):
            read_accessor.reactor_pinname = pinname
        subcelltype = source.subcelltype
        if subcelltype is None:
            subcelltype = target._subcelltype
        write_accessor = WriteAccessor(
            read_accessor, target, 
            celltype=target._celltype, 
            subcelltype=target._subcelltype, 
            pinname=None,
            path=None
        )
        read_accessor.write_accessor = write_accessor
        assert self.accessor_to_upstream.get(read_accessor) is None, (self.accessor_to_upstream[read_accessor], worker)
        self.accessor_to_upstream[read_accessor] = worker
        to_downstream.append(read_accessor)
        self.cell_to_upstream[target] = read_accessor
        
        manager.cancel_cell(target, void=False)
        manager.taskmanager.register_accessor(read_accessor)
        if not worker._void:
            read_accessor._void = False # To trigger propagation
            propagate_accessor(manager.livegraph, read_accessor, False)
        else:
            target._status_reason = StatusReasonEnum.UPSTREAM

        return read_accessor

    def connect_cell_pin(self, current_macro, source, target):
        """Connect a simple cell to a pin"""
        assert source._monitor is None

        manager = self.manager()
        path_cell, path_pin = manager._verify_connect(current_macro, source, target)
        if path_pin:
            msg = str(target) + ": macro-generated pins/paths may not be connected outside the macro"
            raise Exception(msg)
        if path_cell:
            msg = str(source) + ": macro-generated cells/paths may only be connected to cells, not %s"
            raise Exception(msg % target)

        pinname = target.name
        worker = target.worker_ref()
        if isinstance(worker, Transformer):
            to_upstream = self.transformer_to_upstream[worker]
            cancel = manager.cancel_transformer
        elif isinstance(worker, Reactor):
            to_upstream = self.reactor_to_upstream[worker]
            cancel = manager.cancel_reactor
        elif isinstance(worker, Macro):
            to_upstream = self.macro_to_upstream[worker]
            cancel = manager.cancel_macro
        assert to_upstream[pinname] is None, target # must have received no connections

        read_accessor = ReadAccessor(
            manager, None, source._celltype
        )
        celltype = target.celltype
        if celltype is None:
            celltype = source._celltype
        subcelltype = target.subcelltype
        if subcelltype is None:
            subcelltype = source._subcelltype        
        write_accessor = WriteAccessor(
            read_accessor, worker, 
            celltype=celltype, 
            subcelltype=subcelltype, 
            pinname=pinname, 
            path=None
        )
        read_accessor.write_accessor = write_accessor
        assert self.accessor_to_upstream.get(read_accessor) is None, (self.accessor_to_upstream[read_accessor], source)
        self.accessor_to_upstream[read_accessor] = source
        self.cell_to_downstream[source].append(read_accessor)
        to_upstream[pinname] = read_accessor
        
        cancel(worker, void=False)
        manager.taskmanager.register_accessor(read_accessor)        
        if not source._void:
            read_accessor._void = False # To trigger propagation
            propagate_accessor(
                manager.livegraph,
                read_accessor,
                False
            )

        return read_accessor

    def connect_cell_cell(self, current_macro, source, target):
        """Connect one simple cell to another"""
        assert source._monitor is None and target._monitor is None
        assert self.has_authority(target), target
        
        manager = self.manager()
        read_accessor = ReadAccessor(
            manager, None, source._celltype
        )
        write_accessor = WriteAccessor(
            read_accessor, target, 
            celltype=target._celltype, 
            subcelltype=target._subcelltype, 
            pinname=None, 
            path=None
        )
        read_accessor.write_accessor = write_accessor
        assert self.accessor_to_upstream.get(read_accessor) is None, (self.accessor_to_upstream[read_accessor], source)
        self.accessor_to_upstream[read_accessor] = source
        self.cell_to_downstream[source].append(read_accessor)
        self.cell_to_upstream[target] = read_accessor
        
        manager.cancel_cell(target, void=False)
        manager.taskmanager.register_accessor(read_accessor) 
        target._status_reason = StatusReasonEnum.UPSTREAM       

        return read_accessor

    def connect_macropath_cell(self, current_macro, source, target):
        """Connect a macropath to a simple cell"""
        assert target._monitor is None
        assert self.has_authority(target), target
        
        manager = self.manager()
        read_accessor = ReadAccessor(
            manager, None, source
        )
        write_accessor = WriteAccessor(
            read_accessor, target, 
            celltype=target._celltype, 
            subcelltype=target._subcelltype, 
            pinname=None, 
            path=None
        )
        read_accessor.write_accessor = write_accessor
        assert self.accessor_to_upstream.get(read_accessor) is None, (self.accessor_to_upstream[read_accessor], source)
        self.accessor_to_upstream[read_accessor] = source
        self.macropath_to_downstream[source].append(read_accessor)
        self.cell_to_upstream[target] = read_accessor
        
        manager.cancel_cell(target, void=False)
        manager.taskmanager.register_accessor(read_accessor) 
        target._status_reason = StatusReasonEnum.UPSTREAM       

        return read_accessor

    def connect_cell_macropath(self, current_macro, source, target):
        """Connect a simple cell to a macropath"""
        assert source._monitor is None
        assert self.has_authority(target), target
        
        manager = self.manager()
        read_accessor = ReadAccessor(
            manager, None, source._celltype
        )
        write_accessor = WriteAccessor(
            read_accessor, target, 
            celltype=target, 
            subcelltype=None, 
            pinname=None, 
            path=None
        )
        read_accessor.write_accessor = write_accessor
        assert self.accessor_to_upstream.get(read_accessor) is None, (self.accessor_to_upstream[read_accessor], source)
        self.accessor_to_upstream[read_accessor] = source
        self.cell_to_downstream[source].append(read_accessor)
        self.macropath_to_upstream[target] = read_accessor
        
        cell = target._cell
        if cell is not None:
            manager.cancel_cell(cell, void=False)
        manager.taskmanager.register_accessor(read_accessor) 
        target._status_reason = StatusReasonEnum.UPSTREAM       

        return read_accessor

    def cell_from_pin(self, pin):
        from ..worker import InputPin, OutputPin
        worker = pin.worker_ref()
        if isinstance(pin, InputPin):
            if isinstance(worker, Transformer):
                upstream = self.transformer_to_upstream[worker]
            elif isinstance(worker, Reactor):
                upstream = self.reactor_to_upstream[worker]
            elif isinstance(worker, Macro):
                upstream = self.macro_to_upstream[worker]
            accessor = upstream[pin.name]
            if accessor is None:
                return None
            return self.accessor_to_upstream[accessor], accessor.subpath
        elif isinstance(pin, OutputPin):
            if isinstance(worker, Transformer):
                downstreams = self.transformer_to_downstream[worker]
            elif isinstance(worker, Reactor):
                downstreams = self.reactor_to_downstream[worker][pin.name]
            if downstreams is None:
                return None
            result = []
            for accessor in downstreams:
                target = accessor.write_accessor.target()
                subpath = accessor.write_accessor.path
                if isinstance(target, (Cell, Path)):                
                    result.append((target, subpath))
        elif isinstance(pin, EditPin):
            raise TypeError(EditPin)
        else:
            raise TypeError(type(pin))
        if not len(result):
            result = None
        return result

    def has_authority(self, cell_or_macropath, path=None):
        if isinstance(cell_or_macropath, Path):
            macropath = cell_or_macropath            
            assert path is None
            if macropath._destroyed:
                return True # TODO? would this ever be bad?
            return self.macropath_to_upstream[macropath] is None
        cell = cell_or_macropath
        if path is not None:
            assert cell._monitor is not None
            assert cell in self.buffercells
            raise NotImplementedError # livegraph branch
        assert cell._monitor is None
        if cell._destroyed and cell in self.temp_auth:            
            return self.temp_auth[cell]
        return self.cell_to_upstream[cell] is None

    def will_lose_authority(self, cell):
        return cell in self._will_lose_authority

    @destroyer
    def destroy_accessor(self, manager, accessor, from_upstream=False):
        #print("DESTROY", accessor)
        expression = accessor.expression
        if expression is not None:
            accessor.expression = None
            self.decref_expression(expression, accessor)            
            accessor._checksum = None
        taskmanager = manager.taskmanager
        taskmanager.destroy_accessor(accessor)
        upstream = self.accessor_to_upstream.pop(accessor)
        if isinstance(upstream, Cell):
            path = accessor.path
            if path is not None:
                raise NotImplementedError # livegraph branch
            else:
                self.cell_to_downstream[upstream].remove(accessor)
        elif isinstance(upstream, Transformer):
            self.transformer_to_downstream[upstream].remove(accessor)
        elif isinstance(upstream, Reactor):
            pinname = accessor.reactor_pinname
            assert pinname is not None
            self.reactor_to_downstream[upstream][pinname].remove(accessor)
        elif isinstance(upstream, Path):
            self.macropath_to_downstream[upstream].remove(accessor)
        elif upstream is None:
            pass
        else:
            raise TypeError(upstream)

        target = accessor.write_accessor.target()
        if isinstance(target, Cell):
            path = accessor.write_accessor.path
            if path is not None:
                raise NotImplementedError # livegraph branch
            else:
                manager.cancel_cell(target, True)
                if target in self.cell_to_upstream:
                    self.cell_to_upstream[target] = None
        elif isinstance(target, Transformer):
            pinname = accessor.write_accessor.pinname
            if target in self.transformer_to_upstream:
                self.transformer_to_upstream[target][pinname] = None
        elif isinstance(target, Reactor):
            pinname = accessor.write_accessor.pinname
            if target in self.reactor_to_upstream:
                self.reactor_to_upstream[target][pinname] = None
        elif isinstance(target, Macro):
            pinname = accessor.write_accessor.pinname
            if target in self.macro_to_upstream:
                self.macro_to_upstream[target][pinname] = None
        elif isinstance(target, Path):
            cell = target._cell
            if cell is not None:
                manager.taskmanager.cancel_macropath(cell, True)
            if target in self.macropath_to_upstream:
                self.macropath_to_upstream[target] = None
        else:
            raise TypeError(target)

    @destroyer
    def destroy_transformer(self, manager, transformer):
        up_accessors = self.transformer_to_upstream.pop(transformer)
        for up_accessor in up_accessors.values():
            if up_accessor is not None:
                self.destroy_accessor(manager, up_accessor)
        down_accessors = self.transformer_to_downstream[transformer]
        while len(down_accessors):            
            accessor = down_accessors[0]
            assert self.accessor_to_upstream[accessor] is transformer
            self.destroy_accessor(manager, accessor, from_upstream=True)
            if len(down_accessors) and down_accessors[0] is accessor:
                print("WARNING: destruction of transformer downstream %s failed" % accessor)
                down_accessors = down_accessors[1:]            
        self.transformer_to_downstream.pop(transformer)

    @destroyer
    def destroy_macro(self, manager, macro):
        up_accessors = self.macro_to_upstream.pop(macro)
        for up_accessor in up_accessors.values():
            if up_accessor is not None:
                self.destroy_accessor(manager, up_accessor)


    @destroyer
    def destroy_reactor(self, manager, reactor):
        self.rtreactors.pop(reactor)
        up_accessors = self.reactor_to_upstream.pop(reactor)
        for up_accessor in up_accessors.values():
            if up_accessor is not None:
                self.destroy_accessor(manager, up_accessor)
        down_accessor_dict = self.reactor_to_downstream[reactor]
        for pinname, down_accessors in down_accessor_dict.items():
            if down_accessors is None:
                continue
            while len(down_accessors):            
                accessor = down_accessors[0]
                assert self.accessor_to_upstream[accessor] is reactor
                self.destroy_accessor(manager, accessor, from_upstream=True)
                if len(down_accessors) and down_accessors[0] is accessor:
                    print("WARNING: destruction of reactor pin %s downstream %s failed" % (pinname, accessor))
                    down_accessors = down_accessors[1:]            
        self.reactor_to_downstream.pop(reactor)
        editpins_cell = self.editpin_to_cell.pop(reactor)
        for pinname, cell in editpins_cell.items():
            if cell is None:
                continue
            editpin = reactor._pins[pinname]
            if cell._destroyed or cell in self._destroying:
                continue
            self.cell_to_editpins[cell].remove(editpin)        

    @destroyer
    def destroy_cell(self, manager, cell):
        structured_cells = []
        buf_struc_cell = self.buffercells.pop(cell, None)
        if buf_struc_cell:
            structured_cells.append(buf_struc_cell)
        else:
            data_struc_cell = self.datacells.pop(cell, None)
            if data_struc_cell:
                structured_cells.append(data_struc_cell)
        structured_cells += self.schemacells.pop(cell, [])
        for structured_cell in structured_cells:
            assert cell._monitor is not None            
            structured_cell.destroy() 
                
        if cell._monitor:
            if buf_struc_cell:
                raise NotImplementedError # livegraph branch
                #up_accessors = self.paths_to_upstream.pop(cell)
            elif data_struc_cell:
                raise NotImplementedError # livegraph branch
                #down_accessors = self.paths_to_downstream.pop(cell)
        else:
            assert not len(structured_cells)
            self.temp_auth[cell] = self.has_authority(cell)
            up_accessor = self.cell_to_upstream.pop(cell)
            if up_accessor is not None:
                self.destroy_accessor(manager, up_accessor)
            down_accessors = self.cell_to_downstream[cell]
            while len(down_accessors):
                accessor = down_accessors[0]
                assert self.accessor_to_upstream[accessor] is cell
                self.destroy_accessor(manager, accessor, from_upstream=True)
                if len(down_accessors) and down_accessors[0] is accessor:
                    print("WARNING: destruction of cell downstream %s failed" % accessor)
                    down_accessors = down_accessors[1:]
            self.cell_to_downstream.pop(cell)
            editpins = self.cell_to_editpins.pop(cell)
            if editpins is not None:
                for editpin in editpins:
                    reactor = editpin.worker_ref()
                    if reactor._destroyed or reactor in self._destroying:
                        continue
                    self.editpin_to_cell[reactor][editpin.name] = None
        self._will_lose_authority.discard(cell)

    @destroyer
    def destroy_macropath(self, macropath):
        manager = self.manager()
        up_accessor = self.macropath_to_upstream.pop(macropath)
        if up_accessor is not None:
            self.destroy_accessor(manager, up_accessor)
        down_accessors = self.macropath_to_downstream[macropath]
        while len(down_accessors):
            accessor = down_accessors[0]
            assert self.accessor_to_upstream[accessor] is macropath
            self.destroy_accessor(manager, accessor, from_upstream=True)
            if len(down_accessors) and down_accessors[0] is accessor:
                print("WARNING: destruction of macropath downstream %s failed" % accessor)
                down_accessors = down_accessors[1:]            
        self.macropath_to_downstream.pop(macropath)

    def check_destroyed(self):        
        attribs = (
            "accessor_to_upstream",
            "expression_to_accessors",
            "cell_to_upstream",
            "cell_to_downstream",
            "paths_to_upstream",
            "paths_to_downstream",
            "transformer_to_upstream",
            "transformer_to_downstream",
            "datacells",
            "buffercells",
            "schemacells",
        )
        name = self.__class__.__name__
        for attrib in attribs:
            a = getattr(self, attrib)            
            if len(a):
                print(name + ", " + attrib + ": %d undestroyed"  % len(a))

from .propagate import propagate_accessor
from .accessor import Accessor, ReadAccessor, WriteAccessor
from ..transformer import Transformer
from ..reactor import Reactor
from ..macro import Macro, Path
from ..cell import Cell
from ..worker import EditPin
from ..runtime_reactor import RuntimeReactor