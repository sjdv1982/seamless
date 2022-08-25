TODO: split up!! Mostly to "features" documentation, some to "seamless explained"



### B3. Interactive workflows

Intro:


### Jupyter integration

- await translation
- traitlets, output

### C2. Mounting to the file system

Intro:

- mount, mode, authority
- Link to E1 (why files are bad)

Intermediate:

- Mount as directory

### C3. HTTP sharing

Intro:

- share
- cell.mimetype
- REST
- Your own web page, Seamless as file server (link to beginner gotchas)

### C4. Web status and web interface generation

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

### C5. Seamless projects

Intro:

- How to set up a project

Intermediate:

- Customize load-project
- Vaults, zips in relation to Git version control


### C7. Creating help for others

- Managing help contexts, HTML

## Part D. Software development with Seamless

### D1. Structured cells

Intro:
- Subcells and path building
- Silk (link to Silk::example, Silk::validation)
- Limitations: mount, read-only share with mimetype

Intermediate:
TODO: give a simple intro, but then link to big data instead
- Deep cells and hash patterns.

### D2. Silk

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

### D3. Environment

Intro:

- Conda, powers, which, image, Docker

### D4. Libraries and Library instances

Intro:

- Scatter transformers: TODO
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

### D5. Debugging Seamless transformers

Intro:
- Link to "compiled and interpreted"
- Debug mode

### D6. Polyglot and modules

Intro:
- Compiled and interpreted

In-depth:
- Adding your own language

### D7. Seamless and big data

Intro:
- Deep cells
- DeepCell, DeepFolderCell, FolderCell

Intermediate:
- Scatter transformers (TODO)
- stdlib.map

In-depth:
- Elision (link to library elision)

### D8. The low level

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

## Part E. Seamless and the rest of the world

### E1. Why files are bad

RIP
- Why Seamless is different from nextflow
- Link to: Nextflow-style channels, scatter transformers
- Link to reproducibility
- Converting from snakemake
/RIP

### E2. Reproducibility

Intermediate:
- Universal and delocalized computation
- Determinism, random generators, parallel/GPU.

In-depth:
- Link to "files are bad"
- Files and URLs are not reproducible
- Reproducibility: weak, strong and brittle.
- Interoperability (FAIR): weak, strong and brittle
- Provenance. Link: federation.

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

## Part F. Seamless implementation
(not quite developer docs, but very technical)
- How the high level wraps the graph data structure
- Various kinds of caches in Seamless
- Async tasks