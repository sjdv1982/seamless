from seamless import context, cell, export, transformer
from seamless.lib import edit, display, link, browse
from seamless.slash import slash0
import sys

#Stage 1
# Concatenate PDBs

ctx = context()
ctx.attract = cell(("text", "code", "slash-0"))
# !touch "attract.slash"
ctx.attract.fromfile("attract.slash")
link(ctx.attract)
ctx.attract.set("""
@input_doc pdbA
@input_doc pdbB
@intern pdb
@intern result

cat !pdbA !pdbB > pdb
cat !pdb > result

@export pdb
@export result
""")
ctx.slash = slash0(ctx.attract)
export(ctx.slash.pdbA)
export(ctx.slash.pdbB)
ctx.pdbA.fromfile("unbound/1AVXA.pdb")
ctx.pdbB.fromfile("unbound/1AVXB.pdb")
export(ctx.slash.pdb)
export(ctx.slash.result)
display(ctx.result, "Result")

### Stage 2
# Visualize PDB

from seamless.lib.ngl import ngl
v = ctx.view_pdb = ngl(["pdb"]) #False if ngl.js in local dir
ctx.pdb.connect(v.data_pdb)
export(v.representations, "cson")
# !touch "representations.cson"
ctx.representations.fromfile("representations.cson")
ctx.representations.set("[{}]")
link(ctx.representations)
h = ctx.view_pdb_html = export(v.html)
link(h, ".", "view-pdb.html")
# !google-chrome view-pdb.html &
browse(h)

### Stage 3
# Improve representation

ctx.representations.set("""
[
  {
    color: "red"
    sele: ":A"
  }
  {
    color: "blue"
    sele: ":B"
  }
  {
    repr: "ball+stick"
    color: "green"
    sele: "560-570:B"
  }
]
""")

### Stage 4
# reduce, randsearch, attract
#   result <= .dat file
# collect
#   pdb  <= collected pdb
# representation: cycle through models
# add fix-receptor

ctx.attract.set("""
@input_doc pdbA
@input_doc pdbB
@intern result
@intern pdbAr
@intern pdbBr
@intern pdb
@intern startstruc
@intern dockstruc
./scripts/reduce.sh !pdbA > pdbAr
./scripts/reduce.sh !pdbB > pdbBr
python $ATTRACTTOOLS/randsearch.py 2 10 --fix-receptor  > startstruc
$ATTRACTDIR/attract !startstruc $ATTRACTDIR/../attract.par !pdbAr !pdbBr --fix-receptor > dockstruc
cat !dockstruc > result
$ATTRACTDIR/collect !dockstruc !pdbA !pdbB > pdb

@export pdb
@export result
""")

ctx.representations.set("""
[
  {
    color: "red"
    sele: ":A"
  }
  {
    color: "blue"
    sele: ":B/0"
  }
]
""")

### Stage 5
# more starting structures, vmax=10
# grep energies
# display energies

ctx.attract.set("""
@input_doc pdbA
@input_doc pdbB
@intern result
@intern pdbAr
@intern pdbBr
@intern pdb
@intern startstruc
@intern dockstruc
@intern energies

./scripts/reduce.sh !pdbA > pdbAr
./scripts/reduce.sh !pdbB > pdbBr
python $ATTRACTTOOLS/randsearch.py 2 100 --fix-receptor  > startstruc
$ATTRACTDIR/attract !startstruc $ATTRACTDIR/../attract.par !pdbAr !pdbBr --fix-receptor --vmax 10 > dockstruc
grep 'Energy' !dockstruc | awk '{print $3}' | sort -n > energies
$ATTRACTDIR/collect !dockstruc !pdbA !pdbB > pdb

@export pdb
@export energies
@export result
""")

export(ctx.slash.energies)
display(ctx.energies, "Energies")

### Stage 6
# monitor, defray

ctx.attract.set("""
@input_doc pdbA
@input_doc pdbB
@intern result
@intern pdbAr
@intern pdbBr
@intern pdb
@intern startstruc
@intern dockstruc
@intern dockstruc0
@intern energies

./scripts/reduce.sh !pdbA > pdbAr
./scripts/reduce.sh !pdbB > pdbBr
python $ATTRACTTOOLS/randsearch.py 2 100 --fix-receptor  > startstruc
$ATTRACTDIR/attract !startstruc $ATTRACTDIR/../attract.par !pdbAr !pdbBr --fix-receptor --vmax 10 > dockstruc0 @ monitor 0.5
python ./scripts/defray-structures.py !dockstruc0 > dockstruc
grep 'Energy' !dockstruc0 | awk '{print $3}' | sort -n > energies
$ATTRACTDIR/collect !dockstruc !pdbA !pdbB > pdb

@export pdb
@export energies
@export result
""")

### Stage 7
# count structures and display
# show histogram of energies
# maximize energies at 20

ctx.attract.set("""
@input_doc pdbA
@input_doc pdbB
@intern result
@intern pdbAr
@intern pdbBr
@intern pdb
@intern startstruc
@intern dockstruc
@intern dockstruc0
@intern energies
@intern nstrucdone

./scripts/reduce.sh !pdbA > pdbAr
./scripts/reduce.sh !pdbB > pdbBr
python $ATTRACTTOOLS/randsearch.py 2 100 --fix-receptor  > startstruc
$ATTRACTDIR/attract !startstruc $ATTRACTDIR/../attract.par !pdbAr !pdbBr --fix-receptor --vmax 10 > dockstruc0 @ monitor 0.5
python ./scripts/defray-structures.py !dockstruc0 > dockstruc
grep 'Energy' !dockstruc0 | awk '-v' 'm=20' '{v=$3; if (v>m)v=m; print v}' | sort -n > energies
python ./scripts/count-structures.py !dockstruc > nstrucdone
$ATTRACTDIR/collect !dockstruc !pdbA !pdbB > pdb

@export pdb
@export energies
@export result
@export nstrucdone
""")

export(ctx.slash.nstrucdone, "int")
display(ctx.nstrucdone, "#structures")

from histo import histo
ctx.histo_energies = histo("Energies")
ctx.energies.connect(ctx.histo_energies.data)

## Stage 8
# euler2rotmat => poses
# result <= poses
# construct second NGL viewer

ctx.attract.set("""
@input_doc pdbA
@input_doc pdbB
@intern result
@intern pdbAr
@intern pdbBr
@intern pdb
@intern startstruc
@intern dockstruc
@intern dockstruc0
@intern energies
@intern nstrucdone
@intern poses

./scripts/reduce.sh !pdbA > pdbAr
./scripts/reduce.sh !pdbB > pdbBr
python $ATTRACTTOOLS/randsearch.py 2 100 --fix-receptor  > startstruc
$ATTRACTDIR/attract !startstruc $ATTRACTDIR/../attract.par !pdbAr !pdbBr --fix-receptor --vmax 10 > dockstruc0 @ monitor 0.5
python ./scripts/defray-structures.py !dockstruc0 > dockstruc
grep 'Energy' !dockstruc0 | awk '-v' 'm=20' '{v=$3; if (v>m)v=m; print v}' | sort -n > energies
python ./scripts/count-structures.py !dockstruc > nstrucdone
$ATTRACTDIR/collect !dockstruc !pdbA !pdbB > pdb
python ./scripts/euler2rotmat.py !dockstruc > poses
cat !poses > result

@export pdb
@export energies
@export result
@export nstrucdone
@export poses
""")

ctx.select_pose = transformer({
    "poses": {"pin": "input", "dtype": "json"},
    "struc": {"pin": "input", "dtype": "int"},
    "selected_pose": {"pin": "output", "dtype": "json"}
})
export(ctx.select_pose.selected_pose)
export(ctx.slash.poses)
ctx.poses.connect(ctx.select_pose.poses)
ctx.select_pose.code.cell().set("return poses[struc-1][1]")
export(ctx.select_pose.struc).set(1)
edit(ctx.struc, "Selected structure")

v = ctx.view_complex = ngl(["receptor", "ligand"], remote_ngl=True) #False if ngl.js in local dir
v.data_receptor.cell().fromfile("unbound/1AVXA.pdb")
v.data_ligand.cell().fromfile("unbound/1AVXB.pdb")
ctx.representations.connect(v.representations)
h = ctx.view_complex_html = export(v.html)
link(h, ".", "view-complex.html")
# !google-chrome view-complex.html &
ctx.selected_pose.connect(v.transformation_ligand)

## Stage 9
# playcontrol
from seamless.lib.gui.playcontrol import playcontrol
pc = ctx.playcontrol = playcontrol("Select structure")
pc.value.connect(ctx.struc)
ctx.nstrucdone.connect(pc.max)

## Stage 10
# parameterize nstruc, vmax
ctx.attract.set("""
@input_doc pdbA
@input_doc pdbB
@input_var nstruc
@input_var vmax
@intern result
@intern pdbAr
@intern pdbBr
@intern pdb
@intern startstruc
@intern dockstruc
@intern dockstruc0
@intern energies
@intern nstrucdone
@intern poses

./scripts/reduce.sh !pdbA > pdbAr
./scripts/reduce.sh !pdbB > pdbBr
python $ATTRACTTOOLS/randsearch.py 2 $nstruc --fix-receptor  > startstruc
$ATTRACTDIR/attract !startstruc $ATTRACTDIR/../attract.par !pdbAr !pdbBr --fix-receptor --vmax $vmax > dockstruc0 @ monitor 0.5
python ./scripts/defray-structures.py !dockstruc0 > dockstruc
grep 'Energy' !dockstruc0 | awk '-v' 'm=20' '{v=$3; if (v>m)v=m; print v}' | sort -n > energies
python ./scripts/count-structures.py !dockstruc > nstrucdone
$ATTRACTDIR/collect !dockstruc !pdbA !pdbB > pdb
python ./scripts/euler2rotmat.py !dockstruc > poses
cat !poses > result

@export pdb
@export energies
@export result
@export nstrucdone
@export poses
""")
export(ctx.slash.nstruc, "int").set(101)
export(ctx.slash.vmax, "int").set(12)
edit(ctx.nstruc, "Structures to dock")
edit(ctx.vmax, "Maximum minimization steps")
