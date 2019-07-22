import weakref

# NOTE: distinction between simple cells (no StructuredCell monitor), StructuredCell data cells, and StructuredCell buffer cells

class LiveGraph:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.read_accessor_upstream = {} # Mapping of read accessors to the cell or worker that defines it.
                                         # Mapping is a tuple (cell-or-worker, pinname), where pinname is only defined for reactors.
        self.cell_to_upstream = {} # Mapping of simple cells to the read accessor that defines it.
        self.cell_to_downstream = {} # Mapping of simple cells to the read accessors that depend on it.
        self.paths_upstream = {} # Mapping of buffercells-to-dictionary-of-path:upstream-write-accessor.
        self.paths_downstream = {} # Mapping of datacells-to-dictionary-of-path:list-of-downstream-read-accessors
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
        assert self.cell_to_downstream[buffercell] is None

        datacell = structured_cell.data
        assert buffercell is not datacell
        assert datacell in self.cell_to_upstream
        assert self.cell_to_upstream[datacell] is None
        assert self.cell_to_downstream[datacell] is None

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

    def connect_accessor_cell(self, accessor, cell):
        assert isinstance(accessor, ReadAccessor)
        if cell._monitor is None:
            raise NotImplementedError # livegraph branch
        else:
            raise NotImplementedError # livegraph branch, structuredcell
            self.write_accessor_upstream ### ...

    def has_authority(self, cell, path=None):
        if path is not None:
            assert cell._monitor is not None
            assert cell in self.buffercells
            raise NotImplementedError # livegraph branch
        assert cell._monitor is None
        return self.cell_to_upstream[cell] is None

    def destroy_cell(self, cell):
        structured_cells = []
        buf_struc_cell = self.buffercells.pop(cell)
        if buf_struc_cell:
            structured_cells.append(buf_struc_cell)
        else:
            data_struc_cell = self.datacells.pop(cell)
            if data_struc_cell:
                structured_cells.append(data_struc_cell)
        structured_cells += self.schemacells.pop(cell)
        for structured_cell in structured_cells:
            assert cell._monitor is not None            
            structured_cell.destroy() 
        if cell._monitor:
            if buf_struc_cell:
                raise NotImplementedError # livegraph branch
                #up_accessors = self.paths_upstream.pop(cell)
            elif data_struc_cell:
                raise NotImplementedError # livegraph branch
                #down_accessors = self.paths_downstream.pop(cell)
        else:
            assert not len(structured_cells)
            raise NotImplementedError # livegraph branch
            #up_accessor = self.cell_upstream.pop(cell)
            #down_accessors = self.cell_downstream.pop(cell)

from .accessors import Accessor, ReadAccessor, WriteAccessor        