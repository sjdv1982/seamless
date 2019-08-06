import weakref
from ..status import StatusReasonEnum

# NOTE: distinction between simple cells (no StructuredCell monitor), StructuredCell data cells, and StructuredCell buffer cells

class LiveGraph:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.accessor_to_upstream = {} # Mapping of read accessors to the cell or worker that defines it.
                                    # Mapping is a tuple (cell-or-worker, pinname), where pinname is None except for reactors.
        self.expression_to_accessors = {} # Mapping of expressions to the list of read accessors that resolve to it
        self.cell_to_upstream = {} # Mapping of simple cells to the read accessor that defines it.
        self.cell_to_downstream = {} # Mapping of simple cells to the read accessors that depend on it.
        self.paths_to_upstream = {} # Mapping of buffercells-to-dictionary-of-path:upstream-write-accessor.
        self.paths_to_downstream = {} # Mapping of datacells-to-dictionary-of-path:list-of-downstream-read-accessors
        self.transformer_to_upstream = {} # input pin to read accessor
        self.transformer_to_downstream = {}
        self.reactor_to_upstream = {} # input pin to read accessor
        self.reactor_to_downstream = {} # Unlike all other X_to_downstream, this is a dict
        self.macro_to_upstream = {} # input pin to read accessor

        self.datacells = {}
        self.buffercells = {}
        self.schemacells = {} # cell-to-structuredcell to which it serves as schema; can be multiple

        self._will_lose_authority = set()

    def register_cell(self, cell):
        assert cell._monitor is None # StructuredCells get registered later
        self.cell_to_upstream[cell] = None
        self.cell_to_downstream[cell] = []
        self.schemacells[cell] = []

    def register_transformer(self, transformer):
        inputpins = [pinname for pinname in transformer._pins \
            if transformer._pins[pinname].io == "input" ]
        upstream = {pinname:None for pinname in inputpins}
        self.transformer_to_upstream[transformer] = upstream
        self.transformer_to_downstream[transformer] = []

    def register_reactor(self, transformer):
        raise NotImplementedError # livegraph branch; to-downstream and editpins make it tricky

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
        editchannels = list(structured_cell.editchannels.keys())

        inpathdict = {path: None for path in inchannels+editchannels}
        self.paths_upstream[buffercell] = inpathdict

        outpathdict = {path: None for path in outchannels+editchannels}
        self.paths_downstream[datacell] = outpathdict

    def incref_expression(self, expression, accessor):
        expression = expression      
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
        expression = expression
        accessors = self.expression_to_accessors[expression]        
        accessors.remove(accessor)
        #print("DECREF", expression.celltype, expression.target_celltype, accessors)
        if not len(accessors):
            self.expression_to_accessors.pop(expression)
            manager = self.manager()
            manager.cachemanager.decref_checksum(expression.checksum, expression, False)            
            manager.taskmanager.destroy_expression(expression)
    
    def connect_pin_cell(self, source, target):
        """Connect a pin to a simple cell"""
        assert target._monitor is None
        assert self.has_authority(target), target

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
        self.accessor_to_upstream[read_accessor] = worker
        to_downstream.append(read_accessor)
        self.cell_to_upstream[target] = read_accessor
        
        manager.cancel_cell(target, void=False)
        manager.taskmanager.register_accessor(read_accessor)
        if not worker._void:
            read_accessor._void = False # To trigger propagation
            propagate_accessor(read_accessor)
        else:
            target._status_reason = StatusReasonEnum.UPSTREAM

        return read_accessor

    def connect_cell_pin(self, source, target):
        """Connect a simple cell to a pin"""
        assert source._monitor is None

        manager = self.manager()
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

    def connect_cell_cell(self, source, target):
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
        self.accessor_to_upstream[read_accessor] = source
        self.cell_to_downstream[source].append(read_accessor)
        self.cell_to_upstream[target] = read_accessor
        
        manager.cancel_cell(target, void=False)
        manager.taskmanager.register_accessor(read_accessor) 
        target._status_reason = StatusReasonEnum.UPSTREAM       

        return read_accessor

    def cell_from_pin(self, pin):
        worker = pin.worker_ref()
        if isinstance(worker, Transformer):
            upstream = self.transformer_to_upstream[worker]
        elif isinstance(worker, Reactor):
            upstream = self.reactor_to_upstream[worker]
        elif isinstance(worker, Macro):
            upstream = self.macro_to_upstream[worker]
        upstreams = upstream[pin.name]
        if upstreams is None:
            return None
        result = []
        for accessor in upstreams:
            cell = self.accessor_to_upstream[accessor]
            assert isinstance(cell, (Cell, Path))
            result.append(cell)
        if not len(result):
            result = None
        return result

    def has_authority(self, cell, path=None):
        if path is not None:
            assert cell._monitor is not None
            assert cell in self.buffercells
            raise NotImplementedError # livegraph branch
        assert cell._monitor is None
        return self.cell_to_upstream[cell] is None

    def will_lose_authority(self, cell):
        return cell in self._will_lose_authority

    def destroy_accessor(self, manager, accessor):
        from ..cell import Cell
        from ..transformer import Transformer
        expression = accessor.expression
        if expression is not None:
            self.decref_expression(expression, accessor)
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
        elif isinstance(target, Macro):
            pinname = accessor.write_accessor.pinname
            if target in self.macro_to_upstream:
                self.macro_to_upstream[target][pinname] = None
        else:
            raise TypeError(target)

    def destroy_transformer(self, manager, transformer):
        up_accessors = self.transformer_to_upstream.pop(transformer)
        for up_accessor in up_accessors.values():
            if up_accessor is not None:
                self.destroy_accessor(manager, up_accessor)
        down_accessors = self.transformer_to_downstream[transformer]
        while len(down_accessors):
            accessor = down_accessors[0]
            self.destroy_accessor(manager, accessor)
        self.transformer_to_downstream.pop(transformer)

    def destroy_macro(self, manager, macro):
        up_accessors = self.macro_to_upstream.pop(macro)
        for up_accessor in up_accessors.values():
            if up_accessor is not None:
                self.destroy_accessor(manager, up_accessor)

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
            up_accessor = self.cell_to_upstream.pop(cell)
            if up_accessor is not None:
                self.destroy_accessor(manager, up_accessor)
            down_accessors = self.cell_to_downstream[cell]
            while len(down_accessors):
                accessor = down_accessors[0]
                self.destroy_accessor(manager, accessor)
            self.cell_to_downstream.pop(cell)
        self._will_lose_authority.discard(cell)

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