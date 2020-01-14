docking.py

Example demonstrating the use of seamless in protein-protein docking
(the 3D assembly of a protein complex from their components),
using the ATTRACT docking engine (www.attract.ph.tum.de),
invoked via a slash (*) script

This seamless example requires Linux (OSX might work, but untested),
and a working installation of ATTRACT.
It will be demonstrated in a video tutorial on https://www.youtube.com/playlist?list=PL6WSTyQSLz08_GQqj-NyshaWnoIZMsqTK
This video tutorial is planned for August - September 2017.

Protein structure files in Protein Data Bank (PDB) format are available in
unbound/1AVXA.pdb (receptor) and unbound/1AVXB.pdb (ligand).

The original ATTRACT bash script is in attract-original/attract.sh. Note that
the original ATTRACT script is still considerably more sophisticated than the
slash script of this example. In future versions of seamless, when slash
matures, the example will be progressively improved.

How the example works
=====================

The example (docking.py) constructs a docking slash script in 10 stages.

Stage 1 simply concatenates the two PDB files and returns the result.

Stage 2 visualizes the result using NGL (see the seamless ngl example for more
details on how this is done), and stage 3 updates the NGL representation.
Open view-pdb.html in a browser.

Stage 4 converts the protein to ATTRACT coarse-grained representation using the
ATTRACT tool "reduce" (for now, wrapped in a bash script). Then, it generates
initial random poses using the ATTRACT tool "randsearch".
Finally, it energy-minimizes the poses using ATTRACT, keeping the receptor
fixed. This is the actual docking.
The NGL representation can be edited in representations.cson.
In NGL, ":B/0" means that the first docked ligand model is shown.
Change this to ":B/1", ":B/2" etc. to show other docking models.

Stage 5 increases the number of docked models, and displays their docking
energies in a text cell.

Stage 6 constantly monitors the docked structures as they are generated
(every 0.5 seconds). Because of stdout buffering, sometimes the "doc" containing
the docked structures ends in the middle of a structure.
defray-structures fixes this, removing the partial structure.

Stage 7 keeps a running count of the number of docked structures. In addition,
a histogram of the docked energies is constantly displayed (implemented in
histo.py; see the seamless plotly example for more details on how this is done).
Edit plotly_layout.cson and plotly_attrib.cson to modify the plot's visual
styling.

Stage 8 opens a second NGL viewer, that displays the selected structure.
The selected structure is sent as a transformation matrix (of the ligand) to
NGL, which internally applies the transformation on the atomic coordinates.

Stage 9 adds a movie-player-like control to cycle through the docking models.

Stage 10 makes the number of docking structures (nstruc) and the number of
minimization steps (vmax) editable parameters.

Other slash scripts
===================

The directory slash/ contains several slash scripts that perform a docking
protocol in slightly different ways:
- Using ATTRACT's grid acceleration
- Using clustering of the docked poses
- Calculates and plots the RMSD (=deviation) from the docked poses toward the
true protein-protein complex.
Copy them onto attract.slash to see their effects. The layout of the RMSD plot
is defined in plotly_layout_rmsd.cson; this requires the creation of some
new cells, see the docking2/ example for a demonstration.


(*) = slash stands for "seamless bash", a bash replacement language.
Slash is work-in-progress. The general idea is: slash has a bash-like syntax,
but its mechanics are those of a Makefile, executing a command when its
dependencies are updated. There will be two dialects, slash-1 and slash-0. For
now, only the lower-level slash-0 is somewhat working.
Slash-0 requires the explicit declaration of file-like cells ("docs") and
variable-like cells ("vars"). Docs can be imported and exported to the outside
world via seamless pins. Slash-0 commands look like bash: all vars must start
with $, but all docs must start with !, and all literals must be quoted.
See docs/WIP/slash-ast.txt and docs/slash-grammar.txt that are very preliminary
design documents.
