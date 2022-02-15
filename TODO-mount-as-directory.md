
-1. Run a test to determine a reasonable cell budget (step 11)
UPDATE: see step 11
0: Fix the fact that you cannot set a deep list from a Numpy array (DeepStructureError).
====> here
UPDATE: first do Fairserver plan
1. Make Dataset, Repository, DeepCell, DeepListCell classes.
They correspond to the following low-level deep cells:
 Dataset: hash pattern {"*": "!!"} (dict-of-byte-cells)
 Repository: hash pattern {"*": "!!"} (dict-of-byte-cells)
 DeepCell: hash pattern {"*": "!"} (dict-of-mixed-cells)
 DeepListCell: hash pattern {"*": "!"} (list-of-mixed-cells)
Make them connectable and translatable like structured cells.
Dataset/Repository only supports outchannels. 
DeepCell/DeepListCell support also inchannels.
They are inter-convertible (i.e. connectable) among themselves
and also to ordinary structured/simple cells. This is already supported
by the conversion engine, since the classes get translated as deep cells.
There will also be transformer pin celltype "dataset", "deepcell", "deeplistcell". No celltype repository, as it is converted to a normal mixed cell. Assigning a transformer pin to a Dataset, DeepCell, DeepListCell creates a
pin of that celltype. Assigning it to a Repository creates a "dataset" pin in case of a bash transformer, a "mixed" pin otherwise. Pins of "dataset", "deepcell", "deeplistcell" are not part of the normal .inp structured cell and 
are hence not amenable to transformer input schemas.
NOTE: execution order checksum is a part of Dataset/DeepCell as well!
2. Finish core/mount_directory. Support continuous mount only for Repository and Modules! For those, .mount is *always* to a diretory
Support load_directory/write_directory only for Datasets, Repositories and Modules!
Write tests, adapt tests/highlevel/multi-module.py and graphs/multi_module/ accordingly.
3. Bump __seamless__ version of .seamless files to 0.8.
Rip mount.as_directory from high-level Cell. Add a loader so that __seamless__ < 0.8 (or None) will interpret
a Cell("plain") with mount:as_directory as a Repository with .mount.
NOTE: especially important for webgen! 
4. Rip hash patterns from Cell, and adapt examples to use DeepCell, DeepListCell.
Write tests.
NOTE: rip Resource?
5. 
- Re-design database.py so that the default YAML normally works well,
and that there is a subfolder for download pages/buffer info pages
of named datasets.
- For Dataset/Deepcell (not Repository), support loading-by-name.
This will obtain and then set: checksum, and execution order checksum.
Name may include version, format (e.g. gzip)
The RPBS will have a name server that does:
a. Map name+version+format to a checksum
b. Provide links to context/metadata websites (e.g. PDB main page)
c. Provide a link to download options. For the PDB, this would link to
a RPBS "download page", where for each once-or-current PDB checksum (also mmcif), a list of direct download links is provided. 
(example: https://files.rcsb.org/download/1AVX.pdb)
A direct download link can be annotated with "gzip" etc. The database will normally fetch the "download page" and store it locally.
In the future, support BitTorrent as well.
d. Map name+version+format to an execution order checksum.
e. Provide a link to a bufferinfo page for all relevant checksums.
MAKE A BIG WARNING IF LOADING-BY-NAME IS DONE WITHIN LOAD-PROJECT!
This will make load-project not reproducible!!!
- Add a database command to load all entries in a download page in local file cache. File cache can be inside the database dir, but also an outside directory. Do the same for bufferinfo entries.
UPDATE: 
a. load-by-name in a different API (seamless.fair)
b. Allow a list-of-allowed-checksums to be stored, by name. 
   Dataset.load(name) will invoke this.
   Possible to restrict allowed checksums only to this.
   Is also necessary to allow Dataset.share()  
   (list of allowed checksums becomes dropdown menu, restriction is security feature)
   Allow blacklist or whitelist checksum to be stored in Deepcell/Dataset
   (Destroys name-of-directory database hit for Dataset)
UPDATE2: Seamless database and FAIR server are now distinct, but make
tools to export contents of the database dir (notably, /downloads,
/datasets, /deepcells, and deep buffers in /buffers) to a FAIR server dir.
6. Add filename support to transformers, as outlined in https://github.com/sjdv1982/seamless/issues/108. Make bash/docker transformers accept Dataset inputs, leading to directory checksum requests.
Write tests, e.g. a hhblits search where the database path is a Dataset
checksum.
Adapt Cloudless with Shell deployment + file name rewrite and test if 
the dataset folder name is transferred.
7. DONE: fix the bug in the "DEBUGGING IN PROGRESS" commit (c9708d77598)
8. Allow cells in a subcontext to be marked as "input" or "output".
A subcontext will not translate unless all "inputs" have been connected.
.status of the subcontext and all its members will reflect this.
9. Allow "input"/"output" cells and all Transformer pins to have a "scatter" flag. Such cells or pins must be connected from DeepCell/DeepListCell if "mixed", or Dataset if "bytes".
Any Subcontext with "scatter" flags get translated via a stdlib.map
construction. Transformer with "scatter" flags get upgraded to Subcontext. This makes stdlib.map an implicit part of the Seamless high-level language, essentially.
Alternatively, "input"/"output" cells and transformer pins that are 
*already* of the celltype Dataset/DeepCell/DeepListCell can have a "scatter_chunk" parameter, for map_dict_chunk evaluation. This does not
change the celltype of what they are connected to (the context/transformer will still operate on a deep dict/list, albeit a much smaller one). TODO: need then an API to get execution order (for incremental)!
Make sure that any scattered Subcontext/Transformer has no .mount or .share!
Also, modifying the value of a cell/pin CANNOT be relayed to the low level
(there are many low-level copies!) and a re-translation is necessary.
Tell this to the user when they make such a modification!
10. Add a status redirection mechanism to catch error messages agnostic of the internal stdlib.map
11. "Internal elision". Have a cell budget (say, 10 000 cells). Wait with macro execution until the cell budget is below max. Elide macros immediately after their execution if the cell budget is above max.
UPDATE: 40 000 (low level) cells can be created in 5 minutes, without memory problems. This corresponds to a one-transformer high-level context mapped over 2 000 entries. 
Asyncio crawl is the main reason for why constructing cells is slow.
For larger numbers (e.g. 100 000 cells), the memory is still not a major
problem (a few GB at most), but nothing happens anymore.
For 20 000 cells (1000 entries), it takes only 77 seconds, i.e. twice the speed. For 10 000 cells, it is 28 seconds, another 1.4x faster.
For 5000 cells, 10.5 seconds, another 1.3x faster.
Therefore, the cell budget should be a few thousands, not because of
memory, but because of asyncio task speed. Elision should happen early but gently. Apart from elision, all cells in an elision leaf (a macro that does not create
other macros) should have their context binding delayed and then executed as a whole.
Only at million+ cell graphs, memory will ever become a problem.
UPDATE2: Note that elision must also be done if the elided graph fails,
i.e. one of its outputs is not there. In that case, elided graph status must be stored as a deep checksum (combine with status redirection mechanism).
In any case, RPBS elision server is very needed!
12. Fix buffer length remnants from:
- communion server
- protocol.get_buffer.py
- cachemanager


Fairserver plan
===============
DONE - Add bufferinfo r/w support to database-run-actions
DONE - database-run-actions: For all deepcells and datasets together, store a single file deepcontent.json with the total content (summed buffer lengths of all entries) for each deepcell/dataset.
DONE: add a tool to store snapshots in $SDB/shared-directories
TODO: proceed from ~/FAIRSERVER and test-pdb.sh in there.

Fair server requests:
Human and machine. For now, just machine.
If unknown, just return 404.
The server keeps nothing in memory, content is just served by
opening files again and again.
1. /machine/page/<name of fairpage>
- Description
- Link to web page
- List of entries. Each entry:
  - checksum: deep checksum
  - type: deep cell or dataset
  - version number (only required if no date)
  - date (only required if no version number)
  - format (optional. for example, mmcif for pdb)
  - compression (optional. Can be gzip, zip, bzip2)
  - latest: yes or no. For a given format+compression, only one entry can be latest.
  - index_size: size of the deep buffer itself
  - nkeys: number of keys
  - content_size: see above.
  - keyorder: checksum 
  - download_index: checksum (if available)
Response is built dynamically by parsing:
$FD/page_entries/<page_name>.json and $FD/page_header/<page_name>.cson/.json/.yaml
2. /machine/find/<checksum>
   Response:
   - name of fairpage
   - fairpage entry (see above)
3. /machine/download-index/<download index checksum>
   Download index for the deep buffer
4. /machine/deepbuffer/<checksum>
   Deep buffer (= entry index) content 
5. /machine/keyorder/<keyorder checksum>
   Key order buffer (list of key orders) content.
6. /machine/get_entry?page=...&version=...&date=...
   /machine/get_checksum?page=...&version=...&date=...
   /machine/latest/page

