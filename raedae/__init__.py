"""
Framework to transform trees with data access expressions (DAEs) into resolved trees
For resolved trees, it is determined for every property if changing it would change the tree topology
  Non-topological properties can in fact be updated dynamically using buffers, without re-resolving the tree
(This does cause DAE trees to be somewhat limited in transformation abilities; combine with ATC and transformers for more expressive power)

Primitive node types can be defined. Nodes that are children of primitives don't have their DAEs resolved
 Instead, they are converted to runtime access expressions (RAEs), i.e. AST that have to be evaluated at runtime (by Python on the CPU, or CUDA on the GPU)

See the lightweight documentation for more details
"""