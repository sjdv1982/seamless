# Cells

A cell (seamless.highlevel.Cell) contains a piece of data in the dependency graph that is contained by a Seamless Context.
Thus, cells are always part of a Context (called `ctx` by convention).

Within this context graph, cell values are constant.

When you modify a cell, you essentially create a new context graph where all dependencies on this cell are set to `None`, until they have been recomputed.

Assigning a cell to another cell creates a connection from the second cell to the first cell.

Changing cell values is asynchronous:

```python
ctx.a = Cell()
await ctx.translation()
ctx.a = 123
print(ctx.a.value)
```

`None`

```python
await ctx.computation() # or wait a few milliseconds in IPython or Jupyter
print(ctx.a.value)
```

`<Silk 123>`

Cells are by default *structured cells*, which:
- Contain values that are **mixed**: they can contain plain (JSON-serializable) values, Numpy arrays, or a mix of the two.
- Have a schema (a superset of JSON schema)
- Support subcells:

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

```text
<Silk: {'sub1': {'x': 12}, 'sub2': 99} >
<Silk: 12 >
```

Using the `celltype` property, a cell can be changed to a non-structured cell (see the documentation of the Cell class for more details).

Cells are *dependent* if (part of) the cell's value is computed from a dependency, i.e from a transformer or from another cell.
Cells are *independent* if they have their own value, with no dependencies.

Cells can be *mounted* to a file using `Cell.mount`. By default, mounts are both read (the cell changes its value when the file changes its value) and write (vice versa) . Only independent cells can have a read mount. *Structured cells cannot be mounted.*

Cells can be *shared* over HTTP (via the Seamless REST API), using `Cell.share`. By default, shares are read-only (only HTTP GET requests are supported). Independent cells can also be shared as read/write (their value can be changed using HTTP PUT requests). If a cell is to be accessed as a URL from the browser, you are recommended to set `Cell.mimetype`.

Newly created/connected/mounted/shared cells require a re-translation of the context to take effect. This is also the case for a change in celltype.

## Alternative subcell syntax

You can use `ctx.c["sub"]` to assign or refer to subcell `ctx.c.sub`. This way, you can also access subcells that are not valid Python variables, such as `ctx.c["file.txt"]`.
You can also access individual elements from a list:
```python
ctx.c = [10, 20, 30]
ctx.sub = ctx.c[1]
await ctx.computation()
print(ctx.sub.value)
ctx.c = [101, 201, 301]
await ctx.computation()
print(ctx.sub.value)
```

```
20
201
```

## Cell types and conversion

***IMPORTANT: This documentation section is a stub.***

<!--
Cell types:

- Text cells
- Plain cells: str, float, int, bool
- Binary cells: numpy
- Mixed cells
- Conversion
- Code cells, cson, yaml
- Subcelltypes
- Semantic checksums: code, cson, yaml
- Checksum cells
-->