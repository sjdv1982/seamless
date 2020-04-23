Cells
=====

A cell (seamless.highlevel.Cell) contains a piece of data in the dependency graph that is contained by a Seamless Context.
Thus, cells are always part of a Context (called `ctx` by convention).

Within this context graph, cell values are constant.

When you modify a cell, you essentially create a new context graph where all dependencies of this cell are set to `None`, until they have been recomputed.

Assigning a cell to another cell creates a connection from the second cell to the first cell.

Changing cell values is asynchronous: 
```python
ctx.a = Cell()
await ctx.translation()
ctx.a = 123
print(ctx.a.value) 
```
```None```
```python
await ctx.computation() # or wait a few milliseconds in IPython or Jupyter
print(ctx.a.value) 
```
```<Silk 123>```

Cells are by default *structured cells*, which:
- Contain values that are **mixed**: they can contain plain (JSON-serializable) values, Numpy arrays, or a mix of the two.
- Have a schema (a superset of JSON schema)
- Support sub-cells:
```python
ctx.a = Cell()
ctx.b = Cell()
await ctx.translation()
ctx.b.sub1 = {"x": 12}
ctx.b.sub2 = ctx.a
ctx.a = 99
await ctx.computation()
print(ctx.b.value)
ctx.c = ctx.b.sub1.x
await ctx.computation()
print(ctx.c.value)
```

```
<Silk: {'sub1': {'x': 12}, 'sub2': 99} >
<Silk: 12 >
```

Using the celltype property, a cell can be changed to a non-structured cell (see the documentation of the Cell class for more details).