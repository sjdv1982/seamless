# Data storage

In Seamless, everything revolves around checksums. The primary purpose of data storage is to retrieve the underlying buffer of each checksum. In addition, there is "buffer info", the keeping of statistics that help in converting buffers from one celltype to another. Third, there is the storage of transformation results, in the form of a mapping of transformation checksum to result checksum. Finally, there is also compilation, the checksum-to-checksum mapping of source code in e.g. C/C++ to its compiled binary.

## Data storage explained

***IMPORTANT: This documentation section is an outline. The outline is shown below***

- Purpose: checksum to buffer caching
- dependent vs independent checksums, version control
- scratch cells

<!--
**Deployment role: checksum-to-buffer service**

**Deployment role: buffer info service**

**Deployment role: transformation result service**

**Deployment role: compilation service**

These roles are normally taken by the ***Seamless database***.
-->

### Exporting to zips or vaults

***IMPORTANT: This documentation section is a stub.***
(Only checksum-to-buffer cache! Transformations will be recomputed!)

## The Seamless database

***IMPORTANT: This documentation section is a stub.***
(checksum-to-buffer cache, buffer info, etc. over the network, "serving a vault")

### Using the database

***IMPORTANT: This documentation section is a draft. The preliminary text is shown below***

A Seamless instance connected to the database does not maintain its own checksum-to-buffer cache, and therefore uses a lot less memory.

You can start the database with the command `seamless-database`. By default, it loads  /seamless-tools/tools/default-database.yaml, which maintains the database dir in  \$HOME/.seamless/database, but you can supply your own configuration file. Primarily, the database dir contains /buffers, containing one file per buffer (the filename is the checksum, e.g. /buffers/93237a60bf6417104795ed085c074d52f7ae99b5ec773004311ce665eddb4880).The other stores (buffer info, transformation result, compilation, and a few specialized others) map a checksum to either another checksum or something other that is very small. Therefore, each of those stores is organized as JSON files that are split in buckets as they grow larger.

Seamless reads the database IP from the SEAMLESS_DATABASE_IP environment variable, which defaults your Docker host IP. The default Seamless database port (SEAMLESS_DATABASE_PORT) is 5522.

### Database cleanup

The buckets do not take up much space, there is little reason to delete them.  In contrast, buffers/ can get very large. You can freely delete the contents of /buffers while the database is running, this will not cause any crash. The database has a memory cache that may continue to hold the buffer for a while. To cleanly remove any kind of database entry, create a file with a format like
`/seamless-tools/tools/jobless/tests/jobless-test-dblog-ORIGINAL.txt` and then run `seamless-delete-database-from-log <filename>`.

Note that any workflow or transformation job slave that needs the buffer but can't find it will report a CacheMissError. This will happen for sure if the buffer is *independent*, i.e. is not the result of some kind of computation (transformation, conversion, cell expression etc.). If it *is* the result of a computation, and the computation is part of the workflow that is loaded by the Seamless instance, Seamless may try to repeat the computation in order to regenerate the buffer (this is called "fingertipping"). So you can be a bit more aggressive in deleting buffers of intermediate results (or even final results), especially if they are large and/or quick to compute.

### Multiple database directories

It is possible to set up multiple database directories with Seamless database. Only one will be written to, the other ones are read-only. The purpose can be: setting up specialized databases (e.g. the Protein Data Bank), backup, or having them in different file zones.

### File zones

The Seamless database has a special request where you can ask directly for the filename that corresponds to the buffer. With the request, you can specify a file zone (or multiple file zones). If the Seamless database directory is in the same file zone (or in one of the file zones), the file name (i.e. `/buffers/<checksum>`) is assumed to be accessible by the requesting instance, and is returned. In other words, "same file zone" means "same file system". This is very efficient in case of bash transformers,leading to a hard link instead of load-buffer-from-database + write-buffer-to-file-in-temp-directory. In case of a deep folder, the special request is for a folder. Seamless has a tool called `database-share-deepfolder-directory`. It takes a deep folder checksum (or its collection name, see below), reads the deep folder dict, creates a folder `/shared-directories/<deep checksum>/`, and creates a hard link `/shared-directories/<deep checksum>/key` to `/buffers/<checksum>` for every key:checksum pair in the dict. Therefore, `/shared-directories/<deep checksum>` is an exact mirror of the deep folder mounted to disk, without taking any disk space whatsoever. Therefore, bash transformers that take a deep folder as input (e.g. a database search tool) get a soft link to `/shared-directories/<deep checksum>` instead of copying the entire database every time. Of course, this does require that the file zone is the same.
