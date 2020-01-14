The pre-cleanup tag is v0.2-pre-cleanup. In the commits immediately thereafter,
the following things were removed:

- Abandon slash. Creating a bash replacement is not a priority.
Seamless itself is moving away from the file system, and
bash transformers / docker transformers / snakemake 
can be used for legacy/transitional workflows that
are still based around command line tools.
The archive contains: 
    - the implementation
    - the specification (slash-ast.txt, slash-grammar.txt)
    - the docking example
    
- Final deletion from OLD/: the OpenGL library
Used signals (spooky effects at a distance) used by glwindow
 since they are at odds with reproducible computing.
Also, it depended on Qt. If revived, better port to the web 
(three.js?) or Vulkan (no signals needed?)
    - 3D example has been salvaged in this archive, minus some data files

- Removed all Qt support. 
Qt is probably not the technology of the future.
Three notes:
A: 
This is really a feature removal; Qt is working fine
 in 0.2 up to this cleanup. It is just something that I 
 don't wish to support any longer, with the move towards
 Docker images and serving HTML/JS/CSS cells that can be
 accessed over the web.
B:
This is also the final deletion from OLD/ of the lib/gui 
and similar stuff that depends on Qt. 
With the exception of OpenGL, much of this stuff 
should be working up to this cleanup.
C.
This also means that the Orca screensaver will no longer work
(it only worked with 0.1)
Port this to HTML in the future.

- Decided to remove plotly support.
Direct d3.js looks to be more sensible for now.
Nothing todo, already no traces in code base anymore.

- Removed fireworks 0.1 demo and notebook
This demo (of which there was a YouTube video) is no longer working,
 because it depended on OpenGL+Qt (glwindow)
This is in agreement with Seamless's heavier focus towards scientific computing
    - Fireworks demo example and Notebook been salvaged in this archive (not the notebook)

- Removed the rest of the old 0.1 library.
Dynamic HTML generation is probably not quite the way to go,
 now that web content can be easily served over the shareserver.