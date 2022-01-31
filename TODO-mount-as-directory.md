0. Run a test to determine a reasonable cell budget (step 11)
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
2. Finish core/mount_directory. Support continuous mount only for Repository and Modules! 
Support load_directory/write_directory only for Datasets, Repositories and Modules!
Write tests, adapt tests/highlevel/multi-module.py and graphs/multi_module/ accordingly.
3. Bump __seamless__ version of .seamless files to 0.8.
Rip mount.as_directory from high-level Cell. Change it to Module/dataset. Add a loader so that __seamless__ < 0.8 (or None) will interpret
a Cell("plain") with mount:as_directory as a Repository.
NOTE: especially important for webgen! 
4. Rip hash patterns from Cell, and adapt examples to use DeepCell, DeepListCell.
Write tests.
5. 
- Re-design database.py so that the default YAML normally works well,
and that there is a subfolder for download pages.
- For Dataset (not Repository), support loading-by-name.
Name may include version, format (e.g. gzip)
The RPBS will have a name server that does:
a. Map name+version+format to a checksum
b. Provide links to context/metadata websites (e.g. PDB main page)
c. Provide a link to download options. For the PDB, this would link to
a RPBS "download page", where for each once-or-current PDB checksum (also mmcif), a list of direct download links is provided. 
(example: https://files.rcsb.org/download/1AVX.pdb)
A direct download link can be annotated with "gzip" etc. The database will normally fetch the "download page" and store it locally.
In the future, support BitTorrent as well.
MAKE A BIG WARNING IF LOADING-BY-NAME IS DONE WITHIN LOAD-PROJECT!
This will make load-project not reproducible!!!
- Add a database command to load all entries in a download page in local file cache. File cache can be inside the database dir, but also an outside directory.
6. Add filename support to transformers, as outlined in https://github.com/sjdv1982/seamless/issues/108. Make bash/docker transformers accept Dataset inputs, leading to directory checksum requests.
Write tests, e.g. a hhblits search where the database path is a Dataset
checksum.
Adapt Cloudless with Shell deployment + file name rewrite and test if 
the dataset folder name is transferred.
7. fix the bug in the "DEBUGGING IN PROGRESS" commit (c9708d77598)
8. Allow cells in a subcontext to be marked as "input" or "output".
A subcontext will not translate unless all "inputs" have been connected.
.status of the subcontext and all its members will reflect this.
9. Allow "input"/"output" cells and all Transformer pins to have a "scatter" flag. Such cells or pins must be connected from DeepCell/DeepListCell if "mixed", or Dataset if "bytes".
Any Subcontext with "scatter" flags get translated via a stdlib.map
construction. Transformer with "scatter" flags get upgraded to Subcontext. This makes stdlib.map an implicit part of the Seamless high-level language, essentially.
10. Add a status redirection mechanism to catch error messages agnostic of the internal stdlib.map
11. "Internal elision". Have a cell budget (say, 10 000 cells). Wait with macro execution until the cell budget is below max. Elide macros immediately after their execution if the cell budget is above max.