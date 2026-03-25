# Deep cells

The primary function of deep cells is to describe data that is too big to fit in memory, by using a checksum-of-checksums approach. A deep cell has a checksum where the underlying value is itself a dict of checksums. Those checksums can either be of celltype "mixed" (DeepCell) or "bytes" (DeepFolderCell, FolderCell).

***IMPORTANT: This documentation section is a stub.***

(relevant tests are probably not that useful without explanation first. Integrate with the following:)

A transformation is in fact a "deep structure". Its checksum corresponds to a dictionary, where each value is itself a checksum (of the input cells).

Seamless has support for two other kinds of deep structures: deep cells and deep folders. In both cases, the deep structure is again a dictionary, where the keys are strings and the values are checksums. The difference is the cell type of the checksums. For deep cells, the cell type is "mixed" (Seamless's default cell type), which means that you can easily access an individual element and convert it trivially to a normal Seamless cell. In contrast, for deep folders, the cell type is "bytes", which means that buffer and value are the same. This allows a one-to-one mapping with a
folder on the file system.

<!--
Intro:
- Deep cells
- DeepCell, DeepFolderCell, FolderCell

TODO: move/clone from "Deep structures" in "Seamless explained"
-->

## Mapping contexts

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

Mapping libs are in stdlib.map. Currently, there is no reduce (to be done).

You have the choice between `map_dict` and `map_dict_chunk` (support for lists is working, but untested/undocumented). In either case, you must prepare a `mapping context` that will be applied to each element (`map_dict`) or each chunk (`map_dict_chunk`) of an input dict.

Mapping contexts must contain at least two cells: `inp` and `result`. The workflow will generate many clones of the mapping context, and each clone's `inp` will contain its input: a single value (no key) for `map_dict`, and a chunk (a dict containing keys and values) for `map_dict_chunk`.  Typically, the mapping context contains at least one transformer that transforms `inp` to `result`.

There may also be a cell `uniform` that contains parameters that are external to the mapping context, but constant to each clone.

If provided, `uniform` must be a mixed Cell. For `map_dict`, `inp` and `result` must also be mixed Cells. For `map_dict_chunk`, `inp` and `result` can be either a mixed Cell or a SimpleDeepCell.

You are strongly recommended to test the mapping context yourself by connecting `inp` to a simple input, before applying it to thousands of inputs.

## Performance considerations

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

First, it is important to consider the size of the workflow. Seamless workflows can comfortably consist of hundreds of thousands of elements (cells, workers and connections), with a overhead of (at most) a few milliseconds per element. However, once the number of elements approaches millions, the per-element overhead increases and the total overhead explodes, which essentially freezes Seamless.

Note that this applies to low-level elements. High-level elements are translated into one or more low-level elements. A simple Cell is a single element, but a structured Cell is three cells plus connections, and a Transformer is at least seven cells plus one cell per input pin, plus connections. Therefore, you should count at least 20 elements even for a minimal mapping context. That means that you shouldn't create more than ~10 000 mapping context clones.

Second, as always, it is important to make transformation jobs of the appropriate duration (transformation overhead is in the order of 0.1 second). If a mapping of an individual element is too quick, use `map_dict_chunk` and increase the chunk size until you are in the range of 10 seconds to 10 minutes per transformation.

Third, it is important not to create too many running tasks at the same time. To some extent, this is automatically managed by Seamless, but you still should add a manual safeguard using *elision*. The dynamic cloning of mapping contexts is done using a low-level element called a *macro*. With elision, individual macros with well-defined input and output cells can be cached just like transformers can. With an elision cache hit, the macro is not run at all (i.e. the mapping context is not constructed at all), only the result cell is constructed and its checksum is set. In addition, with elision enabled, `map_dict` and `map_dict_chunk` organize the mapping contexts in a hierarchical manner: the top macro spawns submacros that spawn submacros (that spawn submacros, etc.) that finally spawn a chunk of mapping context clones. The maximum number of submacros or mapping contexts that is spawned is controlled by the `elision_chunksize` parameter.

Elision has the additional benefit that re-running a mapping (or resuming it after it was aborted) happens at much reduced overhead, since the workflow graph is not built at all for the parts that have already been done.

Fourth, it is important to consider the size of the data. Obviously, if the dataset that is to be mapped is very large, or its mapped result is very large, then it must be stored as deep cells, with the underlying buffers in a database. However, the underlying data must still be accessed by transformers. If you do `map_dict`, there shouldn't be much of a problem. But with `map_dict_chunk` and large chunk sizes, the main Seamless process will by default convert every chunk to a normal mixed format while preparing the transformation. This will cause it to fetch a lot of data from the database, and then write the aggregate data back. If the number of simultaneous transformations is large, this will cause memory issues. Not that this is at the transformation *preparation* stage, i.e. using a job manager won't help. The solution is to declare the input pin celltype of the transformer as "deepcell". This will cause the *transformation* (wherever it runs) to become responsible to unpack the deep structure into a normal value. Not only could this be much closer to the data, transformations can use fast multi-thread unpacking that minimizes the bookkeeping and database requests. In the other direction, you may also consider to declare the celltype of the transformation result to be "deepcell". In that case, the transformation will (after execution) pack its result into a deep structure (again, using a multi-thread packing function that is much more efficient than the main process) and push it to the database. Moreover, in case of local or jobslave execution, the transformation lock is released (since packing is I/O bound), so another transformation may start.

Finally, for deep cells with a very large number of elements (hundreds of thousands) with small `map_dict_chunk` chunks, it may take time for Seamless to increase and decrease references to the individual buffers (contacting the database each time). Seamless has a heuristic to avoid this for many elements, but it will still do it on every chunk if the chunk is smaller than 1000 or so. To avoid this, do:
``` python
from seamless.core.cache.deeprefmanager import deeprefmanager
deeprefmanager.MAX_DEEP_BUFFER_MEMBERS = X 
```
where X is smaller than your chunk size, but no smaller than 50 or so.