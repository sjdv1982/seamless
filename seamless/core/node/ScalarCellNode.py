from . import Node, resolve_path

class ScalarCellNode(Node):
    _manager = None
    def __init__(self, cell):
        context = cell._context
        self._init(cell, context, None)

    def _init(self, cell, context, node_id):
        from ..cell import Cell
        assert isinstance(cell, Cell)
        self._context = context
        manager = self._context._manager.node
        self._manager = manager
        self._id = manager.register(
            self,
            self._context,
            sends_state = True,
            sends_messages = False,
            id = node_id
        )
        self._cell_id = manager.get_cell_id(cell)
        manager.observe_cell(self._cell_id, self._id)

    def create_ss_link(self, link, incoming):
        if incoming:
            raise TypeError
        target_id = (link.target_context, link.target_id)
        self._manager.listen_state(self._id, target_id)

    def destroy_ss_link(self, link):
        target_id = (link.target_context, link.target_id)
        self._manager.unlisten_state(self._id, target_id)

    def create_msg_link(self, link, incoming):
        if not incoming:
            raise TypeError
        pass

    def destroy_msg_link(self, link):
        pass

    def receive_cell_state(self, state):
        self._manager.send_state(self._id, state)

    def receive_state(self, state):
        raise TypeError

    def receive_message(self, msg):
        if msg.path:
            return
        cell = self._manager.cells[self._cell_id]
        if msg.type in ("state", "set", "update"):
            cell.set(msg.content)
        elif msg.type == "delete":
            cell.set(None)

    def to_json(self):
        nodeid = self._id[1]
        cell = self._manager.cells[self._cell_id]
        return {
            "NodeClass": "ScalarCellNode",
            "cell": cell.path,
            "id": nodeid,
        }

    @classmethod
    def from_json(cls, data, context):
        assert data["type"] ==  "ScalarCellNode"
        cellpath = data["cell"].split()
        root = context._root()
        cell = resolve_path(root, cellpath)
        node_id = data["id"]
        self = cls.__new__()
        self._init(cell, context, node_id)
        return self

    def __del__(self):
        manager = self._manager
        if manager is None:
            return
        manager.observe_cell(self._cell_id, self._id)
        manager.unregister(self._id)

#TODO: register NodeClass with context deserializer
