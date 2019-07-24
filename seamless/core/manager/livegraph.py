import weakref

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
        self.datacells = {}
        self.buffercells = {}
        self.schemacells = {} # cell-to-structuredcell to which it serves as schema; can be multiple

    def register_cell(self, cell):
        assert cell._monitor is None # StructuredCells get registered later
        self.cell_to_upstream[cell] = None
        self.cell_to_downstream[cell] = []
        self.schemacells[cell] = []
        
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
        if expression not in self.expression_to_accessors:
            self.expression_to_accessors[expression] = []
            manager = self.manager()
            manager.cachemanager.incref_checksum(expression.checksum, expression, False)
            manager.taskmanager.register_expression(expression)
        self.expression_to_accessors[expression].append(accessor)

    def decref_expression(self, expression, accessor):
        accessors = self.expression_to_accessors[expression]
        accessors.remove(accessor)        
        if not len(accessors):
            self.expression_to_accessors.pop(expression)
            manager = self.manager()
            manager.cachemanager.decref_checksum(expression.checksum, expression, False)            
            manager.taskmanager.destroy_expression(expression)

    def connect_cell_cell(self, source, target):
        """Connect one simple cell to another"""
        assert source._monitor is None and target._monitor is None
        assert self.has_authority(target), target
        
        manager = self.manager()
        read_accessor = ReadAccessor(
            manager, None, source._celltype, source._subcelltype
        )
        write_accessor = WriteAccessor(
            read_accessor, target, None, None
        )
        read_accessor.write_accessor = write_accessor
        self.accessor_to_upstream[read_accessor] = source
        self.cell_to_downstream[source].append(read_accessor)
        self.cell_to_upstream[target] = read_accessor
        
        manager.taskmanager.register_accessor(read_accessor)
        propagate_cell(self, target, void=False)

        return read_accessor

    def has_authority(self, cell, path=None):
        if path is not None:
            assert cell._monitor is not None
            assert cell in self.buffercells
            raise NotImplementedError # livegraph branch
        assert cell._monitor is None
        return self.cell_to_upstream[cell] is None

    def destroy_accessor(self, manager, accessor):
        taskmanager = manager.taskmanager
        taskmanager.destroy_accessor(accessor)
        self.accessor_to_upstream.pop(accessor)
        expression = accessor.expression
        print("")
        if expression is not None:
            self.decref_expression(expression, accessor)
        

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
            down_accessors = self.cell_to_downstream.pop(cell)
            for accessor in down_accessors:
                self.destroy_accessor(manager, accessor)                

    def check_destroyed(self):        
        attribs = (
            "accessor_to_upstream",
            "expression_to_accessors",
            "cell_to_upstream",
            "cell_to_downstream",
            "paths_to_upstream",
            "paths_to_downstream",
            "datacells",
            "buffercells",
            "schemacells",
        )
        name = self.__class__.__name__        
        for attrib in attribs:
            a = getattr(self, attrib)
            if len(a):
                print(name + ", " + attrib + ": %d undestroyed"  % len(a))

from .propagate import propagate_cell
from .accessor import Accessor, ReadAccessor, WriteAccessor