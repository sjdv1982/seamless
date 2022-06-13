Tutorial
========

<!-- TODO: integrate new_project.md -->

# Part A. Getting started

## A1. How to use Seamless

Seamless is meant to bring together ...
Intro:
- Seamless CLI
- example (link to simple cells) + status
- new project + status + web form (link to C5.)
- Interactive programming, interactive workflows.
  Blurring between programmer and user. 
  More like Jupyter than like NextFlow (link)

In-depth (no pre-requisites):
- run from conda environment
- Docker commands
- link: files are bad, database, job manager

## A2. Getting help

Intro:
- Link to reference documentation.
- Accessing the help system

# Part B. Seamless basics

## B1. Simple cells, celltypes and checksums

Intro:
- Text cells
- Plain cells: str, float, int, bool
- Binary cells: numpy
- Mixed cells

Intermediate:
- .set, .observe
- Checksums and buffers: async. link to interactive plumbing. 
  ctx.resolve
- Conversion
- Pin celltypes: link to transformers, libraries
- Code cells, cson, yaml
  (link to mounting, link to semantic checksums)
- scratch
- Pin as_ attribute

In-depth:
- The illusion of values (link to fingertips)
- Subcelltypes
- Semantic checksums: code, cson, yaml
- Checksum cells (link to Structured cells::Deep cells)

## B2. Transformers and transformations

Intro:
- Python transformers
- .inp and .result (link to structured cells)
- Bash transformers
    - RESULT file or directory
    - filedict/filelist subcelltype TODO
- Transformers in IPython and R

Intermediate:
- Docker (link to environments)
- Compiled transformers:
    - header, integrator, executor
    - main_module multiple files (link to module)
- Meta parameters (computation times etc.)
- Transformations and checksums (link to universal delocalized computation)

In-depth:
- Link to polyglot
- Hacking on bash/compiled transformers (not interactively)
- Changing the translation machinery (not interactively)
- Irreproducible transformers (link to determinism)

## B3. Interactive plumbing

Intro:
- Contexts and subcontexts
- Dot and bracket syntax
- Children, tab completion in IPython
- Dependency graph and cancel 
- The .status attribute
- .exception
- logs
- Translate and compute and asynchronous. Link to "checksums and buffers"
- Link to web status (point out: if using project)
- Loading from/saving to graph/zip/vault
- Point to beginner's gotchas

Intermediate:
- Independent vs dependent: history doesn't matter, creating a new program
- bidirectional link
- Downstream dependency
- preliminary, progress
- clearing exceptions

In-depth:
- Fingertipping, cache misses and irreproducibility (link to transformer)
- Resolving cycles

# Part C. Building interactive workflows

## C1. Jupyter integration

Repeat: more like Jupyter than like nextflow, blurring between programmer and user.
Intro:
- await translation
- traitlets, output

## C2. Mounting to the file system

Intro:
- mount, mode, authority
- Link to E1 (why files are bad)

Intermediate:
- Mount as directory

## C3. HTTP sharing

Intro:
- share
- cell.mimetype
- REST
- Your own web page, Seamless as file server (link to beginner gotchas)

## C4. Web status and web interface generation

Intro:
- Web status
- Web interface

Intermediate:
- Customizing the web status generator
- The Seamless client library (and customize it)
- Adding your own web components
- Customizing the web interface generator

In-depth:
- The metalevel, observers, and understanding the status generator

## C5. Seamless projects

Intro:
- How to set up a project

Intermediate:
- Customize load-project
- Vaults, zips in relation to Git version control


## C6. Beginner gotchas
Intro:
- Import inside code (link to "checksums and buffers")
- Don't forget to translate (link to interactive plumbing)
- Seamless dislikes files:
    - Filename in bash transformer
    - Filename in share
    - Filename in mount
    - Link to "why files are bad"

## C7. Creating help for others
- Managing help contexts, HTML

# Part D. Software development with Seamless

## D1. Structured cells
Intro:
- Subcells and path building
- Silk (link to Silk::example, Silk::validation)
- Limitations: mount, read-only share with mimetype

Intermediate:
- Deep cells and hash patterns

## D2. Silk
Intro:
- Silk as a wrapper of mixed data; unsilk
- JavaScript-style attribute access
- example (cells and transformers)
- adding validation (cells and transformers)

Intermediate:
- Silk as a handle for structured cells: buffered and auth
- example and JSON schema; linking schemas.
- adding methods
- serialization
- Silk and _SCHEMA pins in transformers

## D3. Environment
Intro:
- Conda, powers, which, image, Docker

## D4. Libraries and Library instances
Intro:
- Scatter transformers
- Nextflow-style channels
- Gotcha: retranslate after setting a value
- Value and cell pins
- Celldict pins

Intermediate:
- Context pins
(link to: how the high level wraps the graph data structure)
- StaticContext
- Constructor
- Making your own library
- How libraries are embedded in the graph (link to: how the high level wraps the graph data structure)

In-depth:
- Elision 
- Context schema and api schema

## D5. Debugging Seamless transformers
Intro:
- Link to "compiled and interpreted"
- Debug mode 

## D6. Polyglot and modules
Intro:
- Compiled and interpreted

In-depth:
- Adding your own language

## D7. Seamless and big data

Intro:
- Scatter transformers

Intermediate:
- stdlib.map

In-depth:
- Elision (link to library elision)

## D8. The low level

Intermediate:
- High-level Macros
- Rules for the low level
- macro mode
- macros
- reactors and editpins
- high-in-low: 
    - HighLevelContext (link to: how the high level wraps the graph data structure)
    - pseudo-connections; 

In-depth:
- Libraries vs macros

# Part E. Seamless and the rest of the world

## E1. Why files are bad
- Why Seamless is different from nextflow
- Link to: Nextflow-style channels, scatter transformers
- Link to reproducibility
- Converting from snakemake

## E2. Reproducibility

Intermediate:
- Universal and delocalized computation
- Determinism, random generators, parallel/GPU.

In-depth:
- Link to "files are bad"
- Files and URLs are not reproducible
- Reproducibility: weak, strong and brittle.
- Interoperability (FAIR): weak, strong and brittle
- Provenance. Link: federation.

## E3. Deployment

Intro:
- Graph+zip
- serve-graph

Intermediate:
- Python deep down: link to low-level
- Communion
- Databases
- Cloudless and jobless

In-depth:
- Computation where the data is 
- Federation. Link: provenance

# Part F. Seamless implementation
(not quite developer docs, but very technical)
- How the high level wraps the graph data structure
- Various kinds of caches in Seamless
- Async tasks