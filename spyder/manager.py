"""
Spyder manager
The Spyder model state contains the model definition of all Spyder models
In live mode, the Spyder manager will receive and forward updates to the Spyder model state to registered cell processes

If we are not master, the Spyder manager will not exist: all Spyder (re)definition requests will be forwarded to the master
   By default, to the default sfport
   If a special Spyder manager sfport has been specified, then to that one
Therefore, in principle, there is only a single Spyder model state.

Updates can come in the following modes:
- Define
- Redefine
and the following formats:
- Primitive type: Python code
- Full: Python code + dependencies + JSON minischema + formtree
- Form: just the formtree

It is assumed that the Python code not only defines the class X, but also the classes:
- XArray, XArrayArray and XArrayArrayArray
- ResourceX, ResourceXArray, ResourceXArrayArray and ResourceXArrayArrayArray
A full update automatically triggers a full update of any Spyder model that
In case of a full update, every cell chain that indicates a dependency
"""
