from abc import ABC, abstractmethod
from collections import namedtuple

"""
Links are either state-sharing, or message-based.

Manager API:
("nodeid" is in fact a tuple of (context, Node ID). Only the second part
 needs to be saved during serialization)
.register(mynode, context, sends_state, sends_messages, id=None) => nodeid
.unregister(mynodeid)
.get(nodeid) => node
.send_state(mynodeid, state) (also sends a "state" *message*)
.listen_state(targetnodeid, mynodeid) => callback: mynode.receive_state()
.unlisten_state(targetnodeid, mynodeid)
.send_message(mynodeid, message)
.listen_messages(targetnodeid, mynodeid, mynode) => callback: mynode.receive_message()
.unlisten_messages(targetnodeid, mynodeid)
.observe_cell(cellid, mynodeid) => callback: mynode.receive_cell_state()
.unobserve_cell(cellid, mynodeid)

Conventions for link creation:
- Upstream API first creates link object
- Upstream API invokes create_XXX_link(incoming=False) on target node
- Upstream API invokes create_XXX_link(incoming=True) on source node
  Source node is responsible to create links with the managers (listen_state, listen_messages).
  This causes the manager to trigger methods on the nodes when something happens
- Upstream API must hold on to link object

Conventions for link creation: same, but in reverse order:
  (source node must destroy links with the managers)
Links will be destroyed when the source node or target node is destroyed, by
  the manager (after .unregister)

Conventions for serialization:
- A node is always tied to a context object (not a context name)
- When created, each node registers itself with the manager, receiving a node ID
  The node may already have a node ID from serialization. In that case, the node must
  provide this ID to the manager, who will check that the node ID is unique for the context
  When registering, the node must also indicate whether it will send
- Upstream API invokes serialization/deserialization
  Macros must keep track of the nodes that they create
  In a context, nodes are deserialized at the very last, after cells and connections
- Each node only holds its own state. The manager holds all link serialization.
  Each node can query the manager for links using its node ID.

Bidirectional links are not directly supported, but you can create two links.
Nodes are not supposed to re-inform the manager of state updates triggered by
receive_state itself. If node B listens to the state of node A, and node C
listens to the state of node B, then node C will directly receive state updates
of node A from the manager.
"""

class Node(ABC):
    @abstractmethod
    def create_ss_link(self, link, incoming):
        pass

    @abstractmethod
    def destroy_ss_link(self, link):
        pass

    @abstractmethod
    def create_msg_link(self, link, incoming):
        pass

    @abstractmethod
    def destroy_msg_link(self, link):
        pass

    @abstractmethod
    def receive_state(self, state):
        pass

    @abstractmethod
    def receive_cell_state(self, state):
        pass

    @abstractmethod
    def receive_message(self, msg):
        pass

    @abstractmethod
    def to_json(self):
        pass

    @classmethod
    @abstractmethod
    def from_json(cls, data, context):
        pass

Link = namedtuple(typename="Link", field_names=(
  "source_context", "source_id", "target_context", "target_id"
))
Message = namedtuple(typename="Message", field_names=(
  "type", "path", "content",
))

def resolve_path(target, path, index=0):
    if path is not None and len(path) > index:
        try:
            new_target = getattr(target, path[index])
        except AttributeError:
            warn = "WARNING: cannot reconstruct node links for '{0}', target no longer exists"
            subpath = "." + ".".join(target.path + path[:index+1])
            print(warn.format(subpath))
            return None
        return resolve_path(new_target, path, index+1)
    return target

from .ScalarCellNode import ScalarCellNode
