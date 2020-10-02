rm -f twopi-colored.seamless
python3 simple-pi-database.py
python3 twopi-graph-database.py
python3 ~/seamless-scripts/color-graph.py twopi.seamless twopi-colored.seamless
md5sum twopi-colored.seamless
