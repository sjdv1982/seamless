# Deployment

<!--

**Deployment role: transformation job service**. Needs to support as many types of 
transformations as possible. It must also support the cancellation of jobs.

**Deployment role: transformation result service**. Store transformation-to-result mapping.

**Deployment role: compilation service**. Store mapping of source code (C/C++) to compiled binary.
 

### E3. Deployment

Intro:
- Graph+zip
- serve-graph

Intermediate:
- Python deep down: link to low-level
- Communion
- Databases
- Buffer server
- Cloudless and jobless

In-depth:
- Computation where the data is 
- Federation. Link: provenance

-->

## Deploying a workflow as an interactive web service
...
You will need the .seamless file, and a zip file generated with `ctx.save_zip(...)`.
...
Seamless deployment is done using Cloudless (see section below).
...
Think of data storage...

## Cloudless

**Deployment role: live web servers**

This role is normally taken by ***Cloudless***. Note that Seamless embeds its own HTTP server. Thus, Cloudless is a rather simple program that does the following:

- It has a directory "graphs" with Seamless graph files.
- It listens on port 3124. It has an admin interface on /admin.
- It can take requests to launch an instance of a particular Seamless graph.
  This launches a new Docker container with Seamless serving the graph (the `seamless-serve-graph --database` command). With this, the instance connects itself to Seamless DB. In addition, the instance connects itself to jobless if configured (see below).
- HTTP traffic `from /instances/<instanceID>/` is redirected to/from the HTTP server ports of the Seamless instance.
- The graph of the Seamless instance is initially identical to that of the original graph. This changes whenever an input cell is changed over HTTP or a computation finishes. Every few seconds, the graph is stored in the "instances" directory. Note that the graph files are small as they contain only checksums. The underlying buffers are stored in the Seamless database.
- After 10 minutes of no HTTP traffic, the Seamless instance is killed. Whenever new traffic arrives, the Seamless instance is re-instantiated, not from the "graphs" directory, but from its graph file in the "instances" directory.

## Jobless

**Deployment role: transformation job service**

**Deployment role: compilation service**

These roles are normally taken by ***jobless***.

Jobless works by configuring a jobless .yaml file and define "jobhandlers". A jobhandler is a combination of a job plugin and a backend.

Job plugins can be for bash transformations with Docker, bash transformations without Docker, or generic transformations with conda environments. (See the section "Types of transformations" for more detail).

Backends can be:

- Local shell execution with seamless-cli (i.e. using Docker containers)
- Local shell execution with Singularity
- Slurm shell execution with Singulariy
- Local generic execution with seamless-cli
- Local generic execution with Singularity
- Slurm generic execution with Singularity

Jobless requires connection to the Seamless database for itself. Generic jobhandlers also need connection to the Seamless database.

Shell execution with Singularity requires a Singularity image for every Docker image that is being used. In contrast, generic execution only requires the "rpbs/seamless-minimal" Docker/Singularity image. This image contains only the Seamless source code, and relies on an *external* conda environment directory to provide the dependencies. Using seamless-cli commands, jobless exports, copies and updates these environment directories and provides them to the `seamless-minimal` container, in which the
`seamless-conda-env-run-transformation` tool is run.

Jobless is part of the seamless-tools repo. See that repo for more details.

### Using jobless

Seamless reads the jobless IP from the SEAMLESS_COMMUNION_IP environment  variable, which defaults your Docker host IP. The default jobless port (SEAMLESS_COMMUNION_PORT) is 5533.

# Section on deployment of environments (jobless)
...

## Buffer server

**Deployment role: buffer server**

The easiest way to set up a buffer server is to simply share the /buffers directory of a Seamless database directory over HTTP, e.g. using NGINX. The RPBS buffer server works like this.

## Big data and deployment

(bring the data where the computation is, general remarks... and/or link to:
- Seamless explained
- deepcell).

### collections and FAIR databases

Seamless has some facilities for maintaining and sharing deep cells and deep folders.

The `database-run-actions` tool revolves around the concept of "collection", which is essentially a deep structure with a name.
The tool does things like:

- Index an external directory (i.e. a directory under rsync control)
  into a "collection".
- Copy each entry in a collection into /buffers, or hard-link each entry
  to the external directory.
- Build a deep folder buffer for a collection
- Convert a deep folder collection to a deep cell collection
- Unzip each file in a collection
- Build a download index for a collection, i.e. a list of URLs where
  each item in a collection might be found for download.

In addition, there is a tool called `fair-add-distribution` that copies the "collection" deep structure buffers and their download indices, but NOT their underlying buffers, into a dataset "distribution", marked with metadata such as dataset name, version, format and date.  While a collection can change, a distribution should not. Run this repeatedly whenever a collection changes, to create snapshots of the current collection state. 

There is an experimental tool "fairserver.py" that allows querying of datasets, distributions, etc. This is organized using the FAIR principles, i.e. "/access" will retrieve a list of download URLs from the download index. More work is needed to achieve FAIR compliance.

An RPBS FAIR server is running at fair.rpbs.univ-paris-diderot.fr.
Seamless itself has DeepFolder and DeepCell classes that integrate with the FAIR server. For example, `DeepCell.find_distribution("pdb", date="2022-02-18", format="mmcif")` by default contacts the RPBS FAIR server to retrieve the checksum of the distribution. A distribution also has a keyorder, which is important if you just ran a tool on each chunk of an old version of the database, and then update the new database, and you want to re-use the results of the old chunks.
