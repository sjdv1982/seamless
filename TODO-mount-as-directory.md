
-1. Run a test to determine a reasonable cell budget (step 11)
UPDATE: see step 11
0: Fix the fact that you cannot set a deep list from a Numpy array (DeepStructureError).
UPDATE: first do Fairserver plan
1. Make DeepFolder, Folder, DeepCell classes.
They correspond to the following low-level deep cells:
 DeepFolder: hash pattern {"*": "##"} (deep-dict-of-filenames-as-byte-cells)
 Folder: same, but mountable to a folder, and .value and .schema work.
 DeepCell: hash pattern {"*": "#"} (deep-dict-of-mixed-cells)
Their API is similar to normal (structured) Cells.
They can be assigned to normal Cells (any kind of), but they do
not have arbitrary incoming subcell connections. DeepCell/DeepFolder do have an incoming connection for whitelist/blacklist.
For DeepCell/DeepFolder, the .define method can set their checksum(s) and metadata via the FAIR server. 
There is a .set method as well. Folder can be mounted to the filesystem.
Internally, they are translated to structured cells, making them convertible to normal Cells in the conversion engine. However, for DeepCell/DeepFolder, this is intentionally blocked, as it may blow up memory. It is still possible if the hash pattern of the normal Cell has been set (advanced feature). 
NOTE: keyorder (execution order checksum) is a part of DeepFolder/DeepCell as well! If you assign a DeepCell/DeepFolder to another, the keyorder gets copied as well.
NOTE2: You can ask a DeepCell/DeepFolder for .data, but this always returns the deep structure before whitelist/blacklist filtering.
To get it after filtering, create a new DeepCell/DeepFolder and assign it to the first.

2. Finish core/mount_directory. Support continuous mount only for Folder and Modules! For those, .mount is *always* to a directory
Support load_directory/write_directory only for DeepFolders, Folders and Modules!
Write tests, adapt tests/highlevel/multi-module.py and graphs/multi_module/ accordingly.

3. Bump __seamless__ version of .seamless files to 0.8.
Rip mount.as_directory from high-level Cell. Add a loader so that __seamless__ < 0.8 (or None) will interpret
a Cell("plain") with mount:as_directory as a Folder with .mount.
NOTE: especially important for webgen! 

4. Rip hash patterns from Cell, and adapt examples to use DeepCell.
Write tests.
NOTE: rip Resource?
UPDATE: don't rip, but document it as an advanced property.

==> here <==
5. 
- Re-design database.py so that the default YAML normally works well,
and that there is a subfolder for download pages/buffer info pages
of named deepfolders.
- DONE: For DeepFolder/DeepCell (not Folder), support loading-by-name.
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
DONE: buffer server
d. DONE: Map name+version+format to an execution order checksum.
e. DONE: Provide a link to a bufferinfo page for all relevant checksums.
MAKE A BIG WARNING IF LOADING-BY-NAME IS DONE WITHIN LOAD-PROJECT!
This will make load-project not reproducible!!!
- DONE; Add a database command to load all entries in a download page in local file cache. File cache can be inside the database dir, but also an outside directory. Do the same for bufferinfo entries.
UPDATE: 
a. load-by-name in a different API (seamless.fair)
b. TODO: Allow a list-of-allowed-checksums to be stored, by name. 
   DeepFolder.load(name) will invoke this.
   Possible to restrict allowed checksums only to this.
   Is also necessary to allow DeepFolder.share()  
   (list of allowed checksums becomes dropdown menu, restriction is security feature)
   DONE: Allow blacklist or whitelist checksum to be stored in DeepCell/DeepFolder
   (TODO: Destroys name-of-directory database hit for DeepFolder)
   Blacklist and whitelists are strictly local to the graph, no FAIR/database involved.
   Whitelist AND blacklist may be active, which means
   effective_whitelist = whitelist - blacklist.
UPDATE2: Seamless database and FAIR server are now distinct, but make
tools to export contents of the database dir (notably, /downloads,
/deepfolders, /deepcells, and deep buffers in /buffers) to a FAIR server dir. DONE.
DONE UPDATE3: make a PDB test, but rename stdlib.join to stdlib.select.
6. Add filename support to transformers, as outlined in https://github.com/sjdv1982/seamless/issues/108. There will be high-level transformer pin celltype "deepfolder", "deepcell".
Assigning a transformer pin to a DeepFolderCell, DeepCell
creates a pin of that celltype.
Assigning a transformer input to a FolderCell creates a "deepfolder" pin in case of a bash transformer
, a "mixed" pin otherwise. 
The high-level celltypes "deepfolder", "deepcell" do not exist at the low level.
Instead, "mixed" pins are created with the correct hash patterns, i.e. receiving the raw deep structure.
(test this!)
However, bash transformers will create these pins with "filesystem": {"mode": "directory", "optional": False}. "optional" will be True if connected to a Folder (re-connecting it to a DeepFolder will set it to
False). This makes sure that Seamless does not try to load/download gigantic datasets in memory and write them to disk by itself.
Also: use "as_" to select the filename/folder to write to, overruling pin name.
Pins of "deepfolder", "deepcell" are not part of the normal .inp structured cell and 
are hence not amenable to transformer input schemas.

Write tests, e.g. a hhblits search where the database path is a DeepFolder
checksum.
Adapt Cloudless with Shell deployment + file name rewrite and test if 
the deepfolder folder name is transferred.
7. DONE: fix the bug in the "DEBUGGING IN PROGRESS" commit (c9708d77598)
8. Allow cells in a subcontext to be marked as "input" or "output".
A subcontext will not translate unless all "inputs" have been connected.
.status of the subcontext and all its members will reflect this.
9. Allow "input"/"output" cells and all Transformer pins to have a "scatter" flag. Such cells or pins must be connected from DeepCell if "mixed", or DeepFolder if "bytes".
Any Subcontext with "scatter" flags get translated via a stdlib.map
construction. Transformer with "scatter" flags get upgraded to Subcontext. This makes stdlib.map an implicit part of the Seamless high-level language, essentially.
Alternatively, "input"/"output" cells and transformer pins that are 
*already* of the celltype DeepFolder/DeepCell/DeepListCell can have a "scatter_chunk" parameter, for map_dict_chunk evaluation. This does not
change the celltype of what they are connected to (the context/transformer will still operate on a deep dict/list, albeit a much smaller one). DONE: need then an API to get execution order (for incremental)!
Make sure that any scattered Subcontext/Transformer has no .mount or .share!
Also, modifying the value of a cell/pin CANNOT be relayed to the low level
(there are many low-level copies!) and a re-translation is necessary.
Tell this to the user when they make such a modification!
10. Add a status redirection mechanism to catch error messages agnostic of the internal stdlib.map. NOT URGENT: SPIN OFF INTO GITHUB ISSUE.
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
13. Do includables (https://github.com/sjdv1982/seamless/issues/119),
including finishing bootstrap.


